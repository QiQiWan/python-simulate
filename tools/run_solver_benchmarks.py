from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    from geoai_simkit.app.completion_matrix import write_completion_matrix_artifacts
    from geoai_simkit.fem.api import run_core_fem_api_smoke
    from geoai_simkit.solver.benchmark_report import write_benchmark_report

    parser = argparse.ArgumentParser(description="Run GeoAI SimKit solver benchmarks and regenerate completion matrix.")
    parser.add_argument("--out", default=str(ROOT / "benchmark_reports"), help="Output report directory.")
    args = parser.parse_args()

    summary = write_benchmark_report(Path(args.out))
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    bench_src = Path(summary["json_path"])
    bench_dst = reports / "benchmark_report.json"
    if bench_src.exists():
        shutil.copyfile(bench_src, bench_dst)

    core = run_core_fem_api_smoke()
    core_path = reports / "core_fem_smoke_results.json"
    core_path.write_text(json.dumps(core, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    artifacts = write_completion_matrix_artifacts(ROOT / "docs", test_results_path=core_path, benchmark_results_path=bench_dst)

    print(f"Benchmark report: {summary['markdown_path']}")
    print(f"JSON report: {summary['json_path']}")
    print(f"Completion matrix: {artifacts['markdown_path']}")
    print(f"Passed: {summary['passed_count']}/{summary['benchmark_count']}; core={core['passed_count']}/{core['check_count']}")
    return 0 if summary.get("accepted") and core.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
