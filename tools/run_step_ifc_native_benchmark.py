from __future__ import annotations

import argparse
import json
from pathlib import Path

from geoai_simkit.services.step_ifc_native_benchmark import (
    run_step_ifc_native_benchmark,
    write_step_ifc_benchmark_manifest_template,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P8.5 STEP/IFC native certification benchmark.")
    parser.add_argument("input", nargs="?", default="benchmarks/step_ifc", help="STEP/IFC file, directory, or JSON/JSONL manifest")
    parser.add_argument("--output", default="reports/step_ifc_native_benchmark.json")
    parser.add_argument("--allow-fallback", action="store_true", help="Allow surrogate/fallback imports for CI/dry-run diagnostics")
    parser.add_argument("--repeat-count", type=int, default=2, help="Number of repeated imports used for stability checks")
    parser.add_argument("--element-size", type=float, default=1.0, help="Default CAD-FEM mesh control element size")
    parser.add_argument("--write-template", help="Write a benchmark manifest template and exit")
    args = parser.parse_args()

    if args.write_template:
        path = write_step_ifc_benchmark_manifest_template(Path(args.write_template))
        print(json.dumps({"ok": True, "manifest_template": str(path)}, ensure_ascii=False, indent=2))
        return 0

    report = run_step_ifc_native_benchmark(
        Path(args.input),
        output_path=Path(args.output),
        require_native=not args.allow_fallback,
        repeat_count=max(1, int(args.repeat_count)),
        default_element_size=args.element_size,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
