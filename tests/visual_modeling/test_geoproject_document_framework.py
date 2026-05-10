from __future__ import annotations

from pathlib import Path


def test_geoproject_document_has_plaxis_style_root_tree(tmp_path: Path) -> None:
    from geoai_simkit.geoproject import GeoProjectDocument

    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d", "depth": 9.0}, name="pytest-geoproject")
    project.compile_phase_models()
    payload = project.to_dict()

    assert payload["contract"] == "geoproject_document_v1"
    assert list(payload.keys())[:11] == [
        "contract",
        "ProjectSettings",
        "SoilModel",
        "GeometryModel",
        "TopologyGraph",
        "StructureModel",
        "MaterialLibrary",
        "MeshModel",
        "PhaseManager",
        "SolverModel",
        "ResultStore",
    ]
    assert {"SoilContour", "Boreholes", "SoilLayerSurfaces", "SoilClusters", "WaterConditions"}.issubset(payload["SoilModel"].keys())
    assert {"Points", "Curves", "Surfaces", "Volumes", "ParametricFeatures"}.issubset(payload["GeometryModel"].keys())
    assert {"Plates", "Beams", "EmbeddedBeams", "Anchors", "StructuralInterfaces"}.issubset(payload["StructureModel"].keys())
    assert {"MeshSettings", "MeshDocument", "MeshEntityMap", "QualityReport"}.issubset(payload["MeshModel"].keys())
    assert {"InitialPhase", "ConstructionPhases", "CalculationSettings", "PhaseStateSnapshots"}.issubset(payload["PhaseManager"].keys())
    assert {"CompiledPhaseModels", "BoundaryConditions", "Loads", "RuntimeSettings"}.issubset(payload["SolverModel"].keys())
    assert {"PhaseResults", "EngineeringMetrics", "Curves", "Sections", "Reports"}.issubset(payload["ResultStore"].keys())

    validation = project.validate_framework()
    assert validation["ok"] is True
    assert validation["counts"]["volumes"] > 0
    assert validation["counts"]["contact_candidates"] > 0
    assert validation["counts"]["compiled_phase_models"] == validation["counts"]["phases"]

    save_path = tmp_path / "project.geojson"
    project.save_json(save_path)
    loaded = GeoProjectDocument.load_json(save_path)
    assert loaded.validate_framework()["ok"] is True
    assert loaded.to_dict()["MeshModel"]["MeshDocument"]["cell_count"] == payload["MeshModel"]["MeshDocument"]["cell_count"]


def test_geoproject_document_public_exports() -> None:
    from geoai_simkit import GeoProjectDocument
    from geoai_simkit.document import GeoProjectDocument as FromDocumentNamespace

    assert GeoProjectDocument is FromDocumentNamespace
