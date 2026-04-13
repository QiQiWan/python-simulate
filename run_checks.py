from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit.env_check import collect_environment_checks, format_environment_report  # noqa: E402

if __name__ == "__main__":
    print(format_environment_report(collect_environment_checks()))
