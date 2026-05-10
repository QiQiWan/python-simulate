from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit.modules import list_project_modules, module_update_map, run_project_module_smokes
from geoai_simkit.modules import document_model, fem_solver, geotechnical, geology_import, gui_modeling, meshing, postprocessing, stage_planning


def _write_ascii_tetra_stl(path: Path) -> None:
    path.write_text(
        """
solid tetra
facet normal 0 0 1
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
  vertex 0 1 0
  vertex 0 0 1
  vertex 0 0 0
 endloop
endfacet
endsolid tetra
""".strip(),
        encoding="utf-8",
    )


def test_project_module_registry_exposes_update_targets() -> None:
    keys = [row["key"] for row in list_project_modules()]
    assert keys == ["document_model", "geology_import", "meshing", "stage_planning", "gui_modeling", "fem_solver", "geotechnical", "postprocessing"]
    update_map = module_update_map()
    assert update_map["geology_import"]["owned_namespaces"] == [
        "geoai_simkit.geology.importers",
        "geoai_simkit.geometry.stl_loader",
        "geoai_simkit.contracts.geology",
    ]
    assert "import_geology" in update_map["geology_import"]["entrypoints"]
    assert "run_project_incremental_solve" in update_map["fem_solver"]["entrypoints"]
    assert "run_staged_geotechnical_analysis" in update_map["geotechnical"]["entrypoints"]


def test_project_module_smokes_are_dependency_light() -> None:
    result = run_project_module_smokes()
    assert result["ok"] is True
    assert result["check_count"] == 8
    assert result["passed_count"] == 8


def test_geology_import_facade_builds_project_document(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    mesh = geology_import.load_geological_stl(stl_path, {"name": "module_geo", "material_id": "rock"})
    project = geology_import.create_project_from_stl(stl_path, {"name": "module_geo", "material_id": "rock"})
    assert mesh.quality.triangle_count == 4
    assert "module_geo" in project.geometry_model.volumes
    assert project.mesh_model.mesh_document is not None
    assert "rock" in project.material_library.soil_materials


def test_geology_import_registry_supports_structured_json(tmp_path: Path) -> None:
    assert "stl_geology" in geology_import.supported_geology_import_kinds()
    assert "geology_json" in geology_import.supported_geology_import_kinds()
    assert "borehole_csv" in geology_import.supported_geology_import_kinds()
    json_path = tmp_path / "site_geology.json"
    json_path.write_text(
        json.dumps(
            {
                "contract": "geological_model_v1",
                "name": "layered-site",
                "materials": [
                    {
                        "id": "clay",
                        "name": "Soft clay",
                        "model_type": "mohr_coulomb_placeholder",
                        "parameters": {"E_ref": 12000.0, "nu": 0.32},
                        "drainage": "undrained",
                    }
                ],
                "surfaces": [
                    {
                        "id": "ground_surface",
                        "name": "Ground surface",
                        "points": [[0, 0, 0], [10, 0, 0], [10, 8, 0], [0, 8, 0]],
                    }
                ],
                "volumes": [
                    {
                        "id": "upper_clay",
                        "name": "Upper clay",
                        "bounds": [0, 10, 0, 8, -6, 0],
                        "surface_ids": ["ground_surface"],
                        "role": "soil",
                        "material_id": "clay",
                    }
                ],
                "layers": [
                    {
                        "id": "layer_clay",
                        "name": "Clay layer",
                        "volume_ids": ["upper_clay"],
                        "material_id": "clay",
                    }
                ],
                "boreholes": [
                    {
                        "id": "bh_1",
                        "x": 2.5,
                        "y": 3.0,
                        "z": 0.0,
                        "layers": [{"top": 0.0, "bottom": -6.0, "material_id": "clay"}],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = geology_import.import_geology(json_path)
    project = result.project
    assert result.ok is True
    assert result.source_type == "geology_json"
    assert "upper_clay" in project.geometry_model.volumes
    assert "ground_surface" in project.geometry_model.surfaces
    assert "bh_1" in project.soil_model.boreholes
    assert "clay" in project.material_library.soil_materials
    assert project.validate_framework()["ok"] is True


def test_gui_solver_and_postprocessing_facades_share_document_boundary() -> None:
    session = gui_modeling.create_headless_modeling_session({"dimension": "3d"}, name="module-session")
    assert session.document.name == "module-session"
    assert session.viewport.render_payload()["primitives"]

    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="module-project")
    compiled = fem_solver.compile_project_phases(project)
    stage_result = stage_planning.compile_project_stages(project)
    summary = postprocessing.build_project_result_summary(project)
    validation = document_model.validate_project(project)

    assert compiled
    assert stage_result.ok is True
    assert meshing.supported_mesh_generators()
    assert validation["ok"] is True
    assert summary["available"] is True
    assert summary["phase_count"] >= 1
