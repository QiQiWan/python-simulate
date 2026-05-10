from __future__ import annotations

from pathlib import Path

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
            ]
        ),
        encoding="utf-8",
    )


def test_borehole_csv_importer_builds_soil_model_surfaces_and_partitions(tmp_path: Path) -> None:
    csv_path = tmp_path / "boreholes.csv"
    _write_borehole_csv(csv_path)
    result = geology_import.import_geology(csv_path)
    project = result.project

    assert result.ok is True
    assert result.source_type == "borehole_csv"
    assert result.metadata["borehole_count"] == 2
    assert sorted(project.soil_model.boreholes) == ["bh1", "bh2"]
    assert len(project.soil_model.boreholes["bh1"].layers) == 2
    assert project.soil_model.boreholes["bh1"].layers[0].top == 12.0
    assert project.soil_model.boreholes["bh1"].layers[0].bottom == 9.0

    assert "layer_fill_top" in project.soil_model.soil_layer_surfaces
    assert "layer_fill_bottom" in project.soil_model.soil_layer_surfaces
    assert "layer_clay_top" in project.soil_model.soil_layer_surfaces
    assert "layer_clay_bottom" in project.soil_model.soil_layer_surfaces
    assert len(project.soil_model.soil_layer_surfaces["layer_clay_bottom"].control_points) == 2

    assert "volume_fill" in project.geometry_model.volumes
    assert "volume_clay" in project.geometry_model.volumes
    assert project.geometry_model.volumes["volume_clay"].material_id == "clay"
    assert "cluster_fill" in project.soil_model.soil_clusters
    assert "cluster_clay" in project.soil_model.soil_clusters
    assert sorted(project.material_library.soil_materials) == ["clay", "fill"]
    assert project.mesh_model.mesh_settings.metadata["requires_volume_meshing"] is True
    assert project.validate_framework()["ok"] is True


def test_borehole_csv_importer_supports_absolute_elevation_mode(tmp_path: Path) -> None:
    csv_path = tmp_path / "boreholes_elevation.csv"
    csv_path.write_text(
        "\n".join(
            [
                "bh_id,x,y,top,bottom,layer,material",
                "A,0,0,100,96,sand,sand",
                "A,0,0,96,90,rock,rock",
            ]
        ),
        encoding="utf-8",
    )
    result = geology_import.import_geology(csv_path, options={"top_bottom_mode": "elevation", "xy_padding": 1.0})
    project = result.project

    assert result.ok is True
    assert project.soil_model.boreholes["a"].layers[0].top == 100.0
    assert project.soil_model.boreholes["a"].layers[0].bottom == 96.0
    assert project.geometry_model.volumes["volume_sand"].bounds == (-1.0, 1.0, -1.0, 1.0, 96.0, 100.0)
