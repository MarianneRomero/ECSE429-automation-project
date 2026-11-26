"""Performance experiments for the Todo Manager REST API.

For each resource and each repeat, starting from an empty server:

  for each level N (ascending):
    populate  create random objects until there are N (every create is timed)
    add       timed POST /<resource>; each new object is deleted right after (untimed)
    update    timed POST /<resource>/:id (amend) on a random id, all fields re-randomised
    delete    timed DELETE /<resource>/:id on a random id; it is recreated right after (untimed)

Restoring after every add/delete means each timed add, update and delete runs
against exactly N objects (this also works when k > N).

Each add/update/delete phase runs at least k operations AND lasts at least
--min-phase-s seconds, so the resource monitor (sampling every --interval s) takes
several samples inside every phase. Requests take well under a millisecond, so k
operations alone would finish between two samples.

Two times are recorded:
  T2        transaction time of one operation: only the HTTP call, inside
            perf_counter() (raw_timings.csv).
  T1_level  total time of one measurement level: populate from the previous level
            to N + the first k add, update and delete operations with their
            restores (levels.csv). Operations that only extend a phase to its
            minimum sampling duration are excluded, so T1_level does not depend on
            --min-phase-s; the full wall-clock time is level_wall_ms.
(analyze.py derives T1_cumulative, the running sum of populate time from 0 to N.)

A request that fails or returns an unexpected status is written to errors.csv,
never to raw_timings.csv.

Usage:
    python performance/perf_runner.py --resource all --monitor
    python performance/perf_runner.py --quick --monitor        # fast smoke test
"""

import argparse
import csv
import json
import platform
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median

import psutil
import requests

from client import BASE_URL, RESOURCES, ApiClient, not_ready_reason
from monitor import find_java_process
from random_data import RandomData

