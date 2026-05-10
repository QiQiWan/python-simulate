from __future__ import annotations

"""No-install GUI launcher kept at repository root for convenience."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["gui"]))
