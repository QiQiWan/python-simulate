from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.workbench import WorkbenchService
from geoai_simkit.commands import CommandStack, GenerateLayeredVolumeMeshCommand
from geoai_simkit.examples.foundation_pit_showcase import build_foundation_pit_showcase_case
from geoai_simkit.modules import geology_import


def _write_borehole_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "borehole_id,x,y,ground_elevation,top_depth,bottom_depth,layer_id,material_id,description",
                "BH1,0,0,12.0,0.0,3.0,fill,fill,Fill",
                "BH1,0,0,12.0,3.0,9.0,clay,clay,Soft clay",
                "BH2,10,0,11.5,0.0,2.5,fill,fill,Fill",
                "BH2,10,0,11.5,2.5,8.0,clay,clay,Soft clay",
                "BH3,0,8,12.5,0.0,4.0,fill,fill,Fill",
                "BH3,0,8,12.5,4.0,10.0,clay,clay,Soft clay",
            ]
        ),
        encoding="utf-8",
    )


def test_generate_layered_volume_mesh_command_updates_geoproject_mesh(tmp_path: Path) -> None:
    csv_path = tmp_path / "boreholes.csv"
    _write_borehole_csv(csv_path)
    project = geology_import.import_geology(csv_path).project
    stack = CommandStack()

    result = stack.execute(GenerateLayeredVolumeMeshCommand(nx=4, ny=3), project)

    assert result.ok is True
    assert result.metadata["cell_count"] == 12
    assert project.mesh_model.mesh_document is not None
    assert project.mesh_model.mesh_document.cell_tags["block_id"][0] == "volume_fill"
    assert project.mesh_model.mesh_settings.metadata["requires_volume_meshing"] is False

    undo = stack.undo(project)
    assert undo.ok is True
    assert project.mesh_model.mesh_document is None


def test_workbench_service_imports_boreholes_and_generates_visual_mesh(tmp_path: Path) -> None:
    csv_path = tmp_path / "boreholes.csv"
    _write_borehole_csv(csv_path)
    service = WorkbenchService()
    document = service.document_from_case(build_foundation_pit_showcase_case(), mode="mesh")

    import_summary = service.import_borehole_csv_geology(document, csv_path)
    pre_preview = service.layered_mesh_preview_payload(document)
    command_result = service.generate_layered_volume_mesh(document, nx=4, ny=3)
    post_preview = service.layered_mesh_preview_payload(document)

    assert import_summary["source_type"] == "borehole_csv"
    assert pre_preview["needs_remesh"] is True
    assert pre_preview["layers"][0]["cell_count"] == 0
    assert command_result.ok is True
    assert document.metadata["geoproject_mesh_summary"]["cell_count"] == 12
    assert post_preview["needs_remesh"] is False
    assert post_preview["cell_count"] == 12
    assert post_preview["layer_count"] == 2
    assert post_preview["min_thickness"] > 0.0
    assert post_preview["max_thickness_ratio"] >= 1.0
    assert post_preview["degenerate_cell_count"] == 0
    assert {row["layer_id"]: row["cell_count"] for row in post_preview["layers"]} == {"clay": 6, "fill": 6}
    assert {row["material_id"] for row in post_preview["layers"]} == {"clay", "fill"}
    assert all(row["min_thickness"] > 0.0 for row in post_preview["layers"])
    assert all(row["max_thickness_ratio"] >= 1.0 for row in post_preview["layers"])
    assert all(row["degenerate_cell_count"] == 0 for row in post_preview["layers"])
    assert post_preview["quality_warning_count"] >= 1
    assert document.model.mesh.n_cells == 12
    assert set(document.model.mesh.cell_data["material_id"]) == {"fill", "clay"}
    assert sorted(block.name for block in document.browser.blocks) == ["volume_clay", "volume_fill"]