HERE = Path(__file__).resolve().parent
DEFAULT_LEVELS = [1, 5, 10, 50, 75, 100, 200, 300, 400, 500, 600, 700, 800, 900,
                  1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
DEFAULTS = {"levels": DEFAULT_LEVELS, "k": 20, "repeats": 3, "min_phase_s": 0.5}
QUICK = {"levels": [1, 10, 50, 100, 500], "k": 5, "repeats": 1, "min_phase_s": 0.3}
MEASURED_OPERATIONS = ("add", "update", "delete")
EXPECTED_STATUS = {"populate": 201, "add": 201, "update": 200, "delete": 200}
WARMUP_REQUESTS = 20  # per resource, excluded from results
MAX_FAILURES = 50     # consecutive failures before a phase gives up

TIMING_FIELDS = ["timestamp", "run_id", "repeat", "resource", "operation", "N", "op_index",
                 "elapsed_ms", "status_code"]
ERROR_FIELDS = ["timestamp", "run_id", "repeat", "resource", "operation", "N", "op_index",
                "status_code", "detail"]
PHASE_FIELDS = ["start_ts", "end_ts", "repeat", "resource", "operation", "N"]
LEVEL_FIELDS = ["start_ts", "end_ts", "repeat", "resource", "N", "T1_level_ms", "level_wall_ms",
                "populate_ms", "add_k_ms", "update_k_ms", "delete_k_ms"]


# --------------------------------------------------------------------------- output

class Recorder:
    """Writes raw_timings.csv, phases.csv, levels.csv and errors.csv (overwritten each run)."""

    def __init__(self, out_dir, run_id):
        self.run_id = run_id
        self._files = []
        self.timings = self._open(out_dir / "raw_timings.csv", TIMING_FIELDS)
        self.phases = self._open(out_dir / "phases.csv", PHASE_FIELDS)
        self.levels = self._open(out_dir / "levels.csv", LEVEL_FIELDS)
        self.errors = self._open(out_dir / "errors.csv", ERROR_FIELDS)
        self.error_count = 0

    def _open(self, path, fields):
        handle = path.open("w", newline="")
        self._files.append(handle)
        writer = csv.writer(handle)
        writer.writerow(fields)
        return writer

    def timing(self, ts, repeat, resource, operation, n, op_index, elapsed_ms, status):
        self.timings.writerow([f"{ts:.6f}", self.run_id, repeat, resource, operation, n, op_index,
                               f"{elapsed_ms:.4f}", status])

    def error(self, ts, repeat, resource, operation, n, op_index, status, detail):
        self.error_count += 1
        self.errors.writerow([f"{ts:.6f}", self.run_id, repeat, resource, operation, n, op_index,
                              status, detail[:200]])

    def phase(self, start, end, repeat, resource, operation, n):
        self.phases.writerow([f"{start:.6f}", f"{end:.6f}", repeat, resource, operation, n])

    def level(self, start, end, repeat, resource, n, wall_ms, parts):
        t1 = sum(parts.values())
        self.levels.writerow([f"{start:.6f}", f"{end:.6f}", repeat, resource, n, f"{t1:.3f}", f"{wall_ms:.3f}",
                              *(f"{parts[name]:.3f}" for name in ("populate", *MEASURED_OPERATIONS))])
        return t1

    def close(self):
        for handle in self._files:
            handle.close()


def p95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def progress(label, n, operation, elapsed, errors, seconds):
    """One compact line per phase (kept under ~100 columns for the screen recording)."""
    stats = (f"T2 mean {mean(elapsed):.3f}  med {median(elapsed):.3f}  p95 {p95(elapsed):.3f} ms"
             if elapsed else "no successful requests")
    print(f"{label} N={n:>5} {operation:<8} {len(elapsed):>5} ops  {stats}  err {errors}  {seconds:4.2f}s",
          flush=True)


# --------------------------------------------------------------------------- measuring

def timed_request(client, method, path, body=None):
    """(elapsed_ms, response, error). Only the HTTP call is timed."""
    started = time.perf_counter()
    try:
        response = client.request(method, path, body)
    except requests.RequestException as error:
        return None, None, error
    elapsed_ms = (time.perf_counter() - started) * 1000
    return elapsed_ms, response, None


class ResourceExperiment:
    """One resource, one repeat: grows the collection level by level."""

    def __init__(self, client, recorder, data, resource, args, repeat):
        self.client = client
        self.recorder = recorder
        self.data = data
        self.rng = data.rng
        self.resource = resource
        self.k = args.k
        self.min_phase_s = args.min_phase_s
        self.repeat = repeat
        self.label = f"[{resource:<10} {repeat}/{args.repeats}]"
        self.ids = []  # ids currently on the server for this resource

    def measure(self, operation, n, op_index, method, path, body=None):
        """Time one request; record it as a timing or an error.
        Returns (elapsed_ms, response) on success, (None, None) on failure."""
        ts = time.time()
        elapsed_ms, response, error = timed_request(self.client, method, path, body)
        if error is not None or response.status_code != EXPECTED_STATUS[operation]:
            status = "" if response is None else response.status_code
            detail = repr(error) if error is not None else response.text
            self.recorder.error(ts, self.repeat, self.resource, operation, n, op_index, status, detail)
            return None, None
        self.recorder.timing(ts, self.repeat, self.resource, operation, n, op_index,
                             elapsed_ms, response.status_code)
        return elapsed_ms, response

    def run_level(self, n):
        """Run one level; returns T1 in ms."""
        level_start, level_clock = time.time(), time.perf_counter()
        parts = {"populate": self.phase("populate", n, self._populate)}
        for operation, step in (("add", self._add), ("update", self._update), ("delete", self._delete)):
            parts[operation] = self.phase(operation, n, lambda n_, elapsed, op=step: self._timeboxed(n_, elapsed, op))
        wall_ms = (time.perf_counter() - level_clock) * 1000
        return self.recorder.level(level_start, time.time(), self.repeat, self.resource, n, wall_ms, parts)

    def phase(self, operation, n, body):
        """Run one phase, write its marker and progress line; returns its T1 share in ms."""
        elapsed, errors_before = [], self.recorder.error_count
        start, clock = time.time(), time.perf_counter()
        t1_ms = body(n, elapsed)
        self.recorder.phase(start, time.time(), self.repeat, self.resource, operation, n)
        progress(self.label, n, operation, elapsed, self.recorder.error_count - errors_before,
                 time.perf_counter() - clock)
        return t1_ms

    def _populate(self, n, elapsed):
        clock, op_index, failures = time.perf_counter(), 0, 0
        while len(self.ids) < n:
            ms, response = self.measure("populate", n, op_index, "POST", f"/{self.resource}",
                                        self.data.payload(self.resource))
            op_index += 1
            if response is None:
                failures += 1
                if failures > MAX_FAILURES:
                    raise RuntimeError(f"populating {self.resource} failed {failures} times; see errors.csv")
                continue
            self.ids.append(response.json()["id"])
            elapsed.append(ms)
        return (time.perf_counter() - clock) * 1000

    def _timeboxed(self, n, elapsed, step):
        """Repeat `step` until at least k operations ran and the phase lasted
        min_phase_s. Returns the time the first k operations took (T1 share)."""
        clock, op_index, failures, first_k_ms = time.perf_counter(), 0, 0, None
        while op_index < self.k or time.perf_counter() - clock < self.min_phase_s:
            if step(n, op_index, elapsed):
                failures = 0
            else:
                failures += 1
                if failures > MAX_FAILURES:
                    raise RuntimeError(f"{self.resource}: {failures} failures in a row; see errors.csv")
            op_index += 1
            if op_index == self.k:
                first_k_ms = (time.perf_counter() - clock) * 1000
        return first_k_ms

    def _add(self, n, op_index, elapsed):
        ms, response = self.measure("add", n, op_index, "POST", f"/{self.resource}",
                                    self.data.payload(self.resource))
        if response is None:
            return False
        elapsed.append(ms)
        self.client.delete(self.resource, response.json()["id"])  # restore N, untimed
        return True

    def _update(self, n, op_index, elapsed):
        object_id = self.rng.choice(self.ids)
        ms, response = self.measure("update", n, op_index, "POST", f"/{self.resource}/{object_id}",
                                    self.data.payload(self.resource))
        if response is None:
            return False
        elapsed.append(ms)
        return True

    def _delete(self, n, op_index, elapsed):
        position = self.rng.randrange(len(self.ids))
        ms, response = self.measure("delete", n, op_index, "DELETE", f"/{self.resource}/{self.ids[position]}")
        if response is None:
            return False
        elapsed.append(ms)
        self.ids[position] = self.client.create(self.resource, self.data.payload(self.resource))  # restore N
        return True

    def cleanup(self):
        for object_id in self.ids:
            self.client.delete(self.resource, object_id)
        self.ids = []


def warm_up(client, data, resources):
    """Throwaway create/amend/delete cycles so the JVM is warm before measuring."""
    for resource in resources:
        sent = 0
        while sent < WARMUP_REQUESTS:
            object_id = client.create(resource, data.payload(resource))
            client.request("POST", f"/{resource}/{object_id}", data.payload(resource))
            client.delete(resource, object_id)
            sent += 3


# --------------------------------------------------------------------------- monitor & metadata

def start_monitor(out_dir, interval):
    process = subprocess.Popen([sys.executable, str(HERE / "monitor.py"),
                                "--out", str(out_dir), "--interval", str(interval)])
    time.sleep(1.5)  # a few baseline samples before the first experiment
    return process


def stop_monitor(process):
    if process is None:
        return
    time.sleep(1.0)  # a few trailing samples after the last experiment
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def command_output(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout or result.stderr).strip() or None  # `java -version` prints to stderr


def machine_info():
    java = find_java_process()
    java_cmd = "java"
    if java is not None:
        try:
            java_cmd = java.exe() or "java"  # the JVM actually serving the API
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    java_version = command_output(java_cmd, "-version")
    mac_version = platform.mac_ver()[0]
    return {
        "chip": (command_output("sysctl", "-n", "machdep.cpu.brand_string") if sys.platform == "darwin"
                 else None) or platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1),
        "os": f"macOS {mac_version}" if mac_version else platform.platform(),
        "os_build": command_output("sw_vers", "-buildVersion") if sys.platform == "darwin" else None,
        "architecture": platform.machine(),
        "java_version": java_version.splitlines()[0] if java_version else None,
        "java_runtime": java_version.splitlines()[1] if java_version and len(java_version.splitlines()) > 1 else None,
        "python_version": platform.python_version(),
        "server_pid": java.pid if java else None,
        "server_started": datetime.fromtimestamp(java.create_time()).isoformat(timespec="seconds") if java else None,
    }


