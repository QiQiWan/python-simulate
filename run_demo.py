from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit._optional import require_optional_dependency  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the packaged geoai-simkit demo")
    parser.add_argument("--out-dir", default=str(ROOT / "exports_root"), help="Directory for exported demo files")
    parser.add_argument("--execution-profile", default="auto", choices=["auto", "cpu-robust", "cpu-debug", "gpu"], help="Demo runtime profile")
    parser.add_argument("--device", default=None, help="Preferred solver device, e.g. cpu or cuda:0")
    args = parser.parse_args()

    try:
        require_optional_dependency("pyvista", feature="The packaged demo", extra="gui")
        from geoai_simkit.examples.pit_example import run_demo  # noqa: E402
    except RuntimeError as exc:  # pragma: no cover
        print(exc)
        raise SystemExit(2) from exc
    except Exception as exc:  # pragma: no cover
        print("Failed to import demo dependencies.")
        print(exc)
        print("Tip: install full dependencies first: python -m pip install -r requirements.txt")
        raise SystemExit(1) from exc

    out = run_demo(Path(args.out_dir), execution_profile=args.execution_profile, device=args.device)
    print(out)


if __name__ == "__main__":
    main()
