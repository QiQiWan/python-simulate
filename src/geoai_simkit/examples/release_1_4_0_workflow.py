from __future__ import annotations

"""GeoAI SimKit 1.4.0 Beta-2 workflow.

1.4.0 promotes the single 1.3 foundation-pit demo to a multi-template Beta-2
catalog.  The release gate requires three engineering scenarios to be one-click
loadable, runnable and exportable from the six-phase workbench:

* 三维基坑分阶段施工
* 边坡稳定分阶段降雨/扰动
* 桩-土相互作用加载
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.app.panels.result_viewer import build_result_viewer, export_legacy_vtk, export_result_summary_json
from geoai_simkit.examples.release_1_2_4_workflow import build_release_1_2_4_project
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.demo_calculation_pipeline import build_demo_pipeline_report
from geoai_simkit.services.demo_templates import (
    apply_engineering_template_identity,
    build_engineering_template_catalog,
    get_engineering_template_spec,
    list_engineering_templates,
)
from geoai_simkit.services.engineering_report import build_engineering_report_payload, export_engineering_report
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.release_acceptance_140 import audit_release_1_4_0


@dataclass(slots=True)
class Template140Artifacts:
    contract: str = "geoai_simkit_release_1_4_0_template_artifacts_v1"
    demo_id: str = ""
    project_path: str = ""
    validation_path: str = ""
    compiler_path: str = ""
    global_newton_path: str = ""
    acceptance_path: str = ""
    demo_run_path: str = ""
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
            "demo_id": self.demo_id,
            "project_path": self.project_path,
            "validation_path": self.validation_path,
            "compiler_path": self.compiler_path,
            "global_newton_path": self.global_newton_path,
            "acceptance_path": self.acceptance_path,
            "demo_run_path": self.demo_run_path,
            "result_viewer_path": self.result_viewer_path,
            "result_export_path": self.result_export_path,
            "vtk_path": self.vtk_path,
            "report_markdown_path": self.report_markdown_path,
            "report_json_path": self.report_json_path,
            "tutorial_path": self.tutorial_path,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class Release140Artifacts:
    contract: str = "geoai_simkit_release_1_4_0_artifacts_v1"
    catalog_path: str = ""
    summary_path: str = ""
    acceptance_path: str = ""
    gui_payload_path: str = ""
    tutorial_path: str = ""
    template_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "catalog_path": self.catalog_path,
            "summary_path": self.summary_path,
            "acceptance_path": self.acceptance_path,
            "gui_payload_path": self.gui_payload_path,
            "tutorial_path": self.tutorial_path,
            "template_artifacts": dict(self.template_artifacts),
            "metadata": dict(self.metadata),
        }


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def build_release_1_4_0_gui_payload(active_demo_id: str = "foundation_pit_3d_beta") -> dict[str, Any]:
    catalog = build_engineering_template_catalog()
    return {
        "contract": "release_1_4_0_multi_template_gui_payload_v1",
        "release": "1.4.2a-cad-facade",
        "demo_center": {
            "title": "工程 Beta-2 多模板中心",
            "default_demo_id": catalog["default_demo_id"],
            "active_demo_id": active_demo_id,
            "template_count": catalog["template_count"],
            "templates": catalog["templates"],
            "one_click_load": True,
            "complete_calculation": True,
            "actions": ["load_demo_project", "run_complete_calculation", "export_demo_bundle", "run_all_templates"],
            "button_labels": {
                "load_demo_project": "一键加载模板",
                "run_complete_calculation": "运行当前模板完整流程",
                "export_demo_bundle": "导出当前模板审查包",
                "run_all_templates": "运行全部 1.4 模板",
            },
        },
        "template_ids": [row["demo_id"] for row in catalog["templates"]],
        "actions": ["load_demo_project", "run_complete_calculation", "export_demo_bundle", "run_all_templates"],
        "quality_gate": catalog["quality_gate"],
    }


def build_release_1_4_0_project(
    demo_id: str = "foundation_pit_3d_beta",
    *,
    exchange_dir: str | Path | None = None,
) -> tuple[GeoProjectDocument, dict[str, Any]]:
    spec = get_engineering_template_spec(demo_id)
    exchange_root = Path(exchange_dir) if exchange_dir is not None else None
    project, build124 = build_release_1_2_4_project(name=f"GeoAI SimKit 1.4.0 Beta-2 {spec.label}", exchange_dir=exchange_root)
    demo_meta = apply_engineering_template_identity(project, demo_id)
    gui_payload = build_release_1_4_0_gui_payload(demo_id)
    project.metadata["release_1_4_0_gui_payload"] = gui_payload
    build = {
        "contract": "geoai_simkit_release_1_4_0_template_build_v1",
        "status": "template_loaded",
        "release": "1.4.2a-cad-facade",
        "demo_id": demo_id,
        "template_family": spec.template_family,
        "release_1_2_4": build124,
        "demo": demo_meta,
        "gui_payload": gui_payload,
    }
    project.metadata["release_1_4_0_build"] = build
    return project, build


def render_release_1_4_0_template_tutorial(project: GeoProjectDocument, acceptance: dict[str, Any], pipeline: dict[str, Any]) -> str:
    demo = dict(project.metadata.get("release_1_4_0_demo", {}) or {})
    steps = [f"- `{row.get('status')}` {row.get('label')} ({row.get('phase')})" for row in list(pipeline.get("steps", []) or [])]
    outputs = [f"- {item}" for item in list(demo.get("expected_outputs", []) or [])]
    return "\n".join([
        f"# GeoAI SimKit 1.4.0 Beta-2 Template Tutorial — {demo.get('label', '')}",
        "",
        "## 一键模板流程",
        "在六阶段工作台中打开 `1.4 Demo` 页签，选择模板后依次执行：",
        "",
        "1. `一键加载模板`：加载当前工程模板。",
        "2. `运行当前模板完整流程`：执行网格、阶段编译、非线性求解、固结、接触迭代和结果导出。",
        "3. `导出当前模板审查包`：输出工程文件、VTK、JSON 和 Markdown 报告。",
        "4. `运行全部 1.4 模板`：批量运行基坑、边坡、桩-土三类模板。",
        "",
        "## 工程问题",
        str(demo.get("primary_engineering_question", "")),
        "",
        "## 预期输出",
        *outputs,
        "",
        "## Calculation pipeline",
        *steps,
        "",
        "## Acceptance",
        f"- Project: `{project.project_settings.name}`",
        f"- Demo: `{demo.get('demo_id', '')}`",
        f"- Family: `{demo.get('template_family', '')}`",
        f"- Status: `{acceptance.get('status', 'unknown')}`",
        f"- Accepted: `{acceptance.get('accepted', False)}`",
        "",
        "## Boundary of use",
        "1.4.2a-cad-facade is a multi-template engineering Beta. It demonstrates complete calculation and export flows for built-in scenarios; native Gmsh/OCC and desktop GUI interaction should still be validated on the target workstation before production sign-off.",
        "",
    ])


def export_release_1_4_0_template_bundle(
    project: GeoProjectDocument,
    output_dir: str | Path,
    *,
    validation: dict[str, Any] | None = None,
    compiler: dict[str, Any] | None = None,
    newton_summary: dict[str, Any] | None = None,
    viewer: dict[str, Any] | None = None,
) -> Template140Artifacts:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    demo_id = str(project.metadata.get("active_demo_id", "foundation_pit_3d_beta"))
    prefix = f"release_1_4_0_{demo_id}"
    validation_payload = validation or validate_geoproject_model(project, require_mesh=True, require_results=True).to_dict()
    compiler_payload = compiler or compile_phase_solver_inputs(project, block_on_errors=False).to_dict()
    project.solver_model.metadata["last_phase_solver_compiler"] = compiler_payload
    newton_payload = newton_summary or dict(project.solver_model.metadata.get("last_global_mohr_coulomb_newton_solve", {}) or {})
    viewer_payload = viewer or build_result_viewer(project)

    project_path = project.save_json(root / f"{prefix}_project.geoproject.json")
    validation_path = _write_json(root / f"{prefix}_validation.json", validation_payload)
    compiler_path = _write_json(root / f"{prefix}_compiler.json", compiler_payload)
    newton_path = _write_json(root / f"{prefix}_global_newton.json", newton_payload)
    viewer_path = _write_json(root / f"{prefix}_result_viewer.json", viewer_payload)
    result_export = export_result_summary_json(project, root / f"{prefix}_result_summary_export.json")
    vtk = export_legacy_vtk(project, root / f"{prefix}_results.vtk")

    artifacts = Template140Artifacts(
        demo_id=demo_id,
        project_path=str(project_path),
        validation_path=validation_path,
        compiler_path=compiler_path,
        global_newton_path=newton_path,
        result_viewer_path=viewer_path,
        result_export_path=str(result_export.get("path", root / f"{prefix}_result_summary_export.json")),
        vtk_path=str(vtk["path"]),
    )
    pipeline = build_demo_pipeline_report(project, artifacts=artifacts.to_dict(), output_dir=root)
    pipeline.demo_id = demo_id
    pipeline_payload = pipeline.to_dict()
    pipeline_payload["demo_id"] = demo_id
    project.metadata["release_1_4_0_pipeline"] = pipeline_payload
    demo_run_path = _write_json(root / f"{prefix}_demo_run.json", pipeline_payload)
    artifacts.demo_run_path = demo_run_path
    template_result_for_acceptance = {
        demo_id: {
            "ok": bool(pipeline_payload.get("ok", False)),
            "pipeline": pipeline_payload,
            "acceptance": {"accepted": bool(pipeline_payload.get("ok", False)), "status": "accepted_template_pipeline" if pipeline_payload.get("ok", False) else "blocked_template_pipeline"},
            "artifacts": artifacts.to_dict(),
        }
    }
    acceptance = audit_release_1_4_0(
        catalog=build_engineering_template_catalog(),
        template_results=template_result_for_acceptance,
        aggregate_artifacts={},
        gui_payload=build_release_1_4_0_gui_payload(demo_id),
    ).to_dict()
    # For per-template bundles we only require the selected template.  Convert
    # the aggregate blocker caused by other templates into template context.
    selected_ok = bool(pipeline_payload.get("ok", False))
    per_template_acceptance = {
        "contract": "geoai_simkit_release_1_4_0_template_acceptance_v1",
        "status": "accepted_1_4_0_template" if selected_ok else "blocked_1_4_0_template",
        "accepted": selected_ok,
        "demo_id": demo_id,
        "pipeline": pipeline_payload,
        "aggregate_reference": acceptance,
        "blocker_count": 0 if selected_ok else 1,
    }
    acceptance_path = _write_json(root / f"{prefix}_acceptance.json", per_template_acceptance)
    artifacts.acceptance_path = acceptance_path
    tutorial_path = root / f"{prefix}_tutorial.md"
    tutorial_path.write_text(render_release_1_4_0_template_tutorial(project, per_template_acceptance, pipeline_payload), encoding="utf-8")
    artifacts.tutorial_path = str(tutorial_path)
    report_payload = build_engineering_report_payload(project, acceptance=per_template_acceptance, solver_summary=newton_payload, compiler=compiler_payload, validation=validation_payload)
    report_payload["release_1_4_0"] = {"demo": dict(project.metadata.get("release_1_4_0_demo", {}) or {}), "pipeline": pipeline_payload, "template_acceptance": per_template_acceptance}
    report = export_engineering_report(root, report_payload, stem=f"{prefix}_engineering_report")
    artifacts.report_markdown_path = report.markdown_path
    artifacts.report_json_path = report.json_path
    artifacts.metadata.update({"accepted": selected_ok, "phase_count": len(project.phase_ids()), "result_phase_count": len(project.result_store.phase_results)})
    project.metadata["release_1_4_0_template_artifacts"] = artifacts.to_dict()
    project.save_json(project_path)
    return artifacts


def run_release_1_4_0_template_workflow(
    demo_id: str = "foundation_pit_3d_beta",
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(output_dir) if output_dir is not None else Path.cwd() / "exports" / "release_1_4_0_templates" / demo_id
    project, build = build_release_1_4_0_project(demo_id, exchange_dir=root / "gmsh_exchange")
    validation = validate_geoproject_model(project, require_mesh=True, require_results=True)
    compiler = compile_phase_solver_inputs(project, block_on_errors=True)
    project.solver_model.metadata["last_phase_solver_compiler"] = compiler.to_dict()
    newton = dict(project.solver_model.metadata.get("last_global_mohr_coulomb_newton_solve", {}) or {})
    viewer = build_result_viewer(project)
    artifacts = export_release_1_4_0_template_bundle(project, root, validation=validation.to_dict(), compiler=compiler.to_dict(), newton_summary=newton, viewer=viewer)
    pipeline = dict(project.metadata.get("release_1_4_0_pipeline", {}) or {})
    accepted = bool(pipeline.get("ok", False))
    template_acceptance = {"contract": "geoai_simkit_release_1_4_0_template_acceptance_v1", "status": "accepted_1_4_0_template" if accepted else "blocked_1_4_0_template", "accepted": accepted, "demo_id": demo_id, "blocker_count": 0 if accepted else 1}
    Path(artifacts.acceptance_path).write_text(json.dumps(template_acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "contract": "geoai_simkit_release_1_4_0_template_workflow_v1",
        "ok": accepted,
        "status": template_acceptance["status"],
        "demo_id": demo_id,
        "project": project,
        "build": build,
        "validation": validation.to_dict(),
        "compiler": compiler.to_dict(),
        "newton_summary": newton,
        "pipeline": pipeline,
        "viewer": viewer,
        "acceptance": template_acceptance,
        "artifacts": artifacts.to_dict(),
    }


def render_release_1_4_0_tutorial(acceptance: dict[str, Any], template_results: dict[str, Any]) -> str:
    rows = []
    for spec in list_engineering_templates():
        result = dict(template_results.get(spec.demo_id, {}) or {})
        rows.append(f"- `{result.get('status', 'missing')}` **{spec.label}** — {spec.primary_engineering_question}")
    return "\n".join([
        "# GeoAI SimKit 1.4.0 Beta-2 Multi-template Tutorial",
        "",
        "## 目标",
        "1.4.0 将 1.3 的单一基坑 Demo 扩展为多工程模板中心。用户可以在六阶段 GUI 中选择模板，一键加载，并运行完整计算流程。",
        "",
        "## 内置模板",
        *rows,
        "",
        "## GUI 操作",
        "1. 启动软件并通过依赖检查。",
        "2. 进入六阶段工作台，打开 `1.4 Demo` 页签。",
        "3. 选择 `基坑`、`边坡` 或 `桩土` 模板。",
        "4. 点击 `一键加载模板`。",
        "5. 点击 `运行当前模板完整流程` 或 `运行全部 1.4 模板`。",
        "6. 在结果阶段查看结果，并导出审查包。",
        "",
        "## Acceptance",
        f"- Status: `{acceptance.get('status', 'unknown')}`",
        f"- Accepted: `{acceptance.get('accepted', False)}`",
        f"- Completed templates: `{acceptance.get('completed_template_count', 0)}/{acceptance.get('template_count', 0)}`",
        "",
        "## Boundary of use",
        "1.4.2a-cad-facade is a multi-template engineering Beta build. It is suitable for workflow demonstrations and regression review; certified production analysis still requires native Gmsh/OCC, full desktop GUI validation and solver benchmark sign-off.",
        "",
    ])


def export_release_1_4_0_bundle(
    template_results: dict[str, Any],
    output_dir: str | Path,
    *,
    gui_payload: dict[str, Any] | None = None,
) -> Release140Artifacts:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    catalog = build_engineering_template_catalog()
    gui_payload = gui_payload or build_release_1_4_0_gui_payload()
    # Write provisional aggregate artifacts first so acceptance can verify them.
    catalog_path = _write_json(root / "release_1_4_0_template_catalog.json", catalog)
    gui_payload_path = _write_json(root / "release_1_4_0_gui_payload.json", gui_payload)
    summary = {
        "contract": "geoai_simkit_release_1_4_0_multi_template_summary_v1",
        "release": "1.4.2a-cad-facade",
        "template_count": len(template_results),
        "templates": {key: {"ok": bool(value.get("ok", False)), "status": value.get("status", ""), "artifacts": value.get("artifacts", {})} for key, value in template_results.items()},
    }
    summary_path = _write_json(root / "release_1_4_0_multi_template_summary.json", summary)
    tutorial_path = root / "release_1_4_0_tutorial.md"
    acceptance_placeholder = {"status": "pending", "accepted": False}
    tutorial_path.write_text(render_release_1_4_0_tutorial(acceptance_placeholder, template_results), encoding="utf-8")
    provisional = Release140Artifacts(catalog_path=catalog_path, summary_path=summary_path, gui_payload_path=gui_payload_path, tutorial_path=str(tutorial_path), template_artifacts={key: value.get("artifacts", {}) for key, value in template_results.items()})
    acceptance = audit_release_1_4_0(catalog=catalog, template_results=template_results, aggregate_artifacts=provisional.to_dict(), gui_payload=gui_payload).to_dict()
    acceptance_path = _write_json(root / "release_1_4_0_acceptance.json", acceptance)
    tutorial_path.write_text(render_release_1_4_0_tutorial(acceptance, template_results), encoding="utf-8")
    provisional.acceptance_path = acceptance_path
    provisional.metadata.update({"accepted": bool(acceptance.get("accepted", False)), "completed_template_count": acceptance.get("completed_template_count", 0), "template_count": acceptance.get("template_count", 0)})
    # Update acceptance now that its path exists.
    acceptance = audit_release_1_4_0(catalog=catalog, template_results=template_results, aggregate_artifacts=provisional.to_dict(), gui_payload=gui_payload).to_dict()
    Path(acceptance_path).write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
    provisional.metadata.update({"accepted": bool(acceptance.get("accepted", False)), "completed_template_count": acceptance.get("completed_template_count", 0), "template_count": acceptance.get("template_count", 0)})
    return provisional


def run_release_1_4_0_workflow(*, output_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(output_dir) if output_dir is not None else Path.cwd() / "exports" / "release_1_4_0_multi_template"
    root.mkdir(parents=True, exist_ok=True)
    template_results: dict[str, Any] = {}
    for spec in list_engineering_templates():
        template_results[spec.demo_id] = run_release_1_4_0_template_workflow(spec.demo_id, output_dir=root / spec.demo_id)
    gui_payload = build_release_1_4_0_gui_payload()
    aggregate_artifacts = export_release_1_4_0_bundle(template_results, root, gui_payload=gui_payload)
    acceptance = audit_release_1_4_0(catalog=build_engineering_template_catalog(), template_results=template_results, aggregate_artifacts=aggregate_artifacts.to_dict(), gui_payload=gui_payload)
    Path(aggregate_artifacts.acceptance_path).write_text(json.dumps(acceptance.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "contract": "geoai_simkit_release_1_4_0_workflow_v1",
        "ok": bool(acceptance.accepted),
        "release": "1.4.2a-cad-facade",
        "catalog": build_engineering_template_catalog(),
        "template_results": template_results,
        "gui_payload": gui_payload,
        "acceptance": acceptance.to_dict(),
        "artifacts": aggregate_artifacts.to_dict(),
    }


__all__ = [
    "Template140Artifacts",
    "Release140Artifacts",
    "build_release_1_4_0_gui_payload",
    "build_release_1_4_0_project",
    "run_release_1_4_0_template_workflow",
    "run_release_1_4_0_workflow",
    "export_release_1_4_0_bundle",
    "render_release_1_4_0_tutorial",
]