# --------------------------------------------------------------------------- main

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resource", choices=[*RESOURCES, "all"], default="all")
    parser.add_argument("--levels", type=lambda s: [int(x) for x in s.split(",")],
                        help="comma-separated object counts, ascending (default 1,5,10,...,10000; "
                             "append ,20000 for the optional extra level)")
    parser.add_argument("--k", type=int, help=f"minimum timed operations per phase (default {DEFAULTS['k']})")
    parser.add_argument("--min-phase-s", type=float, dest="min_phase_s",
                        help=f"minimum duration of each add/update/delete phase in s (default {DEFAULTS['min_phase_s']})")
    parser.add_argument("--repeats", type=int, help=f"repeats per resource (default {DEFAULTS['repeats']})")
    parser.add_argument("--seed", type=int, help="random seed (default: chosen at random and logged)")
    parser.add_argument("--out", type=Path, default=HERE / "results", help="output directory")
    parser.add_argument("--monitor", action="store_true", help="sample CPU/memory with monitor.py during the run")
    parser.add_argument("--interval", type=float, default=0.1, help="monitor sampling interval in s (default 0.1)")
    parser.add_argument("--quick", action="store_true",
                        help=f"smoke test: levels {','.join(map(str, QUICK['levels']))}, k={QUICK['k']}, "
                             f"repeats={QUICK['repeats']}, min phase {QUICK['min_phase_s']} s (explicit options win)")
    args = parser.parse_args()

    preset = QUICK if args.quick else DEFAULTS
    for name, value in preset.items():
        if getattr(args, name) is None:
            setattr(args, name, value)
    if args.seed is None:
        args.seed = random.SystemRandom().randrange(2 ** 31)
    if any(n <= 0 for n in args.levels) or args.levels != sorted(set(args.levels)):
        parser.error("--levels must be positive and strictly increasing")
    if args.k <= 0 or args.repeats <= 0 or args.min_phase_s < 0 or args.interval <= 0:
        parser.error("--k, --repeats and --interval must be positive; --min-phase-s must be >= 0")
    return args


