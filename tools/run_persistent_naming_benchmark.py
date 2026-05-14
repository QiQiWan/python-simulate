from __future__ import annotations

import argparse
import json
from pathlib import Path

from geoai_simkit.services.persistent_naming_benchmark import run_persistent_naming_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Run persistent topology naming benchmark on real STEP/IFC files.")
    parser.add_argument("input", help="Benchmark file or directory containing .step/.stp/.ifc files")
    parser.add_argument("--output", default="reports/persistent_naming_benchmark.json")
    parser.add_argument("--allow-fallback", action="store_true", help="Allow non-native fallback imports for dry-run diagnostics")
    args = parser.parse_args()
    report = run_persistent_naming_benchmark(Path(args.input), output_path=Path(args.output), require_native=not args.allow_fallback)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
