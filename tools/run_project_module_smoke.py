from __future__ import annotations

"""Run the coarse project-module facade smoke suite."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit.modules import run_project_module_smokes  # noqa: E402


def main() -> int:
    result = run_project_module_smokes()
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "project_module_smoke.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "passed": result["passed_count"], "total": result["check_count"], "report": str(out_path)}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
