from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.panels.result_viewer import build_result_viewer, export_legacy_vtk
from geoai_simkit.commands import (
    AddPhaseCommand,
    AssignEntityMaterialCommand,
    AssignGeometrySemanticCommand,
    CommandStack,
    CreateBlockCommand,
    CreateLineCommand,
    CreateSurfaceCommand,
    GeneratePreviewMeshCommand,
    RunPreviewStageResultsCommand,
    SetPhaseStructureActivationCommand,
    SetPhaseWaterConditionCommand,
)
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.stl_import_pipeline import STLImportWizardOptions, analyze_stl_file, run_stl_import_pipeline


def _project() -> GeoProjectDocument:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter82")
    project.geometry_model.points.clear()
    project.geometry_model.curves.clear()
    project.geometry_model.surfaces.clear()
    project.geometry_model.volumes.clear()
    return project


def test_p2_semantic_assignment_promotes_raw_geometry_to_engineering_records() -> None:
    project = _project()
    stack = CommandStack()

    surface_result = stack.execute(
        CreateSurfaceCommand(
            coords=((0, 0, 0), (1, 0, 0), (1, 0, -1), (0, 0, -1)),
            surface_id="surface_wall",
            role="sketch",
        ),
        project,
    )
    assert surface_result.ok
    semantic_result = stack.execute(
        AssignGeometrySemanticCommand("surface_wall", "wall", material_id="C30_concrete", metadata={"thickness": 0.8}),
        project,
    )
    assert semantic_result.ok
    assert "wall_surface_wall" in project.structure_model.plates
    assert project.structure_model.plates["wall_surface_wall"].material_id == "C30_concrete"

    line_result = stack.execute(CreateLineCommand((0, 0, -1), (2, 0, -1), edge_id="curve_anchor"), project)
    assert line_result.ok
    anchor_result = stack.execute(
        AssignGeometrySemanticCommand("curve_anchor", "anchor", material_id="anchor_steel", metadata={"prestress": 120.0}),
        project,
    )
    assert anchor_result.ok
    assert "anchor_curve_anchor" in project.structure_model.anchors
    assert project.structure_model.anchors["anchor_curve_anchor"].prestress == 120.0

    block_result = stack.execute(
        CreateBlockCommand(bounds=(0, 1, 0, 1, -2, 0), block_id="volume_soil", role="sketch"),
        project,
    )
    assert block_result.ok
    soil_result = stack.execute(AssignGeometrySemanticCommand("volume_soil", "soil_volume", material_id="soft_clay"), project)
    assert soil_result.ok
    assert project.geometry_model.volumes["volume_soil"].material_id == "soft_clay"
    assert any("volume_soil" in cluster.volume_ids for cluster in project.soil_model.soil_clusters.values())

    mat_result = stack.execute(AssignEntityMaterialCommand("wall_surface_wall", "C35_concrete", category="plate"), project)
    assert mat_result.ok
    assert project.structure_model.plates["wall_surface_wall"].material_id == "C35_concrete"


def test_p4_phase_commands_control_structure_and_water_state() -> None:
    project = _project()
    stack = CommandStack()
    stack.execute(CreateSurfaceCommand(coords=((0, 0, 0), (1, 0, 0), (1, 0, -1)), surface_id="surface_plate"), project)
    stack.execute(AssignGeometrySemanticCommand("surface_plate", "plate", material_id="plate_steel"), project)

    add = stack.execute(AddPhaseCommand("excavation_1", copy_from=project.phase_manager.initial_phase.id), project)
    assert add.ok
    off = stack.execute(SetPhaseStructureActivationCommand("excavation_1", "plate_surface_plate", False), project)
    assert off.ok
    snapshot = project.phase_manager.phase_state_snapshots["excavation_1"]
    assert "plate_surface_plate" not in snapshot.active_structure_ids

    water = stack.execute(SetPhaseWaterConditionCommand("excavation_1", water_condition_id="drawdown", water_level=-3.2), project)
    assert water.ok
    assert project.phase_manager.construction_phases["excavation_1"].water_level == -3.2
    assert project.soil_model.water_conditions["drawdown"].level == -3.2


def test_p5_result_viewer_and_vtk_export(tmp_path: Path) -> None:
    project = _project()
    stack = CommandStack()
    stack.execute(CreateBlockCommand(bounds=(0, 1, 0, 1, -1, 0), block_id="volume_1", role="soil", material_id="soil"), project)
    stack.execute(GeneratePreviewMeshCommand(), project)
    result = stack.execute(RunPreviewStageResultsCommand(), project)
    assert result.ok

    viewer = build_result_viewer(project)
    assert viewer["contract"] == "geoproject_result_viewer_v1"
    assert viewer["available"] is True
    assert viewer["phase_rows"]
    assert any(row["name"] == "max_settlement_mm" for row in viewer["metric_rows"])

    out = export_legacy_vtk(project, tmp_path / "results.vtk")
    assert out["ok"] is True
    assert Path(out["path"]).read_text().startswith("# vtk DataFile Version 3.0")


def test_p3_stl_import_pipeline_analysis_and_optional_volume_mesh(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    stl_path.write_text(
        """
solid tetra
facet normal 0 0 -1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 0 1 0
 endloop
endfacet
facet normal 0 -1 0
 outer loop
  vertex 0 0 0
  vertex 0 0 1
  vertex 1 0 0
 endloop
endfacet
facet normal 1 1 1
 outer loop
  vertex 1 0 0
  vertex 0 0 1
  vertex 0 1 0
 endloop
endfacet
facet normal -1 0 0
 outer loop
  vertex 0 0 0
  vertex 0 1 0
  vertex 0 0 1
 endloop
endfacet
endsolid tetra
""".strip(),
        encoding="utf-8",
    )
    analysis = analyze_stl_file(stl_path, {"name": "tetra", "material_id": "rock"})
    assert analysis["contract"] == "stl_import_wizard_analysis_v1"
    assert analysis["summary"]["triangle_count"] == 4

    result = run_stl_import_pipeline(
        None,
        stl_path,
        STLImportWizardOptions(
            name="tetra",
            material_id="rock",
            repair=True,
            generate_volume_mesh=True,
            volume_mesh_kind="voxel_hex8_from_stl",
            volume_mesh_options={"dims": (2, 2, 2)},
            replace=True,
        ),
    )
    assert result["ok"] is True
    assert result["project"].geometry_model.surfaces
    assert result["current_mesh_summary"]["cell_count"] >= 1
