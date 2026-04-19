from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.performance_audit import analyze_ui_and_model_performance
from geoai_simkit.core.model import GeometryObjectRecord, MaterialBinding, SimulationModel
from geoai_simkit.geometry.mesh_engine import MeshEngine, MeshEngineOptions, MeshingTarget, normalize_element_family, pv


class FakeBlock:
    def __init__(self, bounds, n_cells=12, n_points=24, region_name='region'):
        self.bounds = bounds
        self.n_cells = n_cells
        self.n_points = n_points
        self.field_data = {'region_name': [region_name]}
        self.cell_data = {}

    def copy(self, deep=True):
        return make_block(self.bounds, self.n_cells, self.n_points, self.field_data['region_name'][0])




def make_block(bounds, n_cells=12, n_points=24, region_name='region'):
    if hasattr(pv, 'RectilinearGrid'):
        import numpy as np
        x1 = bounds[1] if bounds[1] > bounds[0] else bounds[0] + 1.0
        y1 = bounds[3] if bounds[3] > bounds[2] else bounds[2] + 1.0
        z1 = bounds[5] if bounds[5] > bounds[4] else bounds[4] + 1.0
        x = np.linspace(bounds[0], x1, 3)
        y = np.linspace(bounds[2], y1, 3)
        z = np.linspace(bounds[4], z1, 3)
        grid = pv.RectilinearGrid(x, y, z).cast_to_unstructured_grid()
        grid.field_data['region_name'] = [region_name]
        return grid
    return FakeBlock(bounds, n_cells=n_cells, n_points=n_points, region_name=region_name)

def test_normalize_element_family_aliases():
    assert normalize_element_family('gmsh_tet') == 'tet4'
    assert normalize_element_family('voxel_hex8') == 'hex8'
    assert normalize_element_family('tet') == 'tet4'
    assert normalize_element_family('weird') == 'auto'


def test_mesh_engine_collects_material_bound_targets_with_refinement():
    blocks = pv.MultiBlock()
    blocks['soil_a'] = make_block((0, 4, 0, 4, 0, 4), region_name='soil_a')
    blocks['wall_a'] = make_block((3, 5, 0, 4, 0, 4), region_name='wall_a')
    model = SimulationModel(name='demo', mesh=blocks)
    model.object_records = [
        GeometryObjectRecord(key='soil_a', name='soil_a', object_type='Surface', region_name='soil_a', source_block='soil_a', metadata={'role': 'soil', 'bbox_min': [0, 0, 0], 'bbox_max': [4, 4, 4]}),
        GeometryObjectRecord(key='wall_a', name='wall_a', object_type='Surface', region_name='wall_a', source_block='wall_a', metadata={'role': 'wall', 'bbox_min': [3, 0, 0], 'bbox_max': [5, 4, 4]}),
    ]
    model.materials = [MaterialBinding(region_name='wall_a', material_name='linear_elastic')]
    engine = MeshEngine(MeshEngineOptions(global_size=2.0, only_material_bound_geometry=True, local_refinement=True, refinement_trigger_count=2, refinement_ratio=0.5))
    targets = engine.collect_targets(model)
    assert [t.region_name for t in targets] == ['wall_a']
    assert targets[0].target_size < 2.0
    assert 'role-sensitive' in targets[0].strategy or 'local-density' in targets[0].strategy


def test_performance_audit_geometry_only_reports_workflow_hint():
    model = SimulationModel(name='g', mesh=make_block((0, 1, 0, 1, 0, 0), n_cells=3, n_points=4))
    model.metadata['geometry_state'] = 'geometry'
    report = analyze_ui_and_model_performance(model)
    assert any('geometry-only' in finding.message for finding in report.findings)


def test_mesh_engine_mesh_model_serializes_slot_targets_without_dict():
    blocks = pv.MultiBlock()
    blocks['soil_a'] = make_block((0, 4, 0, 4, 0, 4), region_name='soil_a')
    model = SimulationModel(name='demo', mesh=blocks)
    model.object_records = [
        GeometryObjectRecord(key='soil_a', name='soil_a', object_type='Surface', region_name='soil_a', source_block='soil_a', metadata={'role': 'soil'}),
    ]
    model.materials = [MaterialBinding(region_name='soil_a', material_name='linear_elastic')]
    engine = MeshEngine(MeshEngineOptions(global_size=2.0, only_material_bound_geometry=True))
    engine._mesh_single_target = lambda temp_model, target, family: temp_model

    meshed = engine.mesh_model(model)
    payload = meshed.metadata['mesh_engine']['targets'][0]
    assert payload['region_name'] == 'soil_a'
    assert payload['block_key'] == 'soil_a'


