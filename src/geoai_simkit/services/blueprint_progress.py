from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BlueprintModuleProgress:
    module_id: str
    plane: str
    blueprint_section: str
    title: str
    percent_complete: int
    status: str
    summary: str
    next_steps: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ('next_steps', 'blockers', 'evidence', 'missing_evidence'):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True, slots=True)
class BlueprintReleaseGate:
    gate_id: str
    title: str
    module_ids: tuple[str, ...]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _exists(rel: str) -> bool:
    return (_project_root() / rel).exists()


def _module(
    module_id: str,
    plane: str,
    section: str,
    title: str,
    summary: str,
    evidence: tuple[str, ...],
    *,
    tests: tuple[str, ...] = (),
    next_steps: tuple[str, ...] = (),
    blockers: tuple[str, ...] = (),
) -> BlueprintModuleProgress:
    all_evidence = tuple(evidence) + tuple(tests)
    present = tuple(item for item in all_evidence if _exists(item))
    missing = tuple(item for item in all_evidence if not _exists(item))
    file_score = len(present) / max(1, len(all_evidence))
    test_score = len(tuple(t for t in tests if _exists(t))) / max(1, len(tests)) if tests else 0.0
    percent = int(round(20 + 55 * file_score + 25 * test_score))
    if missing and percent > 84:
        percent = 84
    if tests and test_score == 0:
        percent = min(percent, 74)
    if percent >= 95:
        status = 'verified'
    elif percent >= 85:
        status = 'implemented-needs-tests'
    elif percent >= 70:
        status = 'partial'
    else:
        status = 'gap'
    gap_notes = tuple(f'Missing evidence: {item}' for item in missing[:4])
    return BlueprintModuleProgress(module_id, plane, section, title, percent, status, summary, next_steps, blockers + gap_notes, present, missing)


def build_blueprint_progress_snapshot() -> tuple[BlueprintModuleProgress, ...]:
    return (
        _module('test_governance', 'Quality Plane', '§Q1', 'Layered regression testing', 'Fast/solver/gui/slow test layers are now explicit, but broader benchmarks still need growth.', ('pyproject.toml',), tests=('tests/fast/test_iter81_fast_contracts.py', 'tests/solver/test_iter81_hardening.py'), next_steps=('Add more material and contact benchmark tests.',)),
        _module('engineering_model', 'Engineering Model', '§1 / §5.1', 'Core engineering model + StageAction semantics', 'SimulationModel now supports object-level StageAction in addition to legacy region activation.', ('src/geoai_simkit/core/model.py', 'src/geoai_simkit/solver/staging.py'), tests=('tests/fast/test_iter81_fast_contracts.py',), next_steps=('Migrate GUI stage editing fully from region rows to object actions.',)),
        _module('tet4_reference_solver', 'Kernel Plane', '§14.3', 'CPU Tet4 reference solver', 'Tet4 remains the trusted reference path, now with mesh gate metadata and support for truss-like structural overlays.', ('src/geoai_simkit/solver/tet4_linear.py', 'src/geoai_simkit/solver/backends/__init__.py', 'src/geoai_simkit/solver/linsys/sparse_block.py'), tests=('tests/solver/test_iter81_hardening.py',), next_steps=('Add patch/cantilever/gravity numerical tolerances against analytical references.',)),
        _module('mesh_solve_gate', 'Preprocess Plane', '§7', 'Mesh quality as solve gate', 'Mesh quality reports can now reject strict solves instead of remaining passive diagnostics.', ('src/geoai_simkit/geometry/mesh_quality.py', 'src/geoai_simkit/solver/mesh_quality_gate.py'), tests=('tests/fast/test_iter81_fast_contracts.py',), next_steps=('Wire gate status into Solve button state and result-package acceptance.',)),
        _module('structural_coupling', 'Kernel Plane', '§13', 'Truss-like support stiffness overlay', 'Truss/anchor/strut members now contribute axial stiffness and pretension loads to Tet4 solves; full beam/plate/shell is still pending.', ('src/geoai_simkit/solver/structural/truss3d.py', 'src/geoai_simkit/pipeline/structures.py'), tests=('tests/solver/test_iter81_hardening.py',), next_steps=('Implement beam3d and plate/shell coupling with rotational DOF recovery.',)),
        _module('gui_cad_interaction', 'Application Plane', '§22', 'CAD-grade viewport interaction foundation', 'Viewport drag uses camera-aware working-plane translation rather than fixed pixel scaling.', ('src/geoai_simkit/post/qt_viewport_events.py', 'src/geoai_simkit/app/viewport/edit_tools/working_plane.py', 'src/geoai_simkit/app/shell/unified_workbench_window.py'), tests=('tests/fast/test_iter81_fast_contracts.py',), next_steps=('Add snapping, axis handles, undo grouping, and entity-level preview transactions.',)),
        _module('gpu_runtime', 'Kernel Plane', '§17 / §18', 'GPU/native runtime path', 'GPU/Warp bridge files exist as compatibility shells, but real CUDA/Warp benchmark evidence is not present in this package.', ('src/geoai_simkit/solver/warp_hex8.py', 'src/geoai_simkit/solver/gpu_native_assembly.py', 'src/geoai_simkit/solver/gpu_runtime.py'), tests=(), blockers=('No real CUDA/Warp acceptance test in this replacement package.',), next_steps=('Treat GPU native nonlinear assembly as experimental until benchmarked.',)),
    )


