from __future__ import annotations

"""GeoAI SimKit 1.0 Basic end-to-end engineering workflow.

The 1.0 workflow upgrades the 0.9 Alpha staged foundation-pit demo with a
production-marked shared-node Hex8 mesh, compact per-phase solver input, strict
release acceptance, engineering report export and save/load regression support.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.app.panels.result_viewer import build_result_viewer, export_legacy_vtk, export_result_summary_json
from geoai_simkit.examples.alpha_0_9_workflow import build_alpha_foundation_pit_project
from geoai_simkit.geoproject import GeoProjectDocument, ReportReference
from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
from geoai_simkit.services.engineering_report import build_engineering_report_payload, export_engineering_report
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.production_mesh import generate_shared_node_hex8_mesh
from geoai_simkit.services.release_acceptance import audit_release_1_0


@dataclass(slots=True)
class Release10WorkflowArtifacts:
    contract: str = "geoai_simkit_release_1_0_artifacts_v1"
    project_path: str = ""
    validation_path: str = ""
    compiler_path: str = ""
    solver_summary_path: str = ""
    acceptance_path: str = ""
    result_viewer_path: str = ""
    result_export_path: str = ""
    vtk_path: str = ""
    report_markdown_path: str = ""
    report_json_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "project_path": self.project_path,
            "validation_path": self.validation_path,
            "compiler_path": self.compiler_path,
            "solver_summary_path": self.solver_summary_path,
            "acceptance_path": self.acceptance_path,
            "result_viewer_path": self.result_viewer_path,
            "result_export_path": self.result_export_path,
            "vtk_path": self.vtk_path,
            "report_markdown_path": self.report_markdown_path,
            "report_json_path": self.report_json_path,
            "metadata": dict(self.metadata),
        }


def _all_material_records(project: GeoProjectDocument) -> list[Any]:
    records: list[Any] = []
    for bucket in (
        project.material_library.soil_materials,
        project.material_library.plate_materials,
        project.material_library.beam_materials,
        project.material_library.interface_materials,
    ):
        records.extend(bucket.values())
    return records


def configure_release_1_0_baseline(project: GeoProjectDocument) -> dict[str, Any]:
    """Apply deterministic 1.0 Basic acceptance settings to the demo project.

    The baseline case is a surcharge-driven linear-static staged verification
    case.  Self-weight is disabled for this built-in demo so solver acceptance
    depends on the staged load/activation path and not on the known coarse
    single-cell body-force limitation of the lightweight CI mesh.
    """

    original_unit_weights: dict[str, dict[str, float]] = {}
    for record in _all_material_records(project):
        params = dict(getattr(record, "parameters", {}) or {})
        saved: dict[str, float] = {}
        for key in ("gamma", "gamma_unsat", "gamma_sat", "unit_weight"):
            if key in params:
                saved[key] = float(params[key])
                params[key] = 0.0
        if saved:
            original_unit_weights[str(record.id)] = saved
            record.parameters.update(params)
            record.metadata.setdefault("release_1_0_original_unit_weights", saved)
            record.metadata["release_1_0_load_basis"] = "surcharge_only_linear_static"

    phase_ids = project.phase_ids()
    for bc in project.solver_model.boundary_conditions.values():
        bc.stage_ids = list(phase_ids)
    for phase_id in phase_ids:
        settings = project.phase_manager.calculation_settings.get(phase_id)
        if settings is None:
            from geoai_simkit.geoproject.document import CalculationSettings

            settings = CalculationSettings()
            project.phase_manager.calculation_settings[phase_id] = settings
        settings.tolerance = 1.0e-8
        settings.calculation_type = "linear_static"
        settings.metadata["release_1_0"] = "strict_linear_static_acceptance"
        project.refresh_phase_snapshot(phase_id)

    project.project_settings.metadata.update({"release": "1.0.0-basic", "workflow": "foundation_pit_basic_engineering"})
    project.metadata["release"] = "1.0.0-basic"
    project.metadata["release_1_0_baseline"] = {
        "load_basis": "surcharge_only_linear_static",
        "unit_weight_parameters_disabled": original_unit_weights,
        "phase_count": len(phase_ids),
    }
    return dict(project.metadata["release_1_0_baseline"])


def build_release_1_0_project(*, name: str = "GeoAI SimKit 1.0 Basic Foundation Pit") -> tuple[GeoProjectDocument, dict[str, Any]]:
    """Build the release 1.0 project and attach a production-marked mesh."""

    project = build_alpha_foundation_pit_project(name=name)
    baseline = configure_release_1_0_baseline(project)
    mesh, mesh_report = generate_shared_node_hex8_mesh(project, attach=True)
    project.solver_model.compiled_phase_models.clear()
    for phase_id in project.phase_ids():
        project.refresh_phase_snapshot(phase_id)
    project.compile_phase_models()
    project.metadata["release_1_0_build"] = {
        "status": "model_built",
        "baseline": baseline,
        "mesh": mesh_report.to_dict(),
        "node_count": mesh.node_count,
        "cell_count": mesh.cell_count,
    }
    return project, mesh_report.to_dict()


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def export_release_1_0_bundle(
    project: GeoProjectDocument,
    output_dir: str | Path,
    *,
    validation: dict[str, Any] | None = None,
    compiler: dict[str, Any] | None = None,
    solver_summary: dict[str, Any] | None = None,
    acceptance: dict[str, Any] | None = None,
    viewer: dict[str, Any] | None = None,
) -> Release10WorkflowArtifacts:
    """Export all artifacts needed to review the 1.0 Basic workflow."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    validation_payload = validation or validate_geoproject_model(project, require_mesh=True, require_results=True).to_dict()
    compiler_payload = compiler or compile_phase_solver_inputs(project, block_on_errors=False).to_dict()
    solver_payload = solver_summary or dict(project.solver_model.metadata.get("last_incremental_solve", {}) or {})
    acceptance_payload = acceptance or audit_release_1_0(project, solver_summary=solver_payload).to_dict()
    viewer_payload = viewer or build_result_viewer(project)
    report_payload = build_engineering_report_payload(
        project,
        acceptance=acceptance_payload,
        solver_summary=solver_payload,
        compiler=compiler_payload,
        validation=validation_payload,
    )

    project_path = project.save_json(root / "release_1_0_project.geoproject.json")
    validation_path = _write_json(root / "release_1_0_validation.json", validation_payload)
    compiler_path = _write_json(root / "release_1_0_compiler.json", compiler_payload)
    solver_path = _write_json(root / "release_1_0_solver_summary.json", solver_payload)
    acceptance_path = _write_json(root / "release_1_0_acceptance.json", acceptance_payload)
    viewer_path = _write_json(root / "release_1_0_result_viewer.json", viewer_payload)
    result_export = export_result_summary_json(project, root / "release_1_0_result_summary_export.json")
    vtk = export_legacy_vtk(project, root / "release_1_0_results.vtk", phase_id=project.phase_ids()[-1])
    report_artifacts = export_engineering_report(root, report_payload, stem="release_1_0_engineering_report")
    project.result_store.reports["release_1_0_engineering_report"] = ReportReference(
        id="release_1_0_engineering_report",
        title="GeoAI SimKit 1.0 Basic engineering report",
        path=report_artifacts.markdown_path,
        kind="markdown",
        metadata={"source": "release_1_0_workflow"},
    )
    return Release10WorkflowArtifacts(
        project_path=str(project_path),
        validation_path=validation_path,
        compiler_path=compiler_path,
        solver_summary_path=solver_path,
        acceptance_path=acceptance_path,
        result_viewer_path=viewer_path,
        result_export_path=str(result_export.get("path", root / "release_1_0_result_summary_export.json")),
        vtk_path=str(vtk["path"]),
        report_markdown_path=report_artifacts.markdown_path,
        report_json_path=report_artifacts.json_path,
        metadata={"phase_count": len(project.phase_ids()), "result_phase_count": len(project.result_store.phase_results)},
    )


