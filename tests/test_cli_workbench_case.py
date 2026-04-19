import json

from geoai_simkit.cli import main
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline.io import save_case_spec


def test_cli_workbench_case_outputs_nextgen_summary(tmp_path, capsys):
    case_path = tmp_path / 'demo_case.json'
    save_case_spec(build_demo_case(), case_path)
    main(['workbench-case', str(case_path)])
    payload = json.loads(capsys.readouterr().out)
    assert payload['case_name'] == 'pit-demo'
    assert 'wall' in payload['browser']['block_names']
    assert payload['preprocess']['n_interface_elements'] >= 1
    assert payload['partition_advisory'] == {}
