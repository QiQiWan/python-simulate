from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.commands.cad_fem_preprocessor_commands import BuildCadFemPreprocessorCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.core.cad_fem_preprocessor import CAD_FEM_PREPROCESSOR_CONTRACT, CadFemReadinessReport
from geoai_simkit.geoproject.cad_shape_store import CadShapeRecord, CadTopologyRecord
from geoai_simkit.services.cad_fem_preprocessor import build_cad_fem_preprocessor, validate_cad_fem_preprocessor
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.topology_identity_service import build_topology_identity_index


def _attach_box_topology(project):
    volume_id = next(iter(project.geometry_model.volumes))
    volume = project.geometry_model.volumes[volume_id]
    all_bounds = [tuple(float(v) for v in row.bounds) for row in project.geometry_model.volumes.values() if row.bounds is not None]
    bounds = (
        min(row[0] for row in all_bounds),
        max(row[1] for row in all_bounds),
        min(row[2] for row in all_bounds),
        max(row[3] for row in all_bounds),
        min(row[4] for row in all_bounds),
        max(row[5] for row in all_bounds),
    )
    material_id = str(volume.material_id or "")
    shape_id = "shape:148:box"
    solid_id = "solid:148:box"
    faces = {
        "xmin": (bounds[0], bounds[0], bounds[2], bounds[3], bounds[4], bounds[5]),
        "xmax": (bounds[1], bounds[1], bounds[2], bounds[3], bounds[4], bounds[5]),
        "ymin": (bounds[0], bounds[1], bounds[2], bounds[2], bounds[4], bounds[5]),
        "ymax": (bounds[0], bounds[1], bounds[3], bounds[3], bounds[4], bounds[5]),
        "zmin": (bounds[0], bounds[1], bounds[2], bounds[3], bounds[4], bounds[4]),
        "zmax": (bounds[0], bounds[1], bounds[2], bounds[3], bounds[5], bounds[5]),
    }
    face_ids = [f"face:148:{name}" for name in faces]
    edge_id = "edge:148:xmin_zmin"
    project.cad_shape_store.shapes[shape_id] = CadShapeRecord(
        id=shape_id,
        name="Iter 148 box shape",
        kind="solid",
        source_entity_ids=[volume_id],
        backend="cad_facade",
        native_shape_available=True,
        topology_ids=[solid_id, *face_ids, edge_id],
        material_id=material_id,
        phase_ids=["initial"],
        metadata={"native_brep_certified": True},
    )
    project.cad_shape_store.topology_records[solid_id] = CadTopologyRecord(
        id=solid_id,
        shape_id=shape_id,
        kind="solid",
        source_entity_id=volume_id,
        bounds=bounds,
        persistent_name="iter148/solid/0",
        native_tag="solid-native",
        metadata={"native_topology": True},
    )
    for name, face_bounds in faces.items():
        tid = f"face:148:{name}"
        project.cad_shape_store.topology_records[tid] = CadTopologyRecord(
            id=tid,
            shape_id=shape_id,
            kind="face",
            source_entity_id=volume_id,
            parent_id=solid_id,
            bounds=face_bounds,
            persistent_name=f"iter148/face/{name}",
            native_tag=f"face-native-{name}",
            orientation=name,
            metadata={"native_topology": True, "orientation": name},
        )
    project.cad_shape_store.topology_records[edge_id] = CadTopologyRecord(
        id=edge_id,
        shape_id=shape_id,
        kind="edge",
        source_entity_id=volume_id,
        parent_id="face:148:xmin",
        bounds=(bounds[0], bounds[0], bounds[2], bounds[2], bounds[4], bounds[5]),
        persistent_name="iter148/edge/xmin_zmin",
        native_tag="edge-native-xmin-zmin",
        metadata={"native_topology": True},
    )
    return shape_id, solid_id, face_ids, edge_id


