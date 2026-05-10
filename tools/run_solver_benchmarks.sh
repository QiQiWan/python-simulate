#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 run_solver_benchmarks.py "$@"
