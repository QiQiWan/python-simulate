from __future__ import annotations

"""GeoAI SimKit 1.2.4 Basic workflow.

1.2.4 extends the 1.1.3 nonlinear/hydro/contact foundation-pit workflow with
an auditable global Mohr-Coulomb Newton tangent path, Gmsh/OCC physical-group
exchange, consolidation coupling, interface open/close iteration and a fixed
six-phase GUI launcher contract.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.app.panels.result_viewer import build_result_viewer, export_legacy_vtk, export_result_summary_json
from geoai_simkit.examples.release_1_1_3_workflow import build_release_1_1_3_project
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.consolidation_coupling import apply_consolidation_coupling
from geoai_simkit.services.engineering_report import build_engineering_report_payload, export_engineering_report
from geoai_simkit.services.global_mohr_coulomb_newton import run_global_mohr_coulomb_newton_solve
from geoai_simkit.services.gmsh_occ_native_exchange import export_import_gmsh_occ_physical_groups
from geoai_simkit.services.gui_interaction_recording import record_phase_workbench_interaction_contract
from geoai_simkit.services.interface_contact_iteration import run_interface_contact_open_close_iteration
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.release_acceptance_124 import audit_release_1_2_4


@dataclass(slots=True)
class Release124WorkflowArtifacts:
    contract: str = "geoai_simkit_release_1_2_4_artifacts_v1"
    project_path: str = ""
    validation_path: str = ""
    gui_recording_path: str = ""
    compiler_path: str = ""
    newton_summary_path: str = ""
    acceptance_path: str = ""
    gmsh_exchange_path: str = ""
    consolidation_path: str = ""
    interface_iteration_path: str = ""
    result_viewer_path: str = ""
    result_export_path: str = ""
    vtk_path: str = ""
    report_markdown_path: str = ""
    report_json_path: str = ""
    tutorial_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "project_path": self.project_path,
            "validation_path": self.validation_path,
            "gui_recording_path": self.gui_recording_path,
            "compiler_path": self.compiler_path,
            "newton_summary_path": self.newton_summary_path,
            "acceptance_path": self.acceptance_path,
            "gmsh_exchange_path": self.gmsh_exchange_path,
            "consolidation_path": self.consolidation_path,
            "interface_iteration_path": self.interface_iteration_path,
            "result_viewer_path": self.result_viewer_path,
            "result_export_path": self.result_export_path,
            "vtk_path": self.vtk_path,
            "report_markdown_path": self.report_markdown_path,
            "report_json_path": self.report_json_path,
            "tutorial_path": self.tutorial_path,
            "metadata": dict(self.metadata),
        }


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def render_release_1_2_4_tutorial(project: GeoProjectDocument, acceptance: dict[str, Any]) -> str:
    return "\n".join([
        "# GeoAI SimKit 1.2.4 Basic Tutorial",
        "",
        "## What changed",
        "1. The desktop launcher now opens the six-phase workbench by default, even without PyVista.",
        "2. The Solve phase records a global Newton-Raphson Mohr-Coulomb consistent-tangent path.",
        "3. The Mesh phase exports/imports a Gmsh/OCC physical-group manifest for native exchange auditing.",
        "4. Hydro-mechanical results include consolidation and excess pore-pressure dissipation.",
        "5. Interfaces include open/closed/sliding iteration fields per phase.",
        "",
        "## Six-phase workflow",
        "地质 → 结构 → 网格 → 阶段配置 → 求解 → 结果查看",
        "",
        "## Acceptance",
        f"- Project: `{project.project_settings.name}`",
        f"- Release: `{project.metadata.get('release', '')}`",
        f"- Phases: `{', '.join(project.phase_ids())}`",
        f"- Status: `{acceptance.get('status', 'unknown')}`",
        f"- Accepted: `{acceptance.get('accepted', False)}`",
        "",
        "## Boundary of use",
        "1.2.4-basic is an auditable advanced workflow build.  It is not a certified commercial geotechnical solver.  Native Gmsh and desktop GUI verification should be run on the target workstation before engineering sign-off.",
        "",
    ])


def build_release_1_2_4_project(*, name: str = "GeoAI SimKit 1.2.4 Basic Foundation Pit", exchange_dir: str | Path | None = None) -> tuple[GeoProjectDocument, dict[str, Any]]:
    project, build113 = build_release_1_1_3_project(name=name)
    project.project_settings.metadata.update({"release": "1.2.4-basic", "workflow": "foundation_pit_global_newton_consolidation_contact"})
    project.metadata["release"] = "1.2.4-basic"
    project.metadata["release_line"] = "1.2.x"
    exchange_root = Path(exchange_dir) if exchange_dir is not None else Path.cwd() / "exports" / "release_1_2_4_exchange"
    gmsh_exchange = export_import_gmsh_occ_physical_groups(project, exchange_root)
    newton = run_global_mohr_coulomb_newton_solve(project, max_iterations=16, tolerance=1.0e-6, write_results=True)
    consolidation = apply_consolidation_coupling(project, write_results=True)
    interface_iteration = run_interface_contact_open_close_iteration(project, write_results=True)
    gui_recording = record_phase_workbench_interaction_contract()
    for phase_id in project.phase_ids():
        project.refresh_phase_snapshot(phase_id)
    build = {
        "contract": "geoai_simkit_release_1_2_4_build_v1",
        "status": "model_built",
        "release_1_1_3": build113,
        "global_newton": newton.to_dict(),
        "gmsh_exchange": gmsh_exchange.to_dict(),
        "consolidation": consolidation.to_dict(),
        "interface_iteration": interface_iteration.to_dict(),
        "gui_recording": gui_recording.to_dict(),
    }
    project.metadata["release_1_2_4_build"] = build
    return project, build


def export_release_1_2_4_bundle(
    project: GeoProjectDocument,
    output_dir: str | Path,
    *,
    validation: dict[str, Any] | None = None,
    gui_recording: dict[str, Any] | None = None,
    compiler: dict[str, Any] | None = None,
    newton_summary: dict[str, Any] | None = None,
    acceptance: dict[str, Any] | None = None,
    viewer: dict[str, Any] | None = None,
) -> Release124WorkflowArtifacts:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    validation_payload = validation or validate_geoproject_model(project, require_mesh=True, require_results=True).to_dict()
    gui_payload = gui_recording or record_phase_workbench_interaction_contract().to_dict()
    compiler_payload = compiler or compile_phase_solver_inputs(project, block_on_errors=False).to_dict()
    newton_payload = newton_summary or dict(project.solver_model.metadata.get("last_global_mohr_coulomb_newton_solve", {}) or {})
    gmsh_payload = dict(project.mesh_model.metadata.get("last_gmsh_occ_native_exchange", {}) or {})
    consolidation_payload = dict(project.solver_model.metadata.get("consolidation_coupling_state", {}) or {})
    interface_payload = dict(project.solver_model.metadata.get("interface_contact_iteration", {}) or {})
    acceptance_payload = acceptance or audit_release_1_2_4(project, newton_summary=newton_payload).to_dict()
    viewer_payload = viewer or build_result_viewer(project)
    tutorial_path = root / "release_1_2_4_tutorial.md"
    tutorial_path.write_text(render_release_1_2_4_tutorial(project, acceptance_payload), encoding="utf-8")
    acceptance_payload = audit_release_1_2_4(project, newton_summary=newton_payload, tutorial_path=tutorial_path).to_dict()
    report_payload = build_engineering_report_payload(project, acceptance=acceptance_payload, solver_summary=newton_payload, compiler=compiler_payload, validation=validation_payload)
    report_payload["release_1_2_4"] = {"gui_recording": gui_payload, "gmsh_exchange": gmsh_payload, "consolidation": consolidation_payload, "interface_iteration": interface_payload}

    project_path = project.save_json(root / "release_1_2_4_project.geoproject.json")
    validation_path = _write_json(root / "release_1_2_4_validation.json", validation_payload)
    gui_path = _write_json(root / "release_1_2_4_gui_recording.json", gui_payload)
    compiler_path = _write_json(root / "release_1_2_4_compiler.json", compiler_payload)
    newton_path = _write_json(root / "release_1_2_4_global_newton.json", newton_payload)
    acceptance_path = _write_json(root / "release_1_2_4_acceptance.json", acceptance_payload)
    gmsh_path = _write_json(root / "release_1_2_4_gmsh_exchange.json", gmsh_payload)
    consolidation_path = _write_json(root / "release_1_2_4_consolidation.json", consolidation_payload)
    interface_path = _write_json(root / "release_1_2_4_interface_iteration.json", interface_payload)
    viewer_path = _write_json(root / "release_1_2_4_result_viewer.json", viewer_payload)
    result_export = export_result_summary_json(project, root / "release_1_2_4_result_summary_export.json")
    vtk = export_legacy_vtk(project, root / "release_1_2_4_results.vtk")
    report_artifacts = export_engineering_report(root, report_payload, stem="release_1_2_4_engineering_report")
    return Release124WorkflowArtifacts(project_path=str(project_path), validation_path=validation_path, gui_recording_path=gui_path, compiler_path=compiler_path, newton_summary_path=newton_path, acceptance_path=acceptance_path, gmsh_exchange_path=gmsh_path, consolidation_path=consolidation_path, interface_iteration_path=interface_path, result_viewer_path=viewer_path, result_export_path=str(result_export.get("path", root / "release_1_2_4_result_summary_export.json")), vtk_path=str(vtk["path"]), report_markdown_path=report_artifacts.markdown_path, report_json_path=report_artifacts.json_path, tutorial_path=str(tutorial_path), metadata={"phase_count": len(project.phase_ids()), "result_phase_count": len(project.result_store.phase_results)})


def run_release_1_2_4_workflow(*, output_dir: str | Path | None = None) -> dict[str, Any]:
    exchange_dir = None if output_dir is None else Path(output_dir) / "gmsh_exchange"
    project, build = build_release_1_2_4_project(exchange_dir=exchange_dir)
    validation = validate_geoproject_model(project, require_mesh=True, require_results=True)
    gui = record_phase_workbench_interaction_contract()
    compiler = compile_phase_solver_inputs(project, block_on_errors=True)
    newton = dict(project.solver_model.metadata.get("last_global_mohr_coulomb_newton_solve", {}) or {})
    viewer = build_result_viewer(project)
    acceptance = audit_release_1_2_4(project, newton_summary=newton)
    artifacts = None
    if output_dir is not None:
        artifacts = export_release_1_2_4_bundle(project, output_dir, validation=validation.to_dict(), gui_recording=gui.to_dict(), compiler=compiler.to_dict(), newton_summary=newton, acceptance=acceptance.to_dict(), viewer=viewer)
        acceptance = audit_release_1_2_4(project, newton_summary=newton, tutorial_path=artifacts.tutorial_path)
    return {"contract": "geoai_simkit_release_1_2_4_workflow_v1", "ok": bool(acceptance.accepted), "project": project, "build": build, "validation": validation.to_dict(), "gui_recording": gui.to_dict(), "compiler": compiler.to_dict(), "newton_summary": newton, "gmsh_exchange": dict(project.mesh_model.metadata.get("last_gmsh_occ_native_exchange", {}) or {}), "consolidation": dict(project.solver_model.metadata.get("consolidation_coupling_state", {}) or {}), "interface_iteration": dict(project.solver_model.metadata.get("interface_contact_iteration", {}) or {}), "viewer": viewer, "acceptance": acceptance.to_dict(), "artifacts": None if artifacts is None else artifacts.to_dict()}


__all__ = ["Release124WorkflowArtifacts", "build_release_1_2_4_project", "run_release_1_2_4_workflow", "export_release_1_2_4_bundle"]
