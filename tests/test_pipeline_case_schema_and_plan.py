from __future__ import annotations

import json

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.cli import main
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.pipeline import (
    CASE_FILE_KIND,
    CASE_FORMAT_VERSION,
    AnalysisCaseSpec,
    BoundaryConditionSpec,
    GeometrySource,
    MaterialAssignmentSpec,
    MeshAssemblySpec,
    MeshPreparationSpec,
    ExcavationStepSpec,
    case_spec_from_dict,
    case_spec_to_dict,
    save_case_spec,
)


def test_case_payload_includes_schema_metadata() -> None:
    payload = case_spec_to_dict(build_demo_case())
    assert payload['case_file_kind'] == CASE_FILE_KIND
    assert payload['case_format_version'] == CASE_FORMAT_VERSION


def test_case_loader_rejects_unknown_future_version() -> None:
    payload = case_spec_to_dict(build_demo_case())
    payload['case_format_version'] = 999
    with pytest.raises(ValueError):
        case_spec_from_dict(payload)


def test_cli_plan_case_outputs_execution_summary(tmp_path, capsys) -> None:
    case_path = save_case_spec(build_demo_case(), tmp_path / 'pit_case.json')
    main(['plan-case', str(case_path), '--execution-profile', 'cpu-debug', '--checkpoint-every', '2', '--max-cutbacks', '6', '--max-stage-retries', '1'])
    captured = capsys.readouterr().out.strip()
    payload = json.loads(captured[captured.find('{'):])
    assert payload['case_name'] == 'pit-demo'
    assert payload['execution_plan']['profile'] == 'cpu-debug'
    assert payload['execution_plan']['checkpoint']['checkpoint_every_n_increments'] == 2
    assert payload['execution_plan']['failure_policy']['max_cutbacks'] == 6
    assert payload['execution_plan']['failure_policy']['max_stage_retries'] == 1
    assert payload['compile']['metadata']['partition_verify_ok'] is True
    assert payload['compile']['partition_advisory']['current_partition_count'] >= 1
    assert 'stage_execution_diagnostics' in payload['compile']
    assert 'stage_linear_system_plans' in payload['compile']
    assert 'linear_system_partition_estimates' in payload['compile']
    assert 'summary' in payload and payload['summary']['n_regions'] > 0


def test_cli_partition_case_outputs_partition_diagnostics(tmp_path, capsys) -> None:
    case_path = save_case_spec(build_demo_case(), tmp_path / 'pit_case.json')
    main(['partition-case', str(case_path), '--partition-count', '2'])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload['case_name'] == 'pit-demo'
    assert payload['partition_count'] == 2
    assert payload['partition_verify_ok'] is True
    assert len(payload['gp_states_per_partition']) == 2
    assert len(payload['comm_bytes_per_partition']) == 2
    assert payload['estimated_comm_bytes_per_increment'] >= 0
    assert len(payload['partition_summaries']) == 2
    assert payload['partition_advisory']['current_partition_count'] == 2
    assert 'stage_execution_diagnostics' in payload
    assert len(payload['stage_linear_system_plans']) >= 1
    assert len(payload['linear_system_partition_estimates']) == 2
    assert len(payload['stage_partition_diagnostics']) >= 1
    assert len(payload['stage_partition_diagnostics'][0]['active_cells_per_partition']) == 2
    assert len(payload['stage_partition_diagnostics'][0]['active_owned_nodes_per_partition']) == 2
    assert len(payload['stage_partition_diagnostics'][0]['active_owned_dofs_per_partition']) == 2


def test_cli_compare_partitions_case_validates_linear_continuum_consistency(tmp_path, capsys) -> None:
    scene = ParametricPitScene(length=8.0, width=4.0, depth=4.0, soil_depth=6.0, nx=4, ny=4, nz=4, wall_thickness=0.4)
    params = {'length': scene.length, 'width': scene.width, 'depth': scene.depth, 'soil_depth': scene.soil_depth, 'nx': scene.nx, 'ny': scene.ny, 'nz': scene.nz, 'wall_thickness': scene.wall_thickness}
    case = AnalysisCaseSpec(
        name='linear-continuum-compare',
        geometry=GeometrySource(kind='parametric_pit', parameters=params, metadata={'source': 'parametric_pit'}),
        mesh=MeshAssemblySpec(merge_points=True),
        materials=(
            MaterialAssignmentSpec(region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'), material_name='linear_elastic', parameters={'E': 1.0e7, 'nu': 0.3, 'rho': 1800.0}),
            MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E': 3.0e10, 'nu': 0.2, 'rho': 2500.0}),
        ),
        boundary_conditions=(
            BoundaryConditionSpec(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)),
        ),
        mesh_preparation=MeshPreparationSpec(
            excavation_steps=(
                ExcavationStepSpec(name='wall_activation', activate_regions=('wall',), metadata={'stage_role': 'support-install'}),
                ExcavationStepSpec(name='excavate_level_1', deactivate_regions=('soil_excavation_1',), metadata={'stage_role': 'excavation'}),
                ExcavationStepSpec(name='excavate_level_2', deactivate_regions=('soil_excavation_2',), metadata={'stage_role': 'excavation'}),
            )
        ),
    )
    case_path = save_case_spec(case, tmp_path / 'linear_compare_case.json')

    main(['compare-partitions-case', str(case_path), '--partition-count', '2', '--abs-tol', '1e-8', '--rel-tol', '1e-8'])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload['case_name'] == 'linear-continuum-compare'
    assert payload['baseline_partition_count'] == 1
    assert payload['candidate_partition_count'] == 2
    assert payload['comparison']['ok'] is True
    assert payload['comparison']['max_abs_diff'] <= 1.0e-8
    assert any(item['field_name'] == 'residual' for item in payload['comparison']['field_differences'])
    assert any(item['field_name'] == 'reaction' for item in payload['comparison']['field_differences'])
    assert payload['linear_system_comparison']['ok'] is True
    assert payload['compile']['candidate']['partition_count'] == 2
    assert payload['compile']['candidate']['partition_advisory']['current_partition_count'] == 2
    assert len(payload['compile']['candidate']['stage_partition_diagnostics']) >= 1
    assert len(payload['compile']['candidate']['stage_linear_system_plans']) >= 1
    assert payload['linear_system_comparison']['candidate_summary']['stage_count'] >= 1
    assert payload['linear_system_comparison']['candidate_summary']['stages_with_actual_partition_local_systems_count'] >= 1
    assert payload['linear_system_comparison']['candidate_summary']['actual_global_rhs_size_total'] > 0
    assert payload['linear_system_comparison']['candidate_summary']['stages_with_residual_summary_count'] >= 1
    assert payload['runtime_assembly']['candidate']
    first_stage_meta = next(iter(payload['runtime_assembly']['candidate'].values()))
    assert first_stage_meta['active_node_count'] > 0
    assert 'active_partition_count' in first_stage_meta
    assert first_stage_meta['operator_summary']['linear_system']['rhs_size'] > 0
    assert first_stage_meta['operator_summary']['linear_system']['residual_size'] > 0
