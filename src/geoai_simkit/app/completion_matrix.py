from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from geoai_simkit.fem.api import get_core_fem_api_contracts, run_core_fem_api_smoke

ROOT = Path(__file__).resolve().parents[3]

def _load_json(path: str | Path | None) -> dict[str, Any] | None:
    if not path: return None
    p = Path(path)
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return None

def _candidate(paths):
    for p in paths:
        data = _load_json(p)
        if data is not None:
            data['source'] = str(p)
            return data
    return None

def _load_core_results(path: str | Path | None = None) -> dict[str, Any]:
    return _load_json(path) or _candidate([ROOT/'reports/core_fem_smoke_results.json', ROOT/'docs/core_fem_smoke_results.json']) or run_core_fem_api_smoke()

def _load_benchmark_results(path: str | Path | None = None) -> dict[str, Any]:
    return _load_json(path) or _candidate([ROOT/'reports/benchmark_report.json', ROOT/'benchmark_reports/benchmark_report.json']) or {'suite':'not_run','accepted': None, 'passed_count':0, 'benchmark_count':0, 'benchmarks': [], 'source': 'not_run'}

def _core_rows(core: dict[str, Any]) -> list[dict[str, Any]]:
    checks = {c.get('key'): c for c in list(core.get('checks', []) or [])}
    rows=[]
    for c in get_core_fem_api_contracts():
        ck = checks.get(c['key'], {})
        smoke_ok = bool(ck.get('ok'))
        smoke_status = ck.get('status','numerical_smoke')
        rows.append({
            **c,
            'smoke_ok': smoke_ok,
            'smoke_status': smoke_status,
            'smoke_value': ck.get('value'),
            'test_result': dict(ck),
            'test_driven_status': 'passed' if smoke_ok else str(smoke_status or 'not_run'),
        })
    return rows

def build_completion_matrix(test_results_path: str | Path | None = None, benchmark_results_path: str | Path | None = None) -> dict[str, Any]:
    core = _load_core_results(test_results_path)
    bench = _load_benchmark_results(benchmark_results_path)
    return {
        'contract': 'completion_matrix_v2',
        'source': 'generated_from_core_smoke_and_solver_benchmarks',
        'core_fem': _core_rows(core),
        'advanced': [
            {'key':'gpu_native','namespace':'geoai_simkit.solver.gpu_native','status':'capability_gated'},
            {'key':'occ_native','namespace':'geoai_simkit.geometry.occ_native_naming','status':'capability_gated'},
            {'key':'uq','namespace':'geoai_simkit.advanced.uq','status':'capability_gated'},
        ],
        'test_results': core,
        'benchmark_results': bench,
    }

def render_completion_matrix_markdown(matrix: dict[str, Any]) -> str:
    core = matrix.get('test_results', {}) or {}; bench = matrix.get('benchmark_results', {}) or {}
    lines = ['# Completion matrix', '', 'Generated from the same JSON artifacts written by `tools/run_core_fem_smoke.py` and `run_solver_benchmarks.py`.', '', f"Core smoke suite: `{core.get('suite','unknown')}`", f"Core smoke passed: **{core.get('passed_count',0)}/{core.get('check_count',0)}**", f"Solver benchmark suite: `{bench.get('suite','not_run')}`", f"Solver benchmarks passed: **{bench.get('passed_count',0)}/{bench.get('benchmark_count',0)}**", '', '| Module | Namespace | Numerical smoke | Status |', '|---|---|---:|---|']
    for row in matrix.get('core_fem', []):
        lines.append(f"| {row.get('label')} | `{row.get('target_namespace')}` | {row.get('smoke_ok')} | {row.get('status')} |")
    lines += ['', '## Advanced capability-gated modules', '', '| Module | Namespace | Status |', '|---|---|---|']
    for row in matrix.get('advanced', []):
        lines.append(f"| {row.get('key')} | `{row.get('namespace')}` | {row.get('status')} |")
    return '\n'.join(lines) + '\n'

def write_completion_matrix_artifacts(out_dir: str | Path = 'docs', *, test_results_path: str | Path | None = None, benchmark_results_path: str | Path | None = None) -> dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    matrix = build_completion_matrix(test_results_path, benchmark_results_path)
    json_path = out/'COMPLETION_MATRIX.generated.json'; md_path = out/'COMPLETION_MATRIX.generated.md'
    json_path.write_text(json.dumps(matrix, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    md_path.write_text(render_completion_matrix_markdown(matrix), encoding='utf-8')
    return {'json_path': str(json_path), 'markdown_path': str(md_path)}


def build_gui_home_payload() -> dict[str, Any]:
    matrix = build_completion_matrix()
    return {'headline': 'FEM completion dashboard', 'completion_matrix': matrix, 'core_fem_ready': matrix.get('test_results', {}).get('ok', False)}

# v0.8.36 operation-page dashboard override kept at end so older imports get the new shape.
def build_gui_home_payload() -> dict[str, Any]:
    matrix = build_completion_matrix()
    cards = [
        {'key':'modeling','label':'Modeling','summary':'Geometry and staged objects'},
        {'key':'mesh','label':'Mesh','summary':'Mesh and contact-aware assembly'},
        {'key':'solve','label':'Solve','summary':'Validation, compile and solve'},
        {'key':'results','label':'Results','summary':'Stage fields and acceptance'},
        {'key':'benchmark','label':'Benchmark','summary':'Numerical smoke and solver benchmarks'},
        {'key':'advanced','label':'Advanced modules','summary':'GPU/OCC/UQ capability gates'},
    ]
    return {'headline':'FEM completion dashboard','cards':cards,'completion_matrix':matrix,'core_fem_ready': matrix.get('test_results', {}).get('ok', False)}
