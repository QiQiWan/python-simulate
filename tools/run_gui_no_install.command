#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 run_gui_no_install.py "$@"
