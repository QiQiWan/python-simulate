from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.panels.release_showcase import build_release_1_0_showcase_payload
from geoai_simkit.examples.release_1_0_workflow import build_release_1_0_project, run_release_1_0_workflow
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.release_acceptance import audit_release_1_0


def test_release_1_0_build_uses_production_hex8_mesh() -> None:
    project, mesh_report = build_release_1_0_project()
    mesh = project.mesh_model.mesh_document
    assert project.project_settings.metadata["release"] == "1.0.0-basic"
    assert project.metadata["release"] == "1.0.0-basic"
    assert mesh_report["ok"] is True
    assert mesh is not None
    assert mesh.metadata["production_ready"] is True
    assert set(mesh.cell_types) == {"hex8"}
    assert mesh.cell_count == 4
    assert mesh.node_count < 32  # shared-node promotion deduplicates coincident vertices
    assert mesh.quality.bad_cell_ids == []


def test_release_1_0_compiler_uses_compact_active_phase_mesh() -> None:
    project, _ = build_release_1_0_project()
    compiler = compile_phase_solver_inputs(project)
    assert compiler.ok
    assert compiler.compiled_phase_count == len(project.phase_ids())
    compiled_initial = project.solver_model.compiled_phase_models["compiled_initial"]
    assert compiled_initial.metadata["compact_active_mesh"] is True
    assert compiled_initial.metadata["contract"] == "compiled_phase_model_input_skeleton_v3"
    for compiled in project.solver_model.compiled_phase_models.values():
        node_count = len(compiled.mesh_block["node_coordinates"])
        assert compiled.active_dof_count == node_count * 3
        used_nodes = sorted({nid for row in compiled.element_block["elements"] for nid in row["connectivity"]})
        assert used_nodes == list(range(node_count))


def test_release_1_0_end_to_end_is_accepted_and_exports_bundle(tmp_path: Path) -> None:
    result = run_release_1_0_workflow(output_dir=tmp_path)
    assert result["contract"] == "geoai_simkit_release_1_0_workflow_v1"
    assert result["ok"] is True
    assert result["solver_summary"]["accepted"] is True
    assert all(row["converged"] for row in result["solver_summary"]["phase_records"])
    assert result["acceptance"]["accepted"] is True
    assert result["acceptance"]["status"] == "accepted_1_0_basic"
    assert result["acceptance"]["blocker_count"] == 0
    artifacts = result["artifacts"]
    for key in (
        "project_path",
        "validation_path",
        "compiler_path",
        "solver_summary_path",
        "acceptance_path",
        "result_viewer_path",
        "result_export_path",
        "vtk_path",
        "report_markdown_path",
        "report_json_path",
    ):
        assert Path(artifacts[key]).exists(), key
    report_text = Path(artifacts["report_markdown_path"]).read_text(encoding="utf-8")
    assert "accepted_1_0_basic" in report_text
    assert "Solver Phase Records" in report_text
    reloaded = GeoProjectDocument.load_json(artifacts["project_path"])
    assert reloaded.phase_ids() == ["initial", "excavation_1", "support_1", "excavation_2", "support_2"]
    assert reloaded.mesh_model.mesh_document is not None
    assert set(reloaded.mesh_model.mesh_document.cell_types) == {"hex8"}
    assert len(reloaded.result_store.phase_results) == 5


def test_release_1_0_audit_blocks_preview_or_nonconverged_models() -> None:
    # Baseline accepted case.
    result = run_release_1_0_workflow()
    project = result["project"]
    accepted = audit_release_1_0(project, solver_summary=result["solver_summary"])
    assert accepted.accepted

    # Deliberately regress the mesh to a preview type; the release gate must block it.
    mesh = project.mesh_model.mesh_document
    assert mesh is not None
    mesh.cell_types = ["hex8_preview"] * mesh.cell_count
    blocked = audit_release_1_0(project, solver_summary=result["solver_summary"])
    assert not blocked.accepted
    assert any(finding.code == "mesh.preview_cells" for finding in blocked.findings)


def test_release_1_0_gui_payload_is_acceptance_aware() -> None:
    result = run_release_1_0_workflow()
    payload = build_release_1_0_showcase_payload(result["project"])
    assert payload["contract"] == "release_1_0_showcase_panel_v1"
    assert payload["release"] == "1.0.0-basic"
    assert payload["mesh"]["cell_types"] == ["hex8"]
    assert payload["acceptance"]["accepted"] is True
    assert "run_release_1_0_workflow" in payload["actions"]