def test_iter148_version_and_cad_fem_contracts_are_exposed():
    assert __version__ in {"1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    payload = build_phase_workbench_qt_payload()
    bridge = payload["geometry_interaction"]["cad_fem_preprocessor"]
    assert bridge["contract"] == CAD_FEM_PREPROCESSOR_CONTRACT
    assert "physical_groups" in bridge["produces"]
    assert "boundary_candidates" in bridge["produces"]
    assert "mesh_controls" in bridge["produces"]


def test_iter148_builds_physical_groups_boundary_candidates_and_mesh_controls():
    project = load_demo_project("foundation_pit_3d_beta")
    _shape_id, solid_id, face_ids, edge_id = _attach_box_topology(project)
    index = build_topology_identity_index(project, attach=True)
    assert index.summary()["face_count"] >= 6

    report = build_cad_fem_preprocessor(project, attach=True, default_element_size=1.25)
    payload = report.to_dict()
    assert payload["contract"] == CAD_FEM_PREPROCESSOR_CONTRACT
    assert report.ok is True
    assert report.status in {"ready_for_meshing", "ready_for_solve_precheck"}
    assert report.summary()["physical_group_count"] >= 2
    assert report.summary()["boundary_candidate_count"] >= 7
    assert report.summary()["mesh_control_count"] >= 1
    roles = {item.candidate_role for item in report.boundary_candidates}
    assert "fixed_base" in roles
    assert "roller_side" in roles
    assert "load_or_free_surface" in roles
    assert "line_load_or_snap_reference" in roles
    assert any(item.topology_id == edge_id and item.dimension == 1 for item in report.boundary_candidates)
    assert any(item.target_key.endswith(solid_id) and item.element_size == 1.25 for item in report.mesh_controls)
    assert project.metadata["cad_fem_preprocessor"]["summary"]["boundary_candidate_count"] >= 7
    assert project.mesh_model.mesh_settings.local_size_fields
    assert any(face_id in item.topology_id for face_id in face_ids for item in report.boundary_candidates)

    validation = validate_cad_fem_preprocessor(project)
    assert validation["ok"] is True

    restored = CadFemReadinessReport.from_dict(project.metadata["cad_fem_preprocessor"])
    assert restored.summary()["mesh_control_count"] == report.summary()["mesh_control_count"]


def test_iter148_cad_fem_preprocessor_command_is_undoable():
    project = load_demo_project("foundation_pit_3d_beta")
    _attach_box_topology(project)
    stack = CommandStack()
    result = stack.execute(BuildCadFemPreprocessorCommand(default_element_size=1.5), project)
    assert result.ok
    assert "cad_fem_preprocessor" in project.metadata
    assert project.mesh_model.mesh_settings.local_size_fields
    undo = stack.undo(project)
    assert undo.ok
    assert "cad_fem_preprocessor" not in project.metadata


def test_iter148_validation_blocks_missing_cad_topology():
    project = load_demo_project("foundation_pit_3d_beta")
    validation = validate_cad_fem_preprocessor(project)
    assert validation["ok"] is False
    assert any("topology" in item.lower() or "shape" in item.lower() for item in validation["blockers"])


def _imports(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    rows: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            rows.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            rows.add(node.module)
    return rows


def test_iter148_core_and_service_boundaries_stay_headless():
    core_imports = _imports("src/geoai_simkit/core/cad_fem_preprocessor.py")
    service_imports = _imports("src/geoai_simkit/services/cad_fem_preprocessor.py")
    forbidden_core = {"geoai_simkit.app", "geoai_simkit.services", "geoai_simkit.geoproject", "PySide6", "pyvista", "vtk", "OCP", "ifcopenshell", "gmsh", "meshio"}
    forbidden_service = {"geoai_simkit.app", "PySide6", "pyvista", "vtk", "OCP", "ifcopenshell", "gmsh", "meshio"}
    assert not any(item == bad or item.startswith(bad + ".") for item in core_imports for bad in forbidden_core)
    assert not any(item == bad or item.startswith(bad + ".") for item in service_imports for bad in forbidden_service)