def test_audit_findings_are_slots_dataclasses_but_still_serializable():
    model = SimulationModel(name='g', mesh=make_block((0, 1, 0, 1, 0, 0), n_cells=3, n_points=4))
    model.metadata['geometry_state'] = 'geometry'
    report = analyze_ui_and_model_performance(model)
    first = report.findings[0]
    from dataclasses import asdict
    payload = asdict(first)
    assert payload['category'] == 'workflow'


def test_mesh_engine_falls_back_to_hex8_when_tet4_backend_is_unavailable(monkeypatch):
    blocks = pv.MultiBlock()
    blocks['soil_a'] = make_block((0, 4, 0, 4, 0, 4), region_name='soil_a')
    model = SimulationModel(name='demo', mesh=blocks)
    target = MeshingTarget(block_key='soil_a', region_name='soil_a', target_size=1.0)
    engine = MeshEngine(MeshEngineOptions(element_family='tet4', allow_family_fallback=True))

    class _BrokenGmshMesher:
        def __init__(self, *args, **kwargs):
            pass
        def mesh_model(self, model):
            raise RuntimeError('gmsh executable was not found on PATH.')

    import types, sys
    fake_mod = types.SimpleNamespace(GmshMesher=_BrokenGmshMesher, GmshMesherOptions=lambda **kwargs: kwargs)
    monkeypatch.setitem(sys.modules, 'geoai_simkit.geometry.gmsh_mesher', fake_mod)
    engine._voxelize_target = lambda temp_model, temp_target: temp_model
    meshed, actual_family, fallback_reason = engine._mesh_single_target(model, target, 'tet4')
    assert meshed is model
    assert actual_family == 'hex8'
    assert 'gmsh executable' in fallback_reason


def test_consolidated_requirements_include_meshing_and_gui_deps():
    req = Path('requirements.txt').read_text()
    assert 'gmsh>=' in req
    assert 'meshio>=' in req
    assert 'PySide6>=' in req
    assert 'ifcopenshell>=' in req


def test_simulation_model_object_mesh_control_roundtrip():
    model = SimulationModel(name='demo', mesh=make_block((0, 1, 0, 1, 0, 1)))
    model.object_records = [
        GeometryObjectRecord(key='soil_a', name='soil_a', object_type='Surface', region_name='soil_a', source_block='soil_a', metadata={}),
    ]
    model.set_object_mesh_control(['soil_a'], element_family='tet4', target_size=0.25, refinement_ratio=0.5)
    payload = model.object_mesh_control('soil_a')
    assert payload['element_family'] == 'tet4'
    assert payload['target_size'] == 0.25
    assert payload['refinement_ratio'] == 0.5
    model.clear_object_mesh_control(['soil_a'])
    assert model.object_mesh_control('soil_a') == {}


def test_mesh_engine_collects_object_level_mesh_overrides():
    blocks = pv.MultiBlock()
    blocks['wall_a'] = make_block((0, 2, 0, 2, 0, 2), region_name='wall_a')
    model = SimulationModel(name='demo', mesh=blocks)
    model.object_records = [
        GeometryObjectRecord(
            key='wall_a',
            name='wall_a',
            object_type='Surface',
            region_name='wall_a',
            source_block='wall_a',
            metadata={'role': 'wall', 'mesh_control': {'element_family': 'tet4', 'target_size': 0.25, 'refinement_ratio': 0.4}},
        ),
    ]
    model.materials = [MaterialBinding(region_name='wall_a', material_name='linear_elastic')]
    engine = MeshEngine(MeshEngineOptions(global_size=2.0, only_material_bound_geometry=True))
    targets = engine.collect_targets(model)
    assert len(targets) == 1
    assert targets[0].preferred_family == 'tet4'
    assert targets[0].target_size == 0.25
    assert targets[0].metadata['mesh_control_refinement_ratio'] == 0.4


