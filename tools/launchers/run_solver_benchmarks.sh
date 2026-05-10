#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../.."
python3 tools/run_solver_benchmarks.py "$@"
