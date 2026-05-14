from pathlib import Path

from geoai_simkit.geology.importers.contracts import GeologyImportRequest
from geoai_simkit.geology.importers.meshio_importer import MeshioGeologyImporter
from geoai_simkit._version import __version__


def test_iter167_version():
    assert __version__ == "1.6.7-meshio-geology-import-empty-start"


def test_uploaded_vtu_and_msh_parse_as_volume_meshes():
    importer = MeshioGeologyImporter()
    for path in (Path("/mnt/data/model_volume.vtu"), Path("/mnt/data/model_volume.msh")):
        result = importer.import_to_project(GeologyImportRequest(source=path, source_type=path.suffix.lstrip(".")))
        assert result.ok
        assert result.metadata["node_count"] == 31200
        assert result.metadata["cell_count"] == 27027
        assert result.metadata["volume_mesh_ready"] is True
        project = result.project
        assert len(project.geometry_model.volumes) == 1
        assert project.mesh_model.mesh_document is not None
        assert project.mesh_model.mesh_document.node_count == 31200
        assert project.mesh_model.mesh_document.cell_count == 27027
        assert set(project.mesh_model.mesh_document.cell_types) == {"hex8"}
        assert project.metadata["solid_solver_ready"] is True


def test_meshio_importer_source_code_has_no_numpy_truth_value_pattern():
    source = Path("src/geoai_simkit/geology/importers/meshio_importer.py").read_text(encoding="utf-8")
    assert 'getattr(mesh, "points", []) or []' not in source
    assert 'getattr(mesh, "cells", []) or []' not in source
    assert "raw_points = getattr(mesh" in source


def test_phase_workbench_starts_with_empty_project_source_code_contract():
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert "GeoProjectDocument.create_empty" in source
    assert "startup_empty_scene" in source
    assert "template_loaded" in source