def main():
    sys.stdout.reconfigure(line_buffering=True)  # keep output in order when piped or recorded
    args = parse_args()
    resources = list(RESOURCES) if args.resource == "all" else [args.resource]

    reason = not_ready_reason()
    if reason:
        sys.exit(f"Server not ready: {reason}.\n"
                 f"Start it with: java -jar runTodoManagerRestAPI-1.5.5.jar  (expected at {BASE_URL})")

    args.out.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    info = {
        "run_id": run_id,
        "parameters": {
            "base_url": BASE_URL, "resources": resources, "levels": args.levels, "k": args.k,
            "min_phase_s": args.min_phase_s, "repeats": args.repeats, "seed": args.seed,
            "monitor": args.monitor, "sample_interval_s": args.interval,
            "warmup_requests_per_resource": WARMUP_REQUESTS,
            "operations": {"populate": "POST /<resource>", "add": "POST /<resource>",
                           "update": "POST /<resource>/:id (amend, all fields)",
                           "delete": "DELETE /<resource>/:id"},
        },
        "machine": machine_info(),
        "start": datetime.now().isoformat(timespec="seconds"),
    }

    machine = info["machine"]
    print(f"Run {run_id}: resources={','.join(resources)} levels={args.levels[0]}..{args.levels[-1]} "
          f"({len(args.levels)} levels) k={args.k} min_phase={args.min_phase_s}s repeats={args.repeats} "
          f"seed={args.seed}")
    print(f"Machine: {machine['chip']}, {machine['ram_gb']} GB RAM, {machine['os']}, "
          f"{machine['java_version']}, Python {machine['python_version']}; server PID {machine['server_pid']}")

    client = ApiClient()
    data = RandomData(args.seed)
    recorder = Recorder(args.out, run_id)
    monitor = start_monitor(args.out, args.interval) if args.monitor else None
    wall_start = time.perf_counter()
    experiment = None
    try:
        warm_up(client, data, resources)
        print(f"Warm-up done ({WARMUP_REQUESTS}+ requests per resource, not recorded)")
        for resource in resources:
            for repeat in range(1, args.repeats + 1):
                client.wipe()  # clean state, including the server's default objects
                experiment = ResourceExperiment(client, recorder, data, resource, args, repeat)
                for n in args.levels:
                    t1 = experiment.run_level(n)
                    print(f"{experiment.label} N={n:>5} T1_level {t1:8.1f} ms", flush=True)
            experiment.cleanup()
            experiment = None
            print(f"{resource}: done, all created objects deleted")
    except KeyboardInterrupt:
        print("\nInterrupted; cleaning up")
    finally:
        if experiment is not None:
            experiment.cleanup()
        recorder.close()
        stop_monitor(monitor)
        client.close()
        info["end"] = datetime.now().isoformat(timespec="seconds")
        info["duration_s"] = round(time.perf_counter() - wall_start, 1)
        info["errors"] = recorder.error_count
        (args.out / "run_info.json").write_text(json.dumps(info, indent=2))

    print(f"Finished in {info['duration_s']} s with {recorder.error_count} errors. Results in {args.out}")


if __name__ == "__main__":
    main()
