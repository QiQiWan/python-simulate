from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from geoai_simkit.app.job_service import JobRunSummary
from geoai_simkit.app.workbench import WorkbenchService
from geoai_simkit.cli import main
from geoai_simkit.core.types import ResultField
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.results import ResultDatabase, StageResultRecord


def test_workbench_service_can_edit_blocks_and_stages(tmp_path: Path):
    service = WorkbenchService()
    document = service.document_from_case(build_demo_case(), mode='assign')
    service.set_block_material(document, 'soil_mass', 'debug_soil')
    service.set_block_flags(document, 'soil_mass', visible=False, locked=True)
    service.add_stage(document, 'custom_excavate', copy_from='excavate_level_2')
    service.set_stage_region_state(document, 'custom_excavate', 'wall', True)
    document = service.refresh_document(document)

    soil_mass = next(item for item in document.browser.blocks if item.name == 'soil_mass')
    assert soil_mass.material_name == 'debug_soil'
    assert soil_mass.visible is False
    assert soil_mass.locked is True
    assert 'custom_excavate' in [row.name for row in document.browser.stage_rows]
    assert service.stage_region_state(document, 'custom_excavate', 'wall') is True

    saved = service.save_document(document, tmp_path / 'edited_case.json')
    reloaded = service.load_document(saved)
    soil_mass_reloaded = next(item for item in reloaded.browser.blocks if item.name == 'soil_mass')
    assert soil_mass_reloaded.material_name == 'debug_soil'
    assert soil_mass_reloaded.visible is False
    assert soil_mass_reloaded.locked is True
    assert 'custom_excavate' in [row.name for row in reloaded.browser.stage_rows]


def test_cli_workbench_edit_case_applies_mutations(tmp_path: Path, capsys):
    source = tmp_path / 'demo_case.json'
    out = tmp_path / 'edited_case.json'
    from geoai_simkit.pipeline.io import save_case_spec

    save_case_spec(build_demo_case(), source)
    main([
        'workbench-edit-case',
        str(source),
        '--out', str(out),
        '--set-material', 'soil_mass=edited_soil',
        '--set-visibility', 'soil_mass=false',
        '--set-locked', 'soil_mass=true',
        '--add-stage', 'custom_stage',
        '--set-stage-active', 'custom_stage:wall=true',
        '--mesh-size', '1.25',
    ])
    payload = json.loads(capsys.readouterr().out)
    assert payload['saved_to'] == str(out)
    assert 'custom_stage' in payload['browser']['stage_names']
    soil_mass = next(item for item in payload['browser']['blocks'] if item['name'] == 'soil_mass')
    assert soil_mass['material_name'] == 'edited_soil'
    assert soil_mass['visible'] is False
    assert soil_mass['locked'] is True


def test_cli_workbench_run_case_uses_result_database(monkeypatch, tmp_path: Path, capsys):
    from geoai_simkit.pipeline.io import save_case_spec
    from geoai_simkit.app import job_service as job_service_module

    source = tmp_path / 'demo_case.json'
    save_case_spec(build_demo_case(), source)

    def fake_run_case(self, case, out_dir, *, execution_profile='auto', device=None, export_stage_series=True):
        db = ResultDatabase(
            model_name=case.name,
            fields=(ResultField(name='U', association='point', values=np.zeros((1, 3)), components=3, stage='initial'),),
            stages=(
                StageResultRecord(
                    stage_name='initial',
                    fields=(ResultField(name='U', association='point', values=np.zeros((1, 3)), components=3, stage='initial'),),
                    metadata={
                        'stage_asset': {'stage_name': 'initial'},
                        'linear_system_diagnostics': {
                            'stage_name': 'initial',
                            'actual_matrix_storage_bytes': 128,
                            'consistency_level': 'global-actual-partition-estimated',
                            'ok': True,
                        },
                    },
                ),
            ),
            metadata={
                'stage_asset_count': 1,
                'stage_linear_system_plans': [{'stage_name': 'initial'}],
                'stage_linear_system_diagnostics_count': 1,
                'linear_system_diagnostics_summary': {'stage_count': 1},
            },
        )
        return JobRunSummary(
            case_name=case.name,
            profile=execution_profile,
            device=device or 'cpu',
            out_path=Path(out_dir) / f'{case.name}.vtu',
            stage_count=1,
            field_count=1,
            result_db=db,
            metadata={},
        )

    monkeypatch.setattr(job_service_module.JobService, 'run_case', fake_run_case)
    main(['workbench-run-case', str(source), '--out-dir', str(tmp_path / 'exports'), '--execution-profile', 'cpu-robust', '--device', 'cpu'])
    payload = json.loads(capsys.readouterr().out)
    assert payload['run']['result_stage_count'] == 1
    assert payload['run']['stage_asset_count'] == 0
    assert payload['results']['field_count'] == 1
    assert payload['results']['stage_asset_count'] == 1
    assert payload['results']['stage_linear_system_plan_count'] == 1
    assert payload['results']['stage_linear_system_diagnostics_count'] == 1
    assert payload['results']['linear_system_diagnostics_summary']['stage_count'] == 1
    assert payload['results']['stage_metadata'][0]['linear_system_consistency_level'] == 'global-actual-partition-estimated'
    assert payload['job_plan']['device'] == 'cpu'



def test_workbench_service_can_set_stage_predecessor():
    service = WorkbenchService()
    document = service.document_from_case(build_demo_case(), mode='stage')
    service.set_stage_predecessor(document, 'excavate_level_2', 'wall_activation')
    document = service.refresh_document(document)
    row = next(item for item in document.browser.stage_rows if item.name == 'excavate_level_2')
    assert row.predecessor == 'wall_activation'