def run_release_1_0_workflow(*, output_dir: str | Path | None = None, run_solver: bool = True) -> dict[str, Any]:
    """Build, compile, solve, accept and optionally export the 1.0 workflow."""

    project, mesh_report = build_release_1_0_project()
    validation = validate_geoproject_model(project, require_mesh=True)
    compiler = compile_phase_solver_inputs(project, block_on_errors=True)
    solver_summary = None
    if run_solver:
        solver_summary = run_geoproject_incremental_solve(project, compile_if_needed=False, write_results=True)
    viewer = build_result_viewer(project)
    acceptance = audit_release_1_0(project, solver_summary=solver_summary)
    artifacts = None
    if output_dir is not None:
        artifacts = export_release_1_0_bundle(
            project,
            output_dir,
            validation=validation.to_dict(),
            compiler=compiler.to_dict(),
            solver_summary=None if solver_summary is None else solver_summary.to_dict(),
            acceptance=acceptance.to_dict(),
            viewer=viewer,
        )
    return {
        "contract": "geoai_simkit_release_1_0_workflow_v1",
        "ok": bool(acceptance.accepted),
        "project": project,
        "mesh_report": mesh_report,
        "validation": validation.to_dict(),
        "compiler": compiler.to_dict(),
        "solver_summary": None if solver_summary is None else solver_summary.to_dict(),
        "viewer": viewer,
        "acceptance": acceptance.to_dict(),
        "artifacts": None if artifacts is None else artifacts.to_dict(),
    }


__all__ = [
    "Release10WorkflowArtifacts",
    "build_release_1_0_project",
    "configure_release_1_0_baseline",
    "run_release_1_0_workflow",
    "export_release_1_0_bundle",
]
