# Part C — Performance testing

Measures how long the Todo Manager takes to **add, update and delete** todos,
projects and categories as the number of objects N grows, while sampling
**CPU %** and **available free memory** with psutil.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r performance/requirements.txt
java -jar runTodoManagerRestAPI-1.5.5.jar        # in another terminal; listens on http://localhost:4567
```

`TODO_API_URL` points the suite at another address, exactly as in Part A.

## Run everything (for the video)

Restart the jar by hand so it starts fresh, open Activity Monitor next to the terminal, then:

```sh
performance/run_all.sh
```

The script never starts or stops the jar. It runs four steps:

1. Checks that the server is reachable, using Part A's check. If not, it stops with a clear message.
2. Deletes the previous `performance/results/`.
3. Runs `perf_runner.py --resource all --monitor` with the full default settings and
   copies the console output to `results/console.log`.
4. Runs `analyze.py`, then prints a short summary: total runtime, number of timed
   requests, errors, monitor samples, number of charts and the output folder.

A full run takes about 7 minutes on an M4 Pro (6.6 min of experiments plus about 20 s of analysis).
Any extra arguments are passed on to `perf_runner.py`. `RESULTS_DIR` changes the output folder.

Smoke test (levels 1,10,50,100,500, k=5, 1 repeat, 0.3 s phases, about 25 s in total):

```sh
performance/run_all.sh --quick
```

The two steps can also be run by hand:

```sh
.venv/bin/python performance/perf_runner.py --resource all --monitor && .venv/bin/python performance/analyze.py
```

Optional extra level: `--levels 1,5,10,50,75,100,200,300,400,500,600,700,800,900,1000,2000,3000,4000,5000,6000,7000,8000,9000,10000,20000`.

## Files

| File | Role |
|---|---|
| `client.py` | Session-based request helper. Reuses `BASE_URL`, `TIMEOUT`, `items()` from `test/support.py` and the readiness check from `test/conftest.py` |
| `random_data.py` | Seedable random payloads (`python performance/random_data.py --resource todos --count 3 --seed 1` previews them) |
| `perf_runner.py` | The experiment runner (below) |
| `monitor.py` | psutil sampler; started/stopped by `perf_runner.py --monitor`, or run on its own |
| `analyze.py` | Builds the summaries and the charts |
| `run_all.sh` | One command for the video: check, clear, run, analyse, summary |

### perf_runner.py options

| Option | Default | Meaning |
|---|---|---|
| `--resource` | `all` | `todos`, `projects`, `categories` or `all` |
| `--levels` | `1,5,10,50,75,100,200,…,900,1000,2000,…,10000` (24 levels) | object counts N, ascending |
| `--k` | `20` | minimum timed operations per add/update/delete phase |
| `--min-phase-s` | `0.5` | minimum duration of each add/update/delete phase (s) |
| `--repeats` | `3` | full repeats per resource |
| `--seed` | random (logged) | seed for payloads and id choice; reuse it to reproduce a run |
| `--out` | `performance/results` | output folder (files are overwritten) |
| `--monitor` | off | sample CPU/memory during the run |
| `--interval` | `0.1` | monitor sampling period (s) |
| `--quick` | off | smoke-test preset; explicit options still win |

## What the runner does

1. Exits with a clear message if the server is not reachable (Part A's check).
2. Warm-up: 20+ untimed create/amend/delete requests per resource (JVM warm-up).
3. For each resource and each repeat, it first **deletes every object on the server,
   including the server's default objects** (2 todos, 1 project, 2 categories), so N
   is exact. Then for each level N, in ascending order:

   | Phase | Request (timed = T2) | Untimed restore |
   |---|---|---|
   | populate | `POST /<resource>` until there are N objects | — |
   | add | `POST /<resource>` with a random body | the new object is deleted |
   | update | `POST /<resource>/:id` (amend) on a random id, all fields re-randomised. `PUT` is not used because it is a full replace (BUG-04) | — |
   | delete | `DELETE /<resource>/:id` on a random id | a new random object is created |

   Restoring after each add/delete keeps every timed add, update and delete at
   exactly N objects, even when k > N.

   Each add/update/delete phase runs **at least k operations and at least
   `--min-phase-s` seconds**. One request takes well under 1 ms, so k = 20 requests
   alone would finish between two monitor samples. The minimum duration puts
   several samples (about 5 with the defaults) inside every phase.
4. At the end of each resource, everything it created is deleted.

Only the HTTP call is inside the `time.perf_counter()` bracket. A response with an
unexpected status (201 for populate/add, 200 for update/delete) or a connection
error goes to `errors.csv`, never to `raw_timings.csv`.

### T2, T1_level and T1_cumulative

- **T2** is the transaction time of the single operation under test. Only the HTTP
  call is timed.
- **T1_level** is the time to complete one measurement level. It includes
  populating from the previous level up to N, plus the first k add, update and
  delete operations with their restores. Operations run only to reach the minimum
  phase duration are left out, so T1_level does not depend on `--min-phase-s`. The
  level's full wall-clock time is `level_wall_ms`. T1_level mostly reflects the
  spacing between levels (100 vs 1,000 objects added), not N itself.
- **T1_cumulative** is the total populate time to build the collection from 0 up to N.
  It is the running sum of the populate times of one repeat, averaged over repeats.

## Output (`performance/results/`)

| File | Contents |
|---|---|
| `raw_timings.csv` | one row per successful timed request (T2): `timestamp, run_id, repeat, resource, operation, N, op_index, elapsed_ms, status_code` |
| `phases.csv` | start/end of every phase: `start_ts, end_ts, repeat, resource, operation, N` |
| `levels.csv` | one row per level and repeat: `T1_level_ms`, `level_wall_ms` and the T1_level parts (`populate_ms`, `add_k_ms`, `update_k_ms`, `delete_k_ms`) |
| `errors.csv` | failed requests (same keys plus `status_code`, `detail`) |
| `system_samples.csv` | `timestamp, sys_cpu_pct, java_cpu_pct, avail_mem_mb, java_rss_mb` |
| `run_info.json` | chip, cores, RAM, macOS version, Java and Python versions, all parameters, start/end time, duration, error count |
| `summary.csv` | long form, one row per (resource, operation, N): `T2_ops, T2_mean_ms, T2_median_ms, T2_p95_ms, T2_std_ms, T2_min_ms, T2_max_ms, errors`, mean CPU/memory of the samples inside that phase, `samples_per_phase_mean/min`, `T1_level_ms`, `T1_cumulative_ms`, `level_wall_ms` |
| `summary_<resource>.csv` | Excel layout, one row per N: `N, add_ms, update_ms, delete_ms, cpu_pct, java_cpu_pct, free_mem_mb, java_rss_mb, T1_level_ms, T1_cumulative_ms`. The add/update/delete columns are mean T2. The usage columns average every sample taken during that level's add/update/delete phases, over all repeats |
| `console.log` | the runner's console output (written by `run_all.sh`) |
| `charts/` | PNG charts at 200 dpi, listed below |

All CSVs written by `analyze.py` are UTF-8 with BOM, so they open directly in Excel.

Charts, for each resource (`todos`, `projects`, `categories`). Add, Update and
Delete keep the same colour (blue, orange and green) in every chart.
`analyze.py` deletes old PNGs before drawing, so `charts/` only ever holds charts
made from the current results.

Combined report figures each have three panels side by side and are sized to be read at half a page:

| Chart | Shows |
|---|---|
| `<resource>_combined_vs_n.png` | (a) T2, (b) Java process CPU, (c) free available memory vs N; linear N axis |
| `<resource>_combined_vs_n_logx.png` | the same figure with a log-scale N axis |
| `<resource>_combined_vs_sample_time.png` | the same three metrics vs sample time |

Individual charts:

| Chart | Shows |
|---|---|
| `<resource>_time_vs_n.png` | mean T2 vs N |
| `<resource>_cpu_vs_n.png` | system CPU % vs N |
| `<resource>_java_cpu_vs_n.png` | Java process CPU % vs N |
| `<resource>_memory_vs_n.png` | available free memory (MB) vs N |
| `<resource>_java_rss_vs_n.png` | Java process RSS (MB) vs N |
| `<resource>_t1_vs_n.png` | T1_level vs N |
| `<resource>_t1_cumulative_vs_n.png` | T1_cumulative vs N |
| `<resource>_time_vs_sample_time.png` | every T2 measurement vs ms since the experiment started |
| `<resource>_{cpu,java_cpu,memory,java_rss}_vs_sample_time.png` | every monitor sample vs time (grey), with samples taken during add/update/delete phases marked in their colour |

`python performance/analyze.py --logx` draws the individual vs-N charts with a log-scale
N axis. The combined vs-N figure is always written in both versions.

### Reading CPU and memory

- `sys_cpu_pct` is the whole machine averaged over all cores (0–100). `java_cpu_pct`
  is the server's JVM as a percentage of **one** core, so it can exceed 100.
- `avail_mem_mb` is memory available to the whole machine, so other apps affect it.
  `java_rss_mb` is the server's own resident memory.
- A phase's CPU and memory are the mean of the samples taken inside it. Nothing is
  interpolated or smoothed. `analyze.py` prints the minimum number of samples per
  phase and warns if any phase had none.

## Machine specs for the report

`run_info.json` records them for each run. Also note which other apps were open
and whether the laptop was on power.
