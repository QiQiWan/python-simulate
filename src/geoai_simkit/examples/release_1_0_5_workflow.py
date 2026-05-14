from __future__ import annotations

"""GeoAI SimKit 1.0.5 Basic workflow.

This release extends 1.0.0-basic with five hardening increments:

* 1.0.1 headless/desktop GUI contract hardening.
* 1.0.2 Gmsh/OCC-preferred production meshing route with explicit fallback.
* 1.0.3 K0/self-weight initial stress preparation.
* 1.0.4 staged Mohr-Coulomb control metadata.
* 1.0.5 engineering report templates, tutorial and release audit bundle.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.app.panels.result_viewer import build_result_viewer, export_legacy_vtk, export_result_summary_json
from geoai_simkit.examples.release_1_0_workflow import build_release_1_0_project
from geoai_simkit.geoproject import GeoProjectDocument, ReportReference
from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
from geoai_simkit.services.engineering_report import build_engineering_report_payload, export_engineering_report
from geoai_simkit.services.gui_desktop_hardening import audit_phase_workbench_desktop_contract
from geoai_simkit.services.k0_initialization import apply_k0_initial_stress
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.production_mesh import generate_gmsh_occ_or_shared_hex8_mesh
from geoai_simkit.services.release_acceptance_105 import audit_release_1_0_5
from geoai_simkit.services.staged_mohr_coulomb import configure_staged_mohr_coulomb_controls


@dataclass(slots=True)
class Release105WorkflowArtifacts:
    contract: str = "geoai_simkit_release_1_0_5_artifacts_v1"
    project_path: str = ""
    validation_path: str = ""
    gui_hardening_path: str = ""
    compiler_path: str = ""
    solver_summary_path: str = ""
    acceptance_path: str = ""
    k0_path: str = ""
    mohr_coulomb_path: str = ""
    mesh_route_path: str = ""
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
            "gui_hardening_path": self.gui_hardening_path,
            "compiler_path": self.compiler_path,
            "solver_summary_path": self.solver_summary_path,
            "acceptance_path": self.acceptance_path,
            "k0_path": self.k0_path,
            "mohr_coulomb_path": self.mohr_coulomb_path,
            "mesh_route_path": self.mesh_route_path,
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


def render_release_1_0_5_tutorial(project: GeoProjectDocument, acceptance: dict[str, Any]) -> str:
    phase_ids = project.phase_ids()
    mesh = project.mesh_model.mesh_document
    mesh_meta = dict(getattr(mesh, "metadata", {}) or {}) if mesh is not None else {}
    return "\n".join(
        [
            "# GeoAI SimKit 1.0.5 Basic Tutorial",
            "",
            "## Purpose",
            "This tutorial walks through the accepted 1.0.5 foundation-pit workflow: geology, structures, mesh, staged configuration, solve and results.",
            "",
            "## Workflow",
            "1. Open the six-phase workbench and start from the Geology phase.",
            "2. Review the demo soil volumes and material assignments.",
            "3. Switch to Structures to inspect walls and struts.",
            "4. Switch to Mesh and verify the Gmsh/OCC-preferred production mesh route.",
            "5. Switch to Staging and inspect excavation/support activation snapshots.",
            "6. Switch to Solve and review K0 initialization and staged Mohr-Coulomb controls.",
            "7. Switch to Results and export VTK, JSON and the engineering report.",
            "",
            "## Current demonstration project",
            f"- Project: `{project.project_settings.name}`",
            f"- Release: `{project.metadata.get('release', '')}`",
            f"- Phases: `{', '.join(phase_ids)}`",
            f"- Mesh cells: `{0 if mesh is None else mesh.cell_count}`",
            f"- Mesh backend: `{mesh_meta.get('selected_backend', mesh_meta.get('mesher', ''))}`",
            f"- Gmsh/OCC fallback used: `{mesh_meta.get('fallback_used', False)}`",
            f"- Acceptance status: `{acceptance.get('status', 'unknown')}`",
            "",
            "## Limitations",
            "The 1.0.5 Basic workflow has explicit K0 and staged Mohr-Coulomb control metadata, but the global solve remains the lightweight compact staged kernel. Treat the bundled result as a regression/engineering-demo result, not certification-grade design output.",
            "",
        ]
    )


def build_release_1_0_5_project(*, name: str = "GeoAI SimKit 1.0.5 Basic Foundation Pit") -> tuple[GeoProjectDocument, dict[str, Any]]:
    """Build a 1.0.5 project with hardened mesh, K0 and MC control metadata."""

    project, _ = build_release_1_0_project(name=name)
    project.project_settings.metadata.update({"release": "1.0.5-basic", "workflow": "foundation_pit_basic_engineering_hardened"})
    project.metadata["release"] = "1.0.5-basic"
    project.metadata["release_line"] = "1.0.x"
    mesh, mesh_route = generate_gmsh_occ_or_shared_hex8_mesh(project, attach=True)
    k0 = apply_k0_initial_stress(project, ground_level=0.0, default_unit_weight=18.0)
    mc = configure_staged_mohr_coulomb_controls(project)
    gui = audit_phase_workbench_desktop_contract()
    project.solver_model.compiled_phase_models.clear()
    for phase_id in project.phase_ids():
        project.refresh_phase_snapshot(phase_id)
    project.compile_phase_models()
    build = {
        "contract": "geoai_simkit_release_1_0_5_build_v1",
        "status": "model_built",
        "mesh_route": mesh_route.to_dict(),
        "k0": k0.to_dict(),
        "mohr_coulomb": mc.to_dict(),
        "gui": gui.to_dict(),
        "node_count": mesh.node_count,
        "cell_count": mesh.cell_count,
    }
    project.metadata["release_1_0_5_build"] = build
    return project, build


def export_release_1_0_5_bundle(
    project: GeoProjectDocument,
    output_dir: str | Path,
    *,
    validation: dict[str, Any] | None = None,
    gui: dict[str, Any] | None = None,
    compiler: dict[str, Any] | None = None,
    solver_summary: dict[str, Any] | None = None,
    acceptance: dict[str, Any] | None = None,
    viewer: dict[str, Any] | None = None,
) -> Release105WorkflowArtifacts:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    validation_payload = validation or validate_geoproject_model(project, require_mesh=True, require_results=True).to_dict()
    gui_payload = gui or audit_phase_workbench_desktop_contract().to_dict()
    compiler_payload = compiler or compile_phase_solver_inputs(project, block_on_errors=False).to_dict()
    solver_payload = solver_summary or dict(project.solver_model.metadata.get("last_incremental_solve", {}) or {})
    mesh_route_payload = dict(project.mesh_model.metadata.get("last_gmsh_occ_mesh_route", {}) or {})
    k0_payload = dict(project.solver_model.metadata.get("k0_initial_stress", {}) or {})
    mc_payload = dict(project.solver_model.metadata.get("staged_mohr_coulomb_control", {}) or {})
    acceptance_payload = acceptance or audit_release_1_0_5(project, solver_summary=solver_payload).to_dict()
    viewer_payload = viewer or build_result_viewer(project)
    report_payload = build_engineering_report_payload(
        project,
        acceptance=acceptance_payload,
        solver_summary=solver_payload,
        compiler=compiler_payload,
        validation=validation_payload,
    )
    report_payload["release_1_0_5"] = {"gui": gui_payload, "mesh_route": mesh_route_payload, "k0": k0_payload, "mohr_coulomb": mc_payload}

    tutorial_text = render_release_1_0_5_tutorial(project, acceptance_payload)
    tutorial_path = root / "release_1_0_5_tutorial.md"
    tutorial_path.write_text(tutorial_text, encoding="utf-8")
    # Re-audit with the tutorial path so the exported acceptance artifact records documentation readiness.
    acceptance_payload = audit_release_1_0_5(project, solver_summary=solver_payload, tutorial_path=tutorial_path).to_dict()
    report_payload["acceptance"] = acceptance_payload

    project_path = project.save_json(root / "release_1_0_5_project.geoproject.json")
    validation_path = _write_json(root / "release_1_0_5_validation.json", validation_payload)
    gui_path = _write_json(root / "release_1_0_5_gui_hardening.json", gui_payload)
    compiler_path = _write_json(root / "release_1_0_5_compiler.json", compiler_payload)
    solver_path = _write_json(root / "release_1_0_5_solver_summary.json", solver_payload)
    acceptance_path = _write_json(root / "release_1_0_5_acceptance.json", acceptance_payload)
    k0_path = _write_json(root / "release_1_0_5_k0_initial_stress.json", k0_payload)
    mc_path = _write_json(root / "release_1_0_5_mohr_coulomb_control.json", mc_payload)
    mesh_route_path = _write_json(root / "release_1_0_5_mesh_route.json", mesh_route_payload)
    viewer_path = _write_json(root / "release_1_0_5_result_viewer.json", viewer_payload)
    result_export = export_result_summary_json(project, root / "release_1_0_5_result_summary_export.json")
    vtk = export_legacy_vtk(project, root / "release_1_0_5_results.vtk", phase_id=project.phase_ids()[-1])
    report_artifacts = export_engineering_report(root, report_payload, stem="release_1_0_5_engineering_report")
    project.result_store.reports["release_1_0_5_engineering_report"] = ReportReference(
        id="release_1_0_5_engineering_report",
        title="GeoAI SimKit 1.0.5 Basic engineering report",
        path=report_artifacts.markdown_path,
        kind="markdown",
        metadata={"source": "release_1_0_5_workflow"},
    )
    return Release105WorkflowArtifacts(
        project_path=str(project_path),
        validation_path=validation_path,
        gui_hardening_path=gui_path,
        compiler_path=compiler_path,
        solver_summary_path=solver_path,
        acceptance_path=acceptance_path,
        k0_path=k0_path,
        mohr_coulomb_path=mc_path,
        mesh_route_path=mesh_route_path,
        result_viewer_path=viewer_path,
        result_export_path=str(result_export.get("path", root / "release_1_0_5_result_summary_export.json")),
        vtk_path=str(vtk["path"]),
        report_markdown_path=report_artifacts.markdown_path,
        report_json_path=report_artifacts.json_path,
        tutorial_path=str(tutorial_path),
        metadata={"phase_count": len(project.phase_ids()), "result_phase_count": len(project.result_store.phase_results)},
    )


def run_release_1_0_5_workflow(*, output_dir: str | Path | None = None, run_solver: bool = True) -> dict[str, Any]:
    project, build = build_release_1_0_5_project()
    validation = validate_geoproject_model(project, require_mesh=True)
    gui = audit_phase_workbench_desktop_contract()
    compiler = compile_phase_solver_inputs(project, block_on_errors=True)
    solver_summary = None
    if run_solver:
        solver_summary = run_geoproject_incremental_solve(project, compile_if_needed=False, write_results=True)
    viewer = build_result_viewer(project)
    acceptance = audit_release_1_0_5(project, solver_summary=solver_summary)
    artifacts = None
    if output_dir is not None:
        artifacts = export_release_1_0_5_bundle(
            project,
            output_dir,
            validation=validation.to_dict(),
            gui=gui.to_dict(),
            compiler=compiler.to_dict(),
            solver_summary=None if solver_summary is None else solver_summary.to_dict(),
            acceptance=acceptance.to_dict(),
            viewer=viewer,
        )
        acceptance = audit_release_1_0_5(project, solver_summary=solver_summary, tutorial_path=artifacts.tutorial_path)
    return {
        "contract": "geoai_simkit_release_1_0_5_workflow_v1",
        "ok": bool(acceptance.accepted),
        "project": project,
        "build": build,
        "validation": validation.to_dict(),
        "gui": gui.to_dict(),
        "compiler": compiler.to_dict(),
        "solver_summary": None if solver_summary is None else solver_summary.to_dict(),
        "viewer": viewer,
        "acceptance": acceptance.to_dict(),
        "artifacts": None if artifacts is None else artifacts.to_dict(),
    }


__all__ = [
    "Release105WorkflowArtifacts",
    "build_release_1_0_5_project",
    "run_release_1_0_5_workflow",
    "export_release_1_0_5_bundle",
    "render_release_1_0_5_tutorial",
]
