from __future__ import annotations

"""Canonical repository-root launcher for the GeoAI SimKit desktop GUI."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit.app.launcher_entry import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], repo_root=ROOT, launcher_name="start_gui.py"))
