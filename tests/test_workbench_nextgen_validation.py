from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit.app.workbench import WorkbenchService
from geoai_simkit.cli import main
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline.io import save_case_spec


def test_workbench_document_includes_validation_summary():
    doc = WorkbenchService().document_from_case(build_demo_case(), mode='geometry')
    assert doc.validation is not None
    assert doc.validation.warning_count >= 0
    assert 'n_interfaces' in doc.validation.summary


def test_cli_workbench_case_includes_validation_payload(tmp_path: Path, capsys):
    case_path = tmp_path / 'demo_case.json'
    save_case_spec(build_demo_case(), case_path)
    main(['workbench-case', str(case_path)])
    payload = json.loads(capsys.readouterr().out)
    assert payload['validation']['ok'] is True
    assert 'summary' in payload['validation']


def test_cli_workbench_validate_case_outputs_validation_only(tmp_path: Path, capsys):
    case_path = tmp_path / 'demo_case.json'
    save_case_spec(build_demo_case(), case_path)
    main(['workbench-validate-case', str(case_path)])
    payload = json.loads(capsys.readouterr().out)
    assert payload['case_name'] == 'pit-demo'
    assert payload['validation']['ok'] is True
