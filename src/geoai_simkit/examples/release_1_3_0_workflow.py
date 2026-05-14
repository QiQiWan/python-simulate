from __future__ import annotations

"""GeoAI SimKit 1.3.0 Beta workflow.

1.3.0 turns the advanced 1.2.4 calculation stack into a one-click engineering
Beta demo that can be loaded from the six-phase workbench and run through the
full calculation/export pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.app.panels.result_viewer import build_result_viewer, export_legacy_vtk, export_result_summary_json
from geoai_simkit.examples.release_1_2_4_workflow import build_release_1_2_4_project
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.demo_calculation_pipeline import build_demo_pipeline_report
from geoai_simkit.services.engineering_report import build_engineering_report_payload, export_engineering_report
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.release_acceptance_130 import audit_release_1_3_0


@dataclass(slots=True)
class Release130WorkflowArtifacts:
    contract: str = "geoai_simkit_release_1_3_0_artifacts_v1"
    project_path: str = ""
    validation_path: str = ""
    compiler_path: str = ""
    global_newton_path: str = ""
    acceptance_path: str = ""
    gmsh_exchange_path: str = ""
    consolidation_path: str = ""
    interface_iteration_path: str = ""
    demo_run_path: str = ""
    gui_payload_path: str = ""
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
            "compiler_path": self.compiler_path,
            "global_newton_path": self.global_newton_path,
            "acceptance_path": self.acceptance_path,
            "gmsh_exchange_path": self.gmsh_exchange_path,
            "consolidation_path": self.consolidation_path,
            "interface_iteration_path": self.interface_iteration_path,
            "demo_run_path": self.demo_run_path,
            "gui_payload_path": self.gui_payload_path,
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


def build_release_1_3_0_gui_payload(project: GeoProjectDocument | None = None) -> dict[str, Any]:
    phase_ids = [] if project is None else project.phase_ids()
    release = "1.3.0-beta" if project is None else str(project.metadata.get("release", "1.3.0-beta"))
    mesh = None if project is None else project.mesh_model.mesh_document
    return {
        "contract": "release_1_3_0_demo_center_gui_payload_v1",
        "release": release,
        "demo_center": {
            "title": "工程 Beta Demo 中心",
            "default_demo_id": "foundation_pit_3d_beta",
            "one_click_load": True,
            "complete_calculation": True,
            "actions": ["load_demo_project", "run_complete_calculation", "export_demo_bundle"],
            "button_labels": {
                "load_demo_project": "一键加载 1.3 Demo",
                "run_complete_calculation": "运行完整计算流程",
                "export_demo_bundle": "导出 Demo 审查包",
            },
        },
        "phase_ids": phase_ids,
        "mesh": None if mesh is None else {"node_count": mesh.node_count, "cell_count": mesh.cell_count, "cell_types": sorted(set(mesh.cell_types))},
        "actions": ["load_demo_project", "run_complete_calculation", "export_demo_bundle"],
    }


def render_release_1_3_0_tutorial(project: GeoProjectDocument, acceptance: dict[str, Any], pipeline: dict[str, Any]) -> str:
    steps = list(pipeline.get("steps", []) or [])
    step_lines = [f"- `{row.get('status')}` {row.get('label')} ({row.get('phase')})" for row in steps]
    return "\n".join([
        "# GeoAI SimKit 1.3.0 Beta Demo Tutorial",
        "",
        "## 一键 Demo",
        "启动 GUI 后进入六阶段工作台，打开右侧 `1.3 Demo` 页签，点击：",
        "",
        "1. `一键加载 1.3 Demo`：加载三维基坑 Beta 示例工程。",
        "2. `运行完整计算流程`：依次完成地质/结构数据、Tet4 网格、阶段编译、Mohr-Coulomb Newton、固结、界面迭代和结果写入。",
        "3. `导出 Demo 审查包`：导出工程文件、结果、VTK、JSON 和 Markdown 报告。",
        "",
        "## Calculation pipeline",
        *step_lines,
        "",
        "## Acceptance",
        f"- Project: `{project.project_settings.name}`",
        f"- Release: `{project.metadata.get('release', '')}`",
        f"- Phases: `{', '.join(project.phase_ids())}`",
        f"- Status: `{acceptance.get('status', 'unknown')}`",
        f"- Accepted: `{acceptance.get('accepted', False)}`",
        "",
        "## Boundary of use",
        "1.3.0-beta is an engineering Beta demonstration build. It can run the complete built-in calculation workflow, but native Gmsh/OCC and desktop GUI interaction should still be verified on the target workstation before production sign-off.",
        "",
    ])


def build_release_1_3_0_project(*, name: str = "GeoAI SimKit 1.3.0 Beta Foundation Pit Demo", exchange_dir: str | Path | None = None) -> tuple[GeoProjectDocument, dict[str, Any]]:
    project, build124 = build_release_1_2_4_project(name=name, exchange_dir=exchange_dir)
    project.project_settings.name = name
    project.project_settings.metadata.update({"release": "1.3.0-beta", "workflow": "one_click_foundation_pit_beta_demo"})
    project.metadata["release"] = "1.3.0-beta"
    project.metadata["release_line"] = "1.3.x"
    project.metadata["release_1_3_0_demo"] = {
        "contract": "geoai_simkit_release_1_3_0_demo_metadata_v1",
        "demo_id": "foundation_pit_3d_beta",
        "label": "三维基坑分阶段施工 Beta Demo",
        "one_click_load": True,
        "complete_calculation": True,
        "description": "A built-in six-phase foundation-pit demo that runs geology, structures, mesh, staging, nonlinear solve, hydro/contact and results export.",
        "phase_sequence": ["geology", "structures", "mesh", "staging", "solve", "results"],
    }
    gui_payload = build_release_1_3_0_gui_payload(project)
    project.metadata["release_1_3_0_gui_payload"] = gui_payload
    build = {
        "contract": "geoai_simkit_release_1_3_0_build_v1",
        "status": "demo_loaded",
        "release_1_2_4": build124,
        "demo": dict(project.metadata["release_1_3_0_demo"]),
        "gui_payload": gui_payload,
    }
    project.metadata["release_1_3_0_build"] = build
    return project, build


def export_release_1_3_0_bundle(
    project: GeoProjectDocument,
    output_dir: str | Path,
    *,
    validation: dict[str, Any] | None = None,
    compiler: dict[str, Any] | None = None,
    newton_summary: dict[str, Any] | None = None,
    viewer: dict[str, Any] | None = None,
    gui_payload: dict[str, Any] | None = None,
) -> Release130WorkflowArtifacts:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    validation_payload = validation or validate_geoproject_model(project, require_mesh=True, require_results=True).to_dict()
    compiler_payload = compiler or compile_phase_solver_inputs(project, block_on_errors=False).to_dict()
    project.solver_model.metadata["last_phase_solver_compiler"] = compiler_payload
    newton_payload = newton_summary or dict(project.solver_model.metadata.get("last_global_mohr_coulomb_newton_solve", {}) or {})
    gmsh_payload = dict(project.mesh_model.metadata.get("last_gmsh_occ_native_exchange", {}) or {})
    consolidation_payload = dict(project.solver_model.metadata.get("consolidation_coupling_state", {}) or {})
    interface_payload = dict(project.solver_model.metadata.get("interface_contact_iteration", {}) or {})
    gui_payload = gui_payload or build_release_1_3_0_gui_payload(project)
    viewer_payload = viewer or build_result_viewer(project)

    # Write non-acceptance artifacts first so the acceptance gate can verify a
    # complete one-click demo bundle.  The acceptance file is created once as a
    # placeholder to break the self-reference cycle, then overwritten below.
    project_path = project.save_json(root / "release_1_3_0_project.geoproject.json")
    validation_path = _write_json(root / "release_1_3_0_validation.json", validation_payload)
    compiler_path = _write_json(root / "release_1_3_0_compiler.json", compiler_payload)
    newton_path = _write_json(root / "release_1_3_0_global_newton.json", newton_payload)
    gmsh_path = _write_json(root / "release_1_3_0_gmsh_exchange.json", gmsh_payload)
    consolidation_path = _write_json(root / "release_1_3_0_consolidation.json", consolidation_payload)
    interface_path = _write_json(root / "release_1_3_0_interface_iteration.json", interface_payload)
    gui_payload_path = _write_json(root / "release_1_3_0_gui_payload.json", gui_payload)
    viewer_path = _write_json(root / "release_1_3_0_result_viewer.json", viewer_payload)
    result_export = export_result_summary_json(project, root / "release_1_3_0_result_summary_export.json")
    vtk = export_legacy_vtk(project, root / "release_1_3_0_results.vtk")

    acceptance_path = root / "release_1_3_0_acceptance.json"
    acceptance_path.write_text("{}", encoding="utf-8")
    provisional_artifacts = Release130WorkflowArtifacts(
        project_path=str(project_path),
        validation_path=validation_path,
        compiler_path=compiler_path,
        global_newton_path=newton_path,
        acceptance_path=str(acceptance_path),
        gmsh_exchange_path=gmsh_path,
        consolidation_path=consolidation_path,
        interface_iteration_path=interface_path,
        gui_payload_path=gui_payload_path,
        result_viewer_path=viewer_path,
        result_export_path=str(result_export.get("path", root / "release_1_3_0_result_summary_export.json")),
        vtk_path=str(vtk["path"]),
    )
    pipeline = build_demo_pipeline_report(project, artifacts=provisional_artifacts.to_dict(), output_dir=root)
    project.metadata["release_1_3_0_pipeline"] = pipeline.to_dict()
    demo_run_path = _write_json(root / "release_1_3_0_demo_run.json", pipeline.to_dict())
    provisional_artifacts.demo_run_path = demo_run_path
    tutorial_path = root / "release_1_3_0_tutorial.md"
    tutorial_path.write_text(render_release_1_3_0_tutorial(project, {"status": "pending", "accepted": False}, pipeline.to_dict()), encoding="utf-8")
    provisional_artifacts.tutorial_path = str(tutorial_path)
    acceptance = audit_release_1_3_0(project, pipeline=pipeline.to_dict(), artifacts=provisional_artifacts.to_dict(), gui_payload=gui_payload, tutorial_path=tutorial_path).to_dict()
    acceptance_path.write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
    tutorial_path.write_text(render_release_1_3_0_tutorial(project, acceptance, pipeline.to_dict()), encoding="utf-8")
    report_payload = build_engineering_report_payload(project, acceptance=acceptance, solver_summary=newton_payload, compiler=compiler_payload, validation=validation_payload)
    report_payload["release_1_3_0"] = {
        "demo": dict(project.metadata.get("release_1_3_0_demo", {}) or {}),
        "pipeline": pipeline.to_dict(),
        "gui_payload": gui_payload,
        "gmsh_exchange": gmsh_payload,
        "consolidation": consolidation_payload,
        "interface_iteration": interface_payload,
    }
    report_artifacts = export_engineering_report(root, report_payload, stem="release_1_3_0_engineering_report")
    provisional_artifacts.report_markdown_path = report_artifacts.markdown_path
    provisional_artifacts.report_json_path = report_artifacts.json_path
    provisional_artifacts.metadata.update({"phase_count": len(project.phase_ids()), "result_phase_count": len(project.result_store.phase_results), "accepted": bool(acceptance.get("accepted", False))})
    project.metadata["release_1_3_0_artifacts"] = provisional_artifacts.to_dict()
    # Persist the final metadata-rich project file after pipeline/artifacts were recorded.
    project.save_json(project_path)
    return provisional_artifacts


def run_release_1_3_0_workflow(*, output_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(output_dir) if output_dir is not None else Path.cwd() / "exports" / "release_1_3_0_demo_run"
    exchange_dir = root / "gmsh_exchange"
    project, build = build_release_1_3_0_project(exchange_dir=exchange_dir)
    validation = validate_geoproject_model(project, require_mesh=True, require_results=True)
    compiler = compile_phase_solver_inputs(project, block_on_errors=True)
    project.solver_model.metadata["last_phase_solver_compiler"] = compiler.to_dict()
    newton = dict(project.solver_model.metadata.get("last_global_mohr_coulomb_newton_solve", {}) or {})
    viewer = build_result_viewer(project)
    gui_payload = build_release_1_3_0_gui_payload(project)
    artifacts = export_release_1_3_0_bundle(project, root, validation=validation.to_dict(), compiler=compiler.to_dict(), newton_summary=newton, viewer=viewer, gui_payload=gui_payload)
    pipeline = dict(project.metadata.get("release_1_3_0_pipeline", {}) or {})
    acceptance = audit_release_1_3_0(project, pipeline=pipeline, artifacts=artifacts.to_dict(), gui_payload=gui_payload, tutorial_path=artifacts.tutorial_path)
    acceptance_path = Path(artifacts.acceptance_path)
    acceptance_path.write_text(json.dumps(acceptance.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "contract": "geoai_simkit_release_1_3_0_workflow_v1",
        "ok": bool(acceptance.accepted),
        "project": project,
        "build": build,
        "validation": validation.to_dict(),
        "compiler": compiler.to_dict(),
        "newton_summary": newton,
        "pipeline": pipeline,
        "gui_payload": gui_payload,
        "viewer": viewer,
        "acceptance": acceptance.to_dict(),
        "artifacts": artifacts.to_dict(),
    }


__all__ = [
    "Release130WorkflowArtifacts",
    "build_release_1_3_0_project",
    "build_release_1_3_0_gui_payload",
    "run_release_1_3_0_workflow",
    "export_release_1_3_0_bundle",
    "render_release_1_3_0_tutorial",
]
