from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap() -> Path:
    root = Path(__file__).resolve().parent
    src = root / 'src'
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    for name in ('logs', 'exports', 'autosave'):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    _bootstrap()
    try:
        if '--smoke' in argv:
            from geoai_simkit.app.launch import build_desktop_gui_startup_report

            report = build_desktop_gui_startup_report(offscreen=True)
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 0 if report.get('ok') else 2

        from geoai_simkit.app.launch import launch_desktop_workbench
        launch_desktop_workbench()
        return 0
    except Exception as exc:
        print('GeoAI SimKit GUI could not start:')
        print(exc)
        print('Install dependencies with: python -m pip install -r requirements.txt')
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
