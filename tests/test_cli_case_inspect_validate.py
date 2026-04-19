from __future__ import annotations

import json

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.cli import build_parser, main


def test_cli_parser_supports_inspect_and_validate_commands() -> None:
    parser = build_parser()
    args = parser.parse_args(['inspect-case', 'demo.json'])
    assert args.cmd == 'inspect-case'
    args = parser.parse_args(['validate-case', 'demo.json'])
    assert args.cmd == 'validate-case'
    args = parser.parse_args(['topology-case', 'demo.json'])
    assert args.cmd == 'topology-case'


def test_inspect_and_validate_case_commands(tmp_path, capsys) -> None:
    case_path = tmp_path / 'pit_case.json'
    main(['export-demo-case', '--out', str(case_path)])
    main(['inspect-case', str(case_path)])
    inspect_out = capsys.readouterr().out.strip()
    inspect_payload = json.loads(inspect_out[inspect_out.find('{'):])
    assert inspect_payload['case_name'] == 'pit-demo'
    assert 'wall' in inspect_payload['regions']
    assert len(inspect_payload['structures']) > 0
    main(['validate-case', str(case_path)])
    validate_out = capsys.readouterr().out.strip()
    validate_payload = json.loads(validate_out[validate_out.find('{'):])
    assert validate_payload['ok'] is True
    assert validate_payload['summary']['n_regions'] > 0
    assert validate_payload['summary']['n_structures'] > 0


def test_topology_case_command_outputs_summary(tmp_path, capsys) -> None:
    case_path = tmp_path / 'pit_case.json'
    main(['export-demo-case', '--out', str(case_path)])
    main(['topology-case', str(case_path)])
    topo_out = capsys.readouterr().out.strip()
    topo_payload = json.loads(topo_out[topo_out.find('{'):])
    assert 'metadata' in topo_payload
    assert 'interfaces' in topo_payload