def test_mesh_engine_records_actual_family_after_fallback():
    blocks = pv.MultiBlock()
    blocks['soil_a'] = make_block((0, 4, 0, 4, 0, 4), region_name='soil_a')
    model = SimulationModel(name='demo', mesh=blocks)
    model.object_records = [
        GeometryObjectRecord(key='soil_a', name='soil_a', object_type='Surface', region_name='soil_a', source_block='soil_a', metadata={'role': 'soil', 'mesh_control': {'element_family': 'tet4'}}),
    ]
    model.materials = [MaterialBinding(region_name='soil_a', material_name='linear_elastic')]
    engine = MeshEngine(MeshEngineOptions(global_size=1.0, only_material_bound_geometry=True))
    engine._mesh_single_target = lambda temp_model, target, family: (temp_model, 'hex8', 'gmsh-missing')
    meshed = engine.mesh_model(model)
    summary = meshed.metadata['mesh_engine']
    assert summary['actual_families'] == ['hex8']
    assert summary['completed_targets'][0]['requested_family'] == 'tet4'
    assert summary['completed_targets'][0]['actual_family'] == 'hex8'


def test_mesh_engine_assigns_shared_merge_group_to_soil_targets():
    blocks = pv.MultiBlock()
    blocks['soil_mass'] = make_block((0, 4, 0, 4, -4, 0), region_name='soil_mass')
    blocks['soil_excavation_1'] = make_block((1, 3, 1, 3, -2, 0), region_name='soil_excavation_1')
    model = SimulationModel(name='demo', mesh=blocks)
    model.object_records = [
        GeometryObjectRecord(key='soil_mass', name='soil_mass', object_type='Surface', region_name='soil_mass', source_block='soil_mass', metadata={'role': 'soil'}),
        GeometryObjectRecord(key='soil_excavation_1', name='soil_excavation_1', object_type='Surface', region_name='soil_excavation_1', source_block='soil_excavation_1', metadata={'role': 'soil'}),
    ]
    model.materials = [
        MaterialBinding(region_name='soil_mass', material_name='mohr_coulomb'),
        MaterialBinding(region_name='soil_excavation_1', material_name='mohr_coulomb'),
    ]
    engine = MeshEngine(MeshEngineOptions(global_size=2.0, only_material_bound_geometry=True))
    targets = engine.collect_targets(model)
    assert {t.metadata['mesh_merge_group'] for t in targets} == {'continuum_soil'}


def test_mesh_engine_records_shared_point_weld_group_for_split_soil():
    blocks = pv.MultiBlock()
    blocks['soil_mass'] = make_block((0, 4, 0, 4, -4, 0), region_name='soil_mass')
    blocks['soil_excavation_1'] = make_block((1, 3, 1, 3, -2, 0), region_name='soil_excavation_1')
    model = SimulationModel(name='demo', mesh=blocks)
    model.object_records = [
        GeometryObjectRecord(key='soil_mass', name='soil_mass', object_type='Surface', region_name='soil_mass', source_block='soil_mass', metadata={'role': 'soil'}),
        GeometryObjectRecord(key='soil_excavation_1', name='soil_excavation_1', object_type='Surface', region_name='soil_excavation_1', source_block='soil_excavation_1', metadata={'role': 'soil'}),
    ]
    model.materials = [
        MaterialBinding(region_name='soil_mass', material_name='mohr_coulomb'),
        MaterialBinding(region_name='soil_excavation_1', material_name='mohr_coulomb'),
    ]
    engine = MeshEngine(MeshEngineOptions(global_size=1.0, only_material_bound_geometry=True))
    engine._mesh_single_target = lambda temp_model, target, family: temp_model
    meshed = engine.mesh_model(model)
    assert 'continuum_soil' in meshed.metadata['mesh_engine']['shared_point_weld_groups']
    groups = {region.name: region.metadata.get('mesh_merge_group') for region in meshed.region_tags}
    assert groups['soil_mass'] == 'continuum_soil'
    assert groups['soil_excavation_1'] == 'continuum_soil'



def test_mesh_engine_directly_tetrahedralizes_existing_volume_blocks():
    if not hasattr(pv, 'RectilinearGrid'):
        return
    blocks = pv.MultiBlock()
    blocks['soil_mass'] = make_block((0, 4, 0, 4, -4, 0), region_name='soil_mass')
    model = SimulationModel(name='demo', mesh=blocks)
    model.object_records = [
        GeometryObjectRecord(key='soil_mass', name='soil_mass', object_type='Volume', region_name='soil_mass', source_block='soil_mass', metadata={'role': 'soil'}),
    ]
    model.materials = [MaterialBinding(region_name='soil_mass', material_name='mohr_coulomb')]
    engine = MeshEngine(MeshEngineOptions(global_size=1.0, only_material_bound_geometry=True, element_family='tet4', allow_family_fallback=False))
    meshed = engine.mesh_model(model)
    grid = meshed.to_unstructured_grid()
    assert set(int(v) for v in grid.celltypes) == {10}
    assert 'tet4' in meshed.metadata['mesh_engine']['actual_families']
