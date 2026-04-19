import numpy as np
import pyvista as pv

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.core.types import ResultField
from geoai_simkit.results import build_result_database
from geoai_simkit.results.runtime_adapter import RuntimeResultStoreAdapter
from geoai_simkit.runtime.result_store import RuntimeResultStore


def test_result_database_groups_fields_by_stage():
    grid = pv.ImageData(dimensions=(2, 2, 2)).cast_to_unstructured_grid()
    model = SimulationModel(name='demo', mesh=grid)
    model.add_result(ResultField(name='U', association='point', values=np.zeros((grid.n_points, 3)), components=3, stage='initial'))
    model.add_result(ResultField(name='von_mises', association='cell', values=np.zeros(grid.n_cells), components=1, stage='initial'))
    model.add_result(ResultField(name='U', association='point', values=np.ones((grid.n_points, 3)), components=3, stage='excavate'))
    db = build_result_database(model)
    assert db.stage_names() == ['initial', 'excavate']
    assert 'U@initial' in db.field_labels()
    assert 'von_mises@initial' in db.field_labels()


def test_runtime_result_store_adapter_preserves_stage_assets():
    store = RuntimeResultStore(
        metadata={
            'case_name': 'runtime-demo',
            'stage_linear_system_plans': [
                {'stage_name': 'initial', 'estimated_matrix_storage_bytes': 1024}
            ],
            'linear_system_diagnostics_summary': {
                'stage_count': 1,
                'stages_with_actual_operator_count': 1,
            },
        }
    )
    store.capture_field(
        ResultField(
            name='U',
            association='point',
            values=np.zeros((1, 3), dtype=float),
            components=3,
            stage='initial',
        )
    )
    store.stage_summaries.append({'stage_name': 'initial', 'field_count': 1})
    store.capture_stage_asset(
        {
            'stage_name': 'initial',
            'stage_summary': {'stage_name': 'initial', 'field_count': 1},
            'stage_linear_system_plan': {'stage_name': 'initial', 'estimated_matrix_storage_bytes': 1024},
            'operator_summary': {'operator': 'continuum_hex8'},
            'linear_system_diagnostics': {
                'stage_name': 'initial',
                'actual_matrix_storage_bytes': 768,
                'active_cell_count_match': True,
            },
        }
    )

    db = RuntimeResultStoreAdapter().from_runtime_store(store)
    assert db.metadata['stage_asset_count'] == 1
    assert db.metadata['stage_linear_system_diagnostics_count'] == 1
    assert db.metadata['linear_system_diagnostics_summary']['stage_count'] == 1
    stage_record = db.stages[0]
    assert stage_record.metadata['stage_asset']['stage_name'] == 'initial'
    assert stage_record.metadata['stage_summary']['stage_name'] == 'initial'
    assert stage_record.metadata['stage_linear_system_plan']['estimated_matrix_storage_bytes'] == 1024
    assert stage_record.metadata['operator_summary']['operator'] == 'continuum_hex8'
    assert stage_record.metadata['linear_system_diagnostics']['actual_matrix_storage_bytes'] == 768
    assert stage_record.metadata['linear_system_diagnostics'].get('actual_global_rhs_size') is None or isinstance(
        stage_record.metadata['linear_system_diagnostics'].get('actual_global_rhs_size'),
        int,
    )