_RELEASE_GATES: tuple[BlueprintReleaseGate, ...] = (
    BlueprintReleaseGate('trustworthy_solve_chain', 'Trustworthy solve chain', ('test_governance', 'tet4_reference_solver', 'mesh_solve_gate', 'structural_coupling'), 'Minimum evidence for a trustworthy strict-mode FEM workflow.'),
    BlueprintReleaseGate('interactive_modeling', 'Interactive modeling', ('engineering_model', 'gui_cad_interaction'), 'Object-level staged modeling and CAD-like viewport interaction.'),
    BlueprintReleaseGate('accelerated_runtime', 'Accelerated runtime', ('gpu_runtime',), 'Native/GPU route beyond the CPU Tet4 reference solver.'),
)


def _gate_status(percent: float) -> str:
    if percent >= 95.0:
        return 'verified'
    if percent >= 85.0:
        return 'implemented-needs-tests'
    if percent >= 70.0:
        return 'partial'
    return 'gap'


def build_release_gate_snapshot() -> list[dict[str, Any]]:
    rows = {item.module_id: item for item in build_blueprint_progress_snapshot()}
    gates: list[dict[str, Any]] = []
    for gate in _RELEASE_GATES:
        members = [rows[module_id] for module_id in gate.module_ids if module_id in rows]
        if not members:
            continue
        percent = round(sum(item.percent_complete for item in members) / len(members), 1)
        blockers = list(dict.fromkeys(blocker for item in members for blocker in item.blockers if str(blocker).strip()))
        next_steps = list(dict.fromkeys(step for item in members for step in item.next_steps if str(step).strip()))
        gates.append({'gate_id': gate.gate_id, 'title': gate.title, 'summary': gate.summary, 'percent_complete': percent, 'status': _gate_status(percent), 'module_count': len(members), 'module_ids': list(gate.module_ids), 'modules': [item.to_dict() for item in members], 'blocker_count': len(blockers), 'blockers': blockers, 'next_steps': next_steps})
    return gates


def blueprint_progress_summary() -> dict[str, Any]:
    rows = build_blueprint_progress_snapshot()
    overall = round(sum(item.percent_complete for item in rows) / max(len(rows), 1), 1)
    by_plane: dict[str, list[int]] = {}
    status_counts: dict[str, int] = {}
    for item in rows:
        by_plane.setdefault(item.plane, []).append(item.percent_complete)
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
    weakest_modules = [item.to_dict() for item in sorted(rows, key=lambda item: item.percent_complete)[:5]]
    release_gates = build_release_gate_snapshot()
    return {'overall_percent': overall, 'module_count': len(rows), 'by_plane': {plane: round(sum(vals) / len(vals), 1) for plane, vals in sorted(by_plane.items())}, 'status_counts': status_counts, 'weakest_modules': weakest_modules, 'release_gates': release_gates, 'release_gate_summary': {item['title']: item['percent_complete'] for item in release_gates}}


def render_blueprint_progress_markdown(*, title: str = 'Blueprint Progress Snapshot') -> str:
    rows = build_blueprint_progress_snapshot()
    summary = blueprint_progress_summary()
    lines = [f'# {title}', '', f"- Overall progress: **{summary['overall_percent']}%**", f"- Modules tracked: **{summary['module_count']}**", '', '## Plane summary', '']
    for plane, percent in summary['by_plane'].items():
        lines.append(f'- **{plane}**: {percent}%')
    lines.extend(['', '## Release gates', ''])
    for gate in summary['release_gates']:
        lines.append(f"- **{gate['title']}**: {gate['percent_complete']}% ({gate['status']})")
        if gate.get('blockers'):
            lines.append(f"  - blockers: {'; '.join(gate['blockers'][:3])}")
    lines.extend(['', '## Module matrix', '', '| Plane | Module | Progress | Status | Evidence | Missing evidence |', '| --- | --- | ---: | --- | --- | --- |'])
    for item in rows:
        lines.append(f"| {item.plane} | {item.title} | {item.percent_complete}% | {item.status} | {', '.join(item.evidence) or '-'} | {', '.join(item.missing_evidence) or '-'} |")
    return '\n'.join(lines) + '\n'


__all__ = ['BlueprintModuleProgress', 'BlueprintReleaseGate', 'build_blueprint_progress_snapshot', 'build_release_gate_snapshot', 'blueprint_progress_summary', 'render_blueprint_progress_markdown']
