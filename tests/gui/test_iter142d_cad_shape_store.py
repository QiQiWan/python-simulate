from __future__ import annotations
from pathlib import Path
from geoai_simkit._version import __version__
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.commands.cad_kernel_commands import BuildCadShapeStoreCommand, ExecuteGmshOccBooleanMeshRoundtripCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.interactive_geometry_commands import BooleanGeometryCommand
from geoai_simkit.examples.release_1_4_2d_workflow import run_release_1_4_2d_workflow
from geoai_simkit.geoproject.document import GeoProjectDocument
from geoai_simkit.services.cad_shape_store_service import build_cad_shape_store, validate_cad_shape_store
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.release_acceptance_142d import audit_release_1_4_2d

def _two_volumes(project):
    ids=list(project.geometry_model.volumes)[:2]; assert len(ids)>=2; return tuple(ids)

def test_142d_version_and_document_roundtrip_cad_shape_store():
    assert __version__ in {'1.4.2d-cad-shape-store', '1.4.3-step-ifc-shape-binding', '1.4.8-cad-fem-preprocessor', '1.4.9-p85-step-ifc-native-benchmark'}
    project=load_demo_project('foundation_pit_3d_beta')
    report=build_cad_shape_store(project,attach=True)
    assert report.ok
    assert project.cad_shape_store.contract=='geoproject_cad_shape_store_v1'
    assert project.cad_shape_store.shapes and project.cad_shape_store.serialized_refs and project.cad_shape_store.topology_records
    loaded=GeoProjectDocument.from_dict(project.to_dict())
    assert loaded.cad_shape_store.shapes.keys()==project.cad_shape_store.shapes.keys()
    assert validate_cad_shape_store(loaded)['ok'] is True

def test_142d_build_command_after_roundtrip(tmp_path):
    project=load_demo_project('foundation_pit_3d_beta'); stack=CommandStack(); stack.execute(BooleanGeometryCommand(operation='union',target_ids=_two_volumes(project)),project)
    assert stack.execute(ExecuteGmshOccBooleanMeshRoundtripCommand(output_dir=str(tmp_path),stem='rt'),project).ok
    result=stack.execute(BuildCadShapeStoreCommand(output_dir=str(tmp_path),include_roundtrip=True,export_references=True),project)
    assert result.ok and result.metadata['shape_count']>0 and result.metadata['operation_count']>=1
    assert Path(result.metadata['exported_store_path']).exists()
    assert audit_release_1_4_2d(project).accepted

def test_142d_workflow_exports_review_bundle(tmp_path):
    result=run_release_1_4_2d_workflow(output_dir=tmp_path)
    assert result['ok'] is True
    assert result['acceptance']['status'] in {'accepted_1_4_2d_cad_shape_store', 'accepted_1_4_2d_native_brep_store'}
    for key in ['project_path','shape_store_path','shape_store_build_path','shape_store_validation_path','acceptance_path','tutorial_path']:
        assert Path(result['artifacts'][key]).exists()

def test_142d_gui_payload_exposes_cad_shape_store():
    payload=build_phase_workbench_qt_payload('structures')
    store=payload['geometry_interaction']['cad_shape_store']
    assert store['contract']=='phase_workbench_cad_shape_store_v1'
    assert store['brep_reference_roundtrip'] is True
    assert store['save_load_persistent'] is True
