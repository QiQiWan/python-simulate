from __future__ import annotations

"""Auditable one-click demo pipeline summaries for the 1.3.0 beta workbench."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DemoPipelineStep:
    key: str
    label: str
    phase: str
    status: str = "pending"
    message: str = ""
    artifact_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "phase": self.phase,
            "status": self.status,
            "message": self.message,
            "artifact_key": self.artifact_key,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class DemoPipelineReport:
    contract: str = "geoai_simkit_demo_complete_calculation_pipeline_v1"
    ok: bool = False
    demo_id: str = "foundation_pit_3d_beta"
    steps: list[DemoPipelineStep] = field(default_factory=list)
    artifact_count: int = 0
    output_dir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "demo_id": self.demo_id,
            "steps": [row.to_dict() for row in self.steps],
            "artifact_count": int(self.artifact_count),
            "output_dir": self.output_dir,
            "metadata": dict(self.metadata),
        }


def _exists(path: Any) -> bool:
    if path is None:
        return False
    if isinstance(path, (dict, list, tuple, set)):
        return False
    if str(path) == "":
        return False
    try:
        return Path(str(path)).exists()
    except Exception:
        return False


def build_demo_pipeline_report(project: Any, *, artifacts: dict[str, Any] | None = None, output_dir: str | Path | None = None) -> DemoPipelineReport:
    """Build a six-phase completion report for the built-in one-click demo."""

    artifacts = dict(artifacts or {})
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    compiler = dict(getattr(getattr(project, "solver_model", None), "metadata", {}).get("last_phase_solver_compiler", {}) or {})
    newton = dict(getattr(getattr(project, "solver_model", None), "metadata", {}).get("last_global_mohr_coulomb_newton_solve", {}) or {})
    consolidation = dict(getattr(getattr(project, "solver_model", None), "metadata", {}).get("consolidation_coupling_state", {}) or {})
    interface_iteration = dict(getattr(getattr(project, "solver_model", None), "metadata", {}).get("interface_contact_iteration", {}) or {})
    result_store = getattr(project, "result_store", None)
    phase_count = len(project.phase_ids()) if hasattr(project, "phase_ids") else 0
    result_phase_count = len(getattr(result_store, "phase_results", {}) or {})
    steps = [
        DemoPipelineStep(
            key="load_demo",
            label="一键加载三维基坑 Demo",
            phase="geology",
            status="done",
            message="Demo project document was created and bound to the phase workbench.",
            metadata={"project_name": getattr(getattr(project, "project_settings", None), "name", ""), "release": getattr(project, "metadata", {}).get("release", "")},
        ),
        DemoPipelineStep(
            key="geology_structure",
            label="生成地质体、开挖体、支护墙和支撑",
            phase="geology/structures",
            status="done" if getattr(project, "geometry_model", None) is not None and getattr(project, "structure_model", None) is not None else "blocked",
            message="Geology and structural semantic objects are available.",
            metadata={
                "volume_count": len(getattr(getattr(project, "geometry_model", None), "volumes", {}) or {}),
                "plate_count": len(getattr(getattr(project, "structure_model", None), "plates", {}) or {}),
                "beam_count": len(getattr(getattr(project, "structure_model", None), "beams", {}) or {}),
                "anchor_count": len(getattr(getattr(project, "structure_model", None), "anchors", {}) or {}),
            },
        ),
        DemoPipelineStep(
            key="mesh",
            label="生成 Tet4 网格与物理组标签",
            phase="mesh",
            status="done" if mesh is not None and bool(getattr(mesh, "cell_count", 0)) else "blocked",
            message="Project mesh is ready for phase compilation.",
            metadata={
                "node_count": 0 if mesh is None else int(getattr(mesh, "node_count", 0) or 0),
                "cell_count": 0 if mesh is None else int(getattr(mesh, "cell_count", 0) or 0),
                "cell_types": [] if mesh is None else sorted({str(v) for v in list(getattr(mesh, "cell_types", []) or [])}),
            },
        ),
        DemoPipelineStep(
            key="compile",
            label="编译阶段施工求解输入",
            phase="staging",
            status="done" if compiler.get("ok", True) and phase_count > 0 else "blocked",
            message="Phase snapshots were compiled into compact active meshes.",
            artifact_key="compiler_path",
            metadata={"phase_count": phase_count, "compiled_phase_count": len(getattr(getattr(project, "solver_model", None), "compiled_phase_models", {}) or {})},
        ),
        DemoPipelineStep(
            key="solve",
            label="运行全局 Mohr-Coulomb Newton 求解",
            phase="solve",
            status="done" if newton.get("accepted", False) else "blocked",
            message="Global nonlinear solve finished and wrote phase results.",
            artifact_key="global_newton_path",
            metadata={"accepted": bool(newton.get("accepted", False)), "iteration_count": int(newton.get("iteration_count", 0) or 0), "residual": float(newton.get("residual_norm_final", 0.0) or 0.0)},
        ),
        DemoPipelineStep(
            key="hydro_contact",
            label="运行固结耦合与界面开闭合迭代",
            phase="solve/results",
            status="done" if consolidation.get("ok", False) and interface_iteration.get("ok", False) else "blocked",
            message="Pore-pressure, consolidation and contact-state fields are available.",
            artifact_key="consolidation_path",
            metadata={"consolidation_ok": bool(consolidation.get("ok", False)), "interface_ok": bool(interface_iteration.get("ok", False))},
        ),
        DemoPipelineStep(
            key="results_export",
            label="生成结果查看、VTK、JSON 和工程报告",
            phase="results",
            status="done" if result_phase_count >= phase_count and any(_exists(artifacts.get(k)) for k in ("vtk_path", "report_markdown_path", "project_path")) else "blocked",
            message="Result viewer payload and export artifacts are ready.",
            artifact_key="vtk_path",
            metadata={"phase_count": phase_count, "result_phase_count": result_phase_count, "exported_artifacts": sorted(k for k, v in artifacts.items() if _exists(v))},
        ),
    ]
    ok = all(row.status == "done" for row in steps)
    return DemoPipelineReport(
        ok=ok,
        steps=steps,
        artifact_count=sum(1 for value in artifacts.values() if _exists(value)),
        output_dir="" if output_dir is None else str(output_dir),
        metadata={"phase_count": phase_count, "result_phase_count": result_phase_count},
    )


__all__ = ["DemoPipelineStep", "DemoPipelineReport", "build_demo_pipeline_report"]
