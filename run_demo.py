from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from geoai_simkit.examples.pit_example import run_demo  # noqa: E402
except Exception as exc:  # pragma: no cover
    print("Failed to import demo dependencies.")
    print(exc)
    print("Tip: install base dependencies first: python -m pip install -r requirements.txt")
    raise SystemExit(1)

if __name__ == "__main__":
    out = run_demo(ROOT / "exports_root")
    print(out)
