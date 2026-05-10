from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools._no_install_bootstrap import bootstrap

def main() -> int:
    root = bootstrap()
    from geoai_simkit.fem.api import run_core_fem_api_smoke
    from geoai_simkit.app.completion_matrix import write_completion_matrix_artifacts
    result = run_core_fem_api_smoke()
    for rel in ['reports/core_fem_smoke_results.json', 'docs/core_fem_smoke_results.json']:
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    artifacts = write_completion_matrix_artifacts(root/'docs', test_results_path=root/'reports/core_fem_smoke_results.json')
    print(f"Core FEM smoke: {result['passed_count']}/{result['check_count']} ok={result['ok']}")
    print(f"Completion matrix: {artifacts['markdown_path']}")
    return 0 if result.get('ok') else 2
if __name__ == '__main__': raise SystemExit(main())
