import json

from geoai_simkit.cli import main
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import StageSpec
from geoai_simkit.pipeline.io import save_case_spec


def test_cli_stage_graph_case_outputs_edges(tmp_path, capsys):
    spec = build_demo_case()
    spec.stages = (
        StageSpec(name='initial', predecessor=None),
        StageSpec(name='wall_activation', predecessor='initial'),
        StageSpec(name='excavate_level_1', predecessor='wall_activation'),
    )
    path = tmp_path / 'stage_graph_case.json'
    save_case_spec(spec, path)
    main(['stage-graph-case', str(path)])
    payload = json.loads(capsys.readouterr().out)
    assert payload['roots'] == ['initial']
    assert {'from': 'initial', 'to': 'wall_activation'} in payload['edges']
