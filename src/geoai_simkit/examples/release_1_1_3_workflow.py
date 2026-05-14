from __future__ import annotations

"""GeoAI SimKit 1.1.3 Basic end-to-end workflow."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.app.panels.result_viewer import build_result_viewer, export_legacy_vtk, export_result_summary_json
from geoai_simkit.examples.release_1_0_5_workflow import build_release_1_0_5_project
from geoai_simkit.geoproject import GeoProjectDocument, ReportReference
from geoai_simkit.services.contact_interface_enhancement import configure_wall_soil_contact_interfaces
from geoai_simkit.services.engineering_report import build_engineering_report_payload, export_engineering_report
from geoai_simkit.services.gmsh_occ_project_mesher import generate_geoproject_gmsh_occ_tet4_mesh
from geoai_simkit.services.gui_interaction_hardening import audit_gui_interaction_hardening
from geoai_simkit.services.hydro_mechanical import apply_pore_pressure_results
from geoai_simkit.services.k0_initialization import apply_k0_initial_stress
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.nonlinear_mohr_coulomb_solver import run_staged_mohr_coulomb_solve
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.release_acceptance_113 import audit_release_1_1_3
from geoai_simkit.services.staged_mohr_coulomb import configure_staged_mohr_coulomb_controls


@dataclass(slots=True)
class Release113WorkflowArtifacts:
    contract: str = "geoai_simkit_release_1_1_3_artifacts_v1"
    project_path: str = ""
    validation_path: str = ""
    gui_interaction_path: str = ""
    compiler_path: str = ""
    solver_summary_path: str = ""
    acceptance_path: str = ""
    gmsh_occ_mesh_path: str = ""
    hydro_path: str = ""
    contact_path: str = ""
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
            "gui_interaction_path": self.gui_interaction_path,
            "compiler_path": self.compiler_path,
            "solver_summary_path": self.solver_summary_path,
            "acceptance_path": self.acceptance_path,
            "gmsh_occ_mesh_path": self.gmsh_occ_mesh_path,
            "hydro_path": self.hydro_path,
            "contact_path": self.contact_path,
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


def render_release_1_1_3_tutorial(project: GeoProjectDocument, acceptance: dict[str, Any]) -> str:
    mesh = project.mesh_model.mesh_document
    mesh_meta = dict(mesh.metadata or {}) if mesh is not None else {}
    return "\n".join(
        [
            "# GeoAI SimKit 1.1.3 Basic Tutorial",
            "",
            "## Purpose",
            "This tutorial reviews the 1.1.3 workflow additions: Tet4 Gmsh/OCC project-mesh contract, staged Mohr-Coulomb nonlinear correction, GUI interaction hardening, groundwater/pore pressure fields and contact interface state.",
            "",
            "## Workflow",
            "1. Open the six-phase workbench and load the 1.1.3 demonstration project.",
            "2. Inspect geology/structure entities and the generated wall-soil interfaces.",
            "3. Open the Mesh phase and verify the Tet4 physical-volume tags.",
            "4. Open the Staging phase and review water condition drawdown per phase.",
            "5. Open the Solve phase and inspect staged Mohr-Coulomb nonlinear records.",
            "6. Open the Results phase and review plastic points, pore pressure, effective stress and interface force fields.",
            "",
            "## Demonstration project",
            f"- Project: `{project.project_settings.name}`",
            f"- Release: `{project.metadata.get('release', '')}`",
            f"- Phases: `{', '.join(project.phase_ids())}`",
            f"- Mesh cells: `{0 if mesh is None else mesh.cell_count}`",
            f"- Mesh backend: `{mesh_meta.get('selected_backend', mesh_meta.get('mesher', ''))}`",
            f"- Acceptance status: `{acceptance.get('status', 'unknown')}`",
            "",
            "## Boundary of use",
            "1.1.3-basic is an auditable engineering workflow build.  It has a real Tet4 compiler contract, pore-pressure fields and Mohr-Coulomb return-map state, but remains below certified commercial geotechnical solver status.",
            "",
        ]
    )


def build_release_1_1_3_project(*, name: str = "GeoAI SimKit 1.1.3 Basic Foundation Pit") -> tuple[GeoProjectDocument, dict[str, Any]]:
    project, _ = build_release_1_0_5_project(name=name)
    project.project_settings.metadata.update({"release": "1.1.3-basic", "workflow": "foundation_pit_nonlinear_hydro_contact"})
    project.metadata["release"] = "1.1.3-basic"
    project.metadata["release_line"] = "1.1.x"
    contact = configure_wall_soil_contact_interfaces(project)
    mesh, mesh_route = generate_geoproject_gmsh_occ_tet4_mesh(project, attach=True)
    k0 = apply_k0_initial_stress(project, ground_level=0.0, default_unit_weight=18.0)
    mc_control = configure_staged_mohr_coulomb_controls(project, control_mode="nonlinear_return_mapping", max_iterations=25, tolerance=1.0e-6)
    gui_interaction = audit_gui_interaction_hardening()
    project.solver_model.compiled_phase_models.clear()
    for phase_id in project.phase_ids():
        project.refresh_phase_snapshot(phase_id)
    project.compile_phase_models()
    build = {
        "contract": "geoai_simkit_release_1_1_3_build_v1",
        "status": "model_built",
        "mesh_route": mesh_route.to_dict(),
        "k0": k0.to_dict(),
        "mohr_coulomb_control": mc_control.to_dict(),
        "gui_interaction": gui_interaction.to_dict(),
        "contact": contact.to_dict(),
        "node_count": mesh.node_count,
        "cell_count": mesh.cell_count,
    }
    project.metadata["release_1_1_3_build"] = build
    return project, build


def export_release_1_1_3_bundle(
    project: GeoProjectDocument,
    output_dir: str | Path,
    *,
    validation: dict[str, Any] | None = None,
    gui_interaction: dict[str, Any] | None = None,
    compiler: dict[str, Any] | None = None,
    solver_summary: dict[str, Any] | None = None,
    acceptance: dict[str, Any] | None = None,
    viewer: dict[str, Any] | None = None,
) -> Release113WorkflowArtifacts:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    validation_payload = validation or validate_geoproject_model(project, require_mesh=True, require_results=True).to_dict()
    gui_payload = gui_interaction or audit_gui_interaction_hardening().to_dict()
    compiler_payload = compiler or compile_phase_solver_inputs(project, block_on_errors=False).to_dict()
    solver_payload = solver_summary or dict(project.solver_model.metadata.get("last_staged_mohr_coulomb_solve", {}) or {})
    mesh_payload = dict(project.mesh_model.metadata.get("last_gmsh_occ_project_mesh", {}) or {})
    hydro_payload = dict(project.solver_model.metadata.get("hydro_mechanical_state", {}) or {})
    contact_payload = dict(project.solver_model.metadata.get("contact_interface_enhancement", {}) or {})
    acceptance_payload = acceptance or audit_release_1_1_3(project, solver_summary=solver_payload).to_dict()
    viewer_payload = viewer or build_result_viewer(project)
    report_payload = build_engineering_report_payload(project, acceptance=acceptance_payload, solver_summary=solver_payload, compiler=compiler_payload, validation=validation_payload)
    report_payload["release_1_1_3"] = {"gui_interaction": gui_payload, "gmsh_occ_project_mesh": mesh_payload, "hydro": hydro_payload, "contact": contact_payload}
    tutorial_path = root / "release_1_1_3_tutorial.md"
    tutorial_path.write_text(render_release_1_1_3_tutorial(project, acceptance_payload), encoding="utf-8")
    acceptance_payload = audit_release_1_1_3(project, solver_summary=solver_payload, tutorial_path=tutorial_path).to_dict()
    report_payload["acceptance"] = acceptance_payload

    project_path = project.save_json(root / "release_1_1_3_project.geoproject.json")
    validation_path = _write_json(root / "release_1_1_3_validation.json", validation_payload)
    gui_path = _write_json(root / "release_1_1_3_gui_interaction.json", gui_payload)
    compiler_path = _write_json(root / "release_1_1_3_compiler.json", compiler_payload)
    solver_path = _write_json(root / "release_1_1_3_solver_summary.json", solver_payload)
    acceptance_path = _write_json(root / "release_1_1_3_acceptance.json", acceptance_payload)
    mesh_path = _write_json(root / "release_1_1_3_gmsh_occ_project_mesh.json", mesh_payload)
    hydro_path = _write_json(root / "release_1_1_3_hydro_mechanical.json", hydro_payload)
    contact_path = _write_json(root / "release_1_1_3_contact_interfaces.json", contact_payload)
    viewer_path = _write_json(root / "release_1_1_3_result_viewer.json", viewer_payload)
    result_export = export_result_summary_json(project, root / "release_1_1_3_result_summary_export.json")
    vtk = export_legacy_vtk(project, root / "release_1_1_3_results.vtk", phase_id=project.phase_ids()[-1])
    report_artifacts = export_engineering_report(root, report_payload, stem="release_1_1_3_engineering_report")
    project.result_store.reports["release_1_1_3_engineering_report"] = ReportReference(id="release_1_1_3_engineering_report", title="GeoAI SimKit 1.1.3 Basic engineering report", path=report_artifacts.markdown_path, kind="markdown", metadata={"source": "release_1_1_3_workflow"})
    return Release113WorkflowArtifacts(project_path=str(project_path), validation_path=validation_path, gui_interaction_path=gui_path, compiler_path=compiler_path, solver_summary_path=solver_path, acceptance_path=acceptance_path, gmsh_occ_mesh_path=mesh_path, hydro_path=hydro_path, contact_path=contact_path, result_viewer_path=viewer_path, result_export_path=str(result_export.get("path", root / "release_1_1_3_result_summary_export.json")), vtk_path=str(vtk["path"]), report_markdown_path=report_artifacts.markdown_path, report_json_path=report_artifacts.json_path, tutorial_path=str(tutorial_path), metadata={"phase_count": len(project.phase_ids()), "result_phase_count": len(project.result_store.phase_results)})


def run_release_1_1_3_workflow(*, output_dir: str | Path | None = None, run_solver: bool = True) -> dict[str, Any]:
    project, build = build_release_1_1_3_project()
    validation = validate_geoproject_model(project, require_mesh=True)
    gui = audit_gui_interaction_hardening()
    compiler = compile_phase_solver_inputs(project, block_on_errors=True)
    solver_summary = None
    hydro = None
    if run_solver:
        solver_summary = run_staged_mohr_coulomb_solve(project, compile_if_needed=False, write_results=True)
        hydro = apply_pore_pressure_results(project, gamma_water=9.81, write_results=True)
    viewer = build_result_viewer(project)
    acceptance = audit_release_1_1_3(project, solver_summary=solver_summary)
    artifacts = None
    if output_dir is not None:
        artifacts = export_release_1_1_3_bundle(project, output_dir, validation=validation.to_dict(), gui_interaction=gui.to_dict(), compiler=compiler.to_dict(), solver_summary=None if solver_summary is None else solver_summary.to_dict(), acceptance=acceptance.to_dict(), viewer=viewer)
        acceptance = audit_release_1_1_3(project, solver_summary=solver_summary, tutorial_path=artifacts.tutorial_path)
    return {"contract": "geoai_simkit_release_1_1_3_workflow_v1", "ok": bool(acceptance.accepted), "project": project, "build": build, "validation": validation.to_dict(), "gui_interaction": gui.to_dict(), "compiler": compiler.to_dict(), "solver_summary": None if solver_summary is None else solver_summary.to_dict(), "hydro": None if hydro is None else hydro.to_dict(), "viewer": viewer, "acceptance": acceptance.to_dict(), "artifacts": None if artifacts is None else artifacts.to_dict()}


__all__ = ["Release113WorkflowArtifacts", "build_release_1_1_3_project", "run_release_1_1_3_workflow", "export_release_1_1_3_bundle"]
