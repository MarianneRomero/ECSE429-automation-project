"""Resource monitor: samples CPU and memory with psutil while the experiments run.

Every `--interval` seconds (default 0.1) it appends one row to
<out>/system_samples.csv:

    timestamp      Unix time of the sample (same clock as raw_timings.csv / phases.csv)
    sys_cpu_pct    whole-machine CPU %, averaged over all cores (0-100)
    java_cpu_pct   CPU % of the Todo Manager's Java process, as % of ONE core
                   (can exceed 100 when the JVM uses several cores); blank if not found
    avail_mem_mb   memory available to new processes (psutil.virtual_memory().available)
    java_rss_mb    resident memory of the Java process; blank if not found

perf_runner.py --monitor starts this as a subprocess and stops it with SIGTERM.
It can also be run by hand:  python performance/monitor.py --out performance/results
Stop it with Ctrl-C.
"""

import argparse
import csv
import os
import signal
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import psutil

JAR_MARKER = "runTodoManagerRestAPI"
FIELDS = ["timestamp", "sys_cpu_pct", "java_cpu_pct", "avail_mem_mb", "java_rss_mb"]
MB = 1024 * 1024


def api_port():
    """Port of the API under test (TODO_API_URL, as in Part A; default 4567)."""
    url = urlparse(os.environ.get("TODO_API_URL", "http://localhost:4567"))
    return url.port or 80


def _listens_on(proc, port):
    try:
        return any(conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port
                   for conn in proc.net_connections(kind="tcp"))
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def find_java_process(marker=JAR_MARKER):
    """The java process running the Todo Manager jar, or None. If several are
    running, the one listening on the API's port is chosen."""
    candidates = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmdline = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if "java" in name and marker in cmdline:
            candidates.append(proc)
    if not candidates:
        return None
    port = api_port()
    chosen = next((proc for proc in candidates if _listens_on(proc, port)), candidates[0])
    chosen.cpu_percent(None)  # prime: the first call always returns 0.0
    return chosen


def java_stats(proc):
    """(cpu %, rss MB) for the Java process, or (None, None) if it is gone."""
    try:
        with proc.oneshot():
            return proc.cpu_percent(None), proc.memory_info().rss / MB
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None, None


def run(out_dir, interval):
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "system_samples.csv"

    java = find_java_process()
    if java is None:
        print(f"[monitor] WARNING: no java process running {JAR_MARKER}*.jar found; "
              "java_cpu_pct / java_rss_mb will be blank", flush=True)
    else:
        print(f"[monitor] sampling every {interval}s; Todo Manager java PID {java.pid}", flush=True)
    psutil.cpu_percent(None)  # prime the system-wide counter

    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        next_tick = time.monotonic() + interval
        while not stop.wait(max(0.0, next_tick - time.monotonic())):
            next_tick += interval
            if java is None:
                java = find_java_process()
            java_cpu, java_rss = java_stats(java) if java else (None, None)
            if java_cpu is None:
                java = None  # process ended; look for it again next tick
            writer.writerow([
                f"{time.time():.3f}",
                f"{psutil.cpu_percent(None):.1f}",
                "" if java_cpu is None else f"{java_cpu:.1f}",
                f"{psutil.virtual_memory().available / MB:.1f}",
                "" if java_rss is None else f"{java_rss:.1f}",
            ])
            handle.flush()
    print(f"[monitor] stopped; samples in {path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results")
    parser.add_argument("--interval", type=float, default=0.1, help="seconds between samples")
    args = parser.parse_args()
    run(args.out, args.interval)


if __name__ == "__main__":
    main()
