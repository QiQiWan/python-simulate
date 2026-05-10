from __future__ import annotations

from pathlib import Path

from geoai_simkit.geology import interpolate_project_layer_surfaces
from geoai_simkit.mesh import generate_layered_volume_mesh
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


def test_interpolates_borehole_layer_surfaces_to_structured_grids(tmp_path: Path) -> None:
    csv_path = tmp_path / "boreholes.csv"
    _write_borehole_csv(csv_path)
    project = geology_import.import_geology(csv_path).project

    result = interpolate_project_layer_surfaces(project, nx=4, ny=3)

    assert result.ok is True
    assert result.to_dict()["surface_count"] == 4
    grid = project.soil_model.soil_layer_surfaces["layer_clay_bottom"].metadata["surface_grid"]
    assert grid["shape"] == [3, 4]
    assert len(grid["points"]) == 12
    assert len(grid["cells"]) == 6
    control_z = [point[2] for point in project.soil_model.soil_layer_surfaces["layer_clay_bottom"].control_points]
    interpolated_z = [point[2] for point in grid["points"]]
    assert min(interpolated_z) >= min(control_z) - 1.0e-9
    assert max(interpolated_z) <= max(control_z) + 1.0e-9


def test_generates_layered_volume_mesh_from_interpolated_surfaces(tmp_path: Path) -> None:
    csv_path = tmp_path / "boreholes.csv"
    _write_borehole_csv(csv_path)
    project = geology_import.import_geology(csv_path).project

    result = generate_layered_volume_mesh(project, nx=4, ny=3)
    mesh = result.mesh

    assert result.ok is True
    assert result.layer_count == 2
    assert mesh.cell_count == 12
    assert mesh.node_count == 48
    assert set(mesh.cell_types) == {"hex8"}
    assert set(mesh.cell_tags["layer_id"]) == {"fill", "clay"}
    assert set(mesh.cell_tags["material_id"]) == {"fill", "clay"}
    assert set(mesh.cell_tags["block_id"]) == {"volume_fill", "volume_clay"}
    assert project.mesh_model.mesh_document is mesh
    assert project.mesh_model.mesh_settings.metadata["requires_volume_meshing"] is False
    assert mesh.entity_map.block_to_cells["volume_fill"] == list(range(0, 6))
    assert mesh.entity_map.block_to_cells["volume_clay"] == list(range(6, 12))
