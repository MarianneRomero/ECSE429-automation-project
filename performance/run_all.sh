#!/usr/bin/env bash
# One-command performance run for the video:
#   check server -> clear old results -> perf_runner (full defaults, --monitor) -> analyze -> summary
#
# Usage (from anywhere):   performance/run_all.sh
# Extra arguments go to perf_runner.py, e.g.  performance/run_all.sh --quick
# Environment:  TODO_API_URL (server, as in Part A), RESULTS_DIR (default performance/results),
#               PYTHON (default .venv/bin/python, else python3)
#
# This script never starts or stops the Todo Manager jar.
set -euo pipefail

cd "$(dirname "$0")/.."                       # repository root
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
RESULTS="${RESULTS_DIR:-performance/results}"

banner() { printf '\n==== %s ====\n' "$1"; }

banner "1/4  Checking the Todo Manager server"
if ! "$PY" -c 'import sys; sys.path.insert(0, "performance")
from client import BASE_URL, not_ready_reason
reason = not_ready_reason()
print(f"Server ready at {BASE_URL}" if not reason else f"Server not ready: {reason}")
sys.exit(1 if reason else 0)'; then
    echo "Start it first:  java -jar runTodoManagerRestAPI-1.5.5.jar"
    exit 1
fi

banner "2/4  Clearing previous results in $RESULTS"
case "$RESULTS" in
    ""|"/"|"."|"..") echo "Refusing to clear RESULTS_DIR='$RESULTS'"; exit 1 ;;
esac
rm -rf -- "$RESULTS"
mkdir -p -- "$RESULTS"

banner "3/4  Running the experiments (perf_runner.py --resource all --monitor $*)"
start=$(date +%s)
"$PY" performance/perf_runner.py --resource all --monitor --out "$RESULTS" "$@" 2>&1 | tee "$RESULTS/console.log"

banner "4/4  Aggregating results and drawing charts (analyze.py)"
"$PY" performance/analyze.py --results "$RESULTS"
end=$(date +%s)

banner "Summary"
"$PY" - "$RESULTS" "$((end - start))" <<'EOF'
import csv, json, sys
from pathlib import Path

results, total_s = Path(sys.argv[1]), int(sys.argv[2])
info = json.loads((results / "run_info.json").read_text())

def data_rows(name):
    with (results / name).open() as handle:
        return sum(1 for _ in csv.reader(handle)) - 1  # minus the header

charts = len(list((results / "charts").glob("*.png")))
print(f"Total runtime      {total_s // 60} min {total_s % 60} s (experiments {info['duration_s']} s)")
print(f"Timed requests     {data_rows('raw_timings.csv'):,} (T2 measurements, plus untimed setup/restore)")
print(f"Errors             {data_rows('errors.csv')}")
print(f"Monitor samples    {data_rows('system_samples.csv'):,}")
print(f"Charts             {charts}")
print(f"Output folder      {results.resolve()}")
EOF
