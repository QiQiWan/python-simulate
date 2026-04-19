from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit._optional import require_optional_dependency  # noqa: E402


def main() -> None:
    try:
        require_optional_dependency("PySide6", feature="The desktop GUI", extra="gui")
        require_optional_dependency("pyvista", feature="The desktop GUI", extra="gui")
        require_optional_dependency("pyvistaqt", feature="The desktop GUI", extra="gui")
        from geoai_simkit.app.workbench_window import launch_nextgen_workbench  # noqa: E402
    except RuntimeError as exc:  # pragma: no cover
        print(exc)
        raise SystemExit(2) from exc
    except Exception as exc:  # pragma: no cover
        print("Failed to import GUI dependencies.")
        print(exc)
        print("Tip: install full dependencies first: python -m pip install -r requirements.txt")
        raise SystemExit(1) from exc

    launch_nextgen_workbench()


if __name__ == "__main__":
    main()
