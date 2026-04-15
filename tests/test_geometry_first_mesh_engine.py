from __future__ import annotations

from geoai_simkit.app.performance_audit import analyze_ui_and_model_performance
from geoai_simkit.core.model import GeometryObjectRecord, MaterialBinding, SimulationModel
from geoai_simkit.geometry.mesh_engine import MeshEngine, MeshEngineOptions, normalize_element_family, pv


class FakeBlock:
    def __init__(self, bounds, n_cells=12, n_points=24, region_name='region'):
        self.bounds = bounds
        self.n_cells = n_cells
        self.n_points = n_points
        self.field_data = {'region_name': [region_name]}
        self.cell_data = {}

    def copy(self, deep=True):
        return FakeBlock(self.bounds, self.n_cells, self.n_points, self.field_data['region_name'][0])


def test_normalize_element_family_aliases():
    assert normalize_element_family('gmsh_tet') == 'tet4'
    assert normalize_element_family('voxel_hex8') == 'hex8'
    assert normalize_element_family('tet') == 'tet4'
    assert normalize_element_family('weird') == 'auto'


def test_mesh_engine_collects_material_bound_targets_with_refinement():
    blocks = pv.MultiBlock()
    blocks['soil_a'] = FakeBlock((0, 4, 0, 4, 0, 4), region_name='soil_a')
    blocks['wall_a'] = FakeBlock((3, 5, 0, 4, 0, 4), region_name='wall_a')
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
    model = SimulationModel(name='g', mesh=FakeBlock((0, 1, 0, 1, 0, 0), n_cells=3, n_points=4))
    model.metadata['geometry_state'] = 'geometry'
    report = analyze_ui_and_model_performance(model)
    assert any('geometry-only' in finding.message for finding in report.findings)


def test_mesh_engine_mesh_model_serializes_slot_targets_without_dict():
    blocks = pv.MultiBlock()
    blocks['soil_a'] = FakeBlock((0, 4, 0, 4, 0, 4), region_name='soil_a')
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
    model = SimulationModel(name='g', mesh=FakeBlock((0, 1, 0, 1, 0, 0), n_cells=3, n_points=4))
    model.metadata['geometry_state'] = 'geometry'
    report = analyze_ui_and_model_performance(model)
    first = report.findings[0]
    from dataclasses import asdict
    payload = asdict(first)
    assert payload['category'] == 'workflow'
