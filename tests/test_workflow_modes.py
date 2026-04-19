from geoai_simkit.app.workflow_modes import (
    build_geometry_structures_rows,
    build_mesh_mode_rows,
    build_stage_activation_matrix,
    build_stages_mode_rows,
    filter_workflow_rows,
    summarize_workflow_modes,
    update_stage_interface_group,
    update_stage_region_activation,
    update_stage_support_group,
    stage_activation_map_for_stage,
)
from geoai_simkit.core.model import (
    AnalysisStage,
    GeometryObjectRecord,
    InterfaceDefinition,
    MaterialBinding,
    SimulationModel,
    StructuralElementDefinition,
)


def make_model():
    model = SimulationModel(name='demo', mesh=object())
    model.object_records = [
        GeometryObjectRecord(
            key='soil', name='soil', object_type='solid', region_name='soil_mass',
            metadata={'role': 'soil', 'mesh_control': {'element_family': 'hex8', 'target_size': 1.5}}
        ),
        GeometryObjectRecord(
            key='wall', name='wall', object_type='solid', region_name='wall',
            metadata={'role': 'wall'}
        ),
    ]
    model.materials = [MaterialBinding(region_name='soil_mass', material_name='mohr_coulomb')]
    model.structures = [StructuralElementDefinition(name='crown', kind='truss2', point_ids=(0, 1), metadata={'source_object': 'wall'})]
    model.interfaces = [InterfaceDefinition(name='iface', kind='spring', slave_point_ids=(0,), master_point_ids=(1,), metadata={'source_object': 'wall'})]
    model.stages = [AnalysisStage(name='initial', metadata={'active_support_groups': ['crown_beam'], 'active_interface_groups': ['outer'], 'solver_preset': 'balanced', 'compute_profile': 'cpu-safe'})]
    model.metadata['geometry_state'] = 'meshed'
    model.metadata['mesh_engine.completed_targets'] = [{'requested_family': 'tet4', 'actual_family': 'hex8'}]
    model.region_tags = []
    return model


def test_geometry_mode_rows_include_material_and_state():
    rows = build_geometry_structures_rows(make_model())
    assert rows[0].material == 'mohr_coulomb'
    assert rows[1].structure_status == 'structure, interface'


def test_mesh_mode_rows_report_requested_and_actual_family():
    model = make_model()
    model.region_tags = []
    # emulate meshing metadata on region after meshing
    from geoai_simkit.core.types import RegionTag
    import numpy as np
    model.region_tags = [RegionTag(name='soil_mass', cell_ids=np.asarray([], dtype=np.int64), metadata={'requested_family': 'tet4', 'actual_family': 'hex8', 'fallback_reason': 'gmsh unavailable'})]
    rows = build_mesh_mode_rows(model)
    assert rows[0].requested_family in {'hex8', 'tet4', 'auto', 'inherit'}
    assert rows[0].actual_family == 'hex8'
    assert 'fallback' in rows[0].status


def test_stage_mode_rows_and_summary():
    model = make_model()
    rows = build_stages_mode_rows(model)
    assert rows[0].supports == 'crown_beam'
    summary = summarize_workflow_modes(model)
    assert 'objects=2' in summary['geometry_structures']
    assert 'stages=1' in summary['stages']


def test_filter_workflow_rows_and_stage_matrix():
    model = make_model()
    rows = build_geometry_structures_rows(model)
    filtered = filter_workflow_rows(rows, ['object_name', 'material', 'structure_status'], 'wall')
    assert len(filtered) == 1
    issue_rows = filter_workflow_rows(rows, ['object_name', 'material', 'structure_status', 'mesh_control'], issues_only=True)
    assert any(row.object_name == 'wall' for row in issue_rows)
    headers, matrix_rows = build_stage_activation_matrix(model)
    assert headers[0] == 'Stage'
    assert matrix_rows[0][0] == 'initial'


def test_update_stage_region_activation_updates_metadata_and_delta():
    from geoai_simkit.core.types import RegionTag
    import numpy as np
    model = make_model()
    model.region_tags = [
        RegionTag(name='soil_mass', cell_ids=np.asarray([], dtype=np.int64), metadata={}),
        RegionTag(name='wall', cell_ids=np.asarray([], dtype=np.int64), metadata={}),
    ]
    model.stages = [
        AnalysisStage(name='initial', metadata={'activation_map': {'soil_mass': True, 'wall': False}}),
        AnalysisStage(name='wall_activation', metadata={'activation_map': {'soil_mass': True, 'wall': False}}),
    ]
    assert update_stage_region_activation(model, 'wall_activation', 'wall', True) is True
    amap = stage_activation_map_for_stage(model, 'wall_activation')
    assert amap == {'soil_mass': True, 'wall': True}
    stage = model.stages[1]
    assert stage.activate_regions == ('wall',)
    assert stage.deactivate_regions == ()



def test_stage_matrix_includes_group_columns_and_group_updates():
    from geoai_simkit.core.types import RegionTag
    import numpy as np
    model = make_model()
    model.region_tags = [
        RegionTag(name='soil_mass', cell_ids=np.asarray([], dtype=np.int64), metadata={}),
        RegionTag(name='wall', cell_ids=np.asarray([], dtype=np.int64), metadata={}),
    ]
    headers, rows = build_stage_activation_matrix(model)
    assert 'S:crown_beam' in headers
    assert 'I:outer' in headers
    assert rows[0][headers.index('S:crown_beam')] == 'on'
    assert rows[0][headers.index('I:outer')] == 'on'
    assert update_stage_support_group(model, 'initial', 'strut_level_1', True) is True
    assert update_stage_interface_group(model, 'initial', 'inner_upper', True) is True
    stage = model.stages[0]
    assert 'strut_level_1' in list(stage.metadata.get('active_support_groups') or [])
    assert 'inner_upper' in list(stage.metadata.get('active_interface_groups') or [])
