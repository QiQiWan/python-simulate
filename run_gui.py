from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from geoai_simkit.app.main_window import launch_main_window  # noqa: E402
except Exception as exc:  # pragma: no cover
    print("Failed to import GUI dependencies.")
    print(exc)
    print("Tip: install GUI dependencies first: python -m pip install -r requirements-ui.txt")
    raise SystemExit(1)

if __name__ == "__main__":
    launch_main_window()
