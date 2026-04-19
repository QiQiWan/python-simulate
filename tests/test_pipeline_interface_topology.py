from __future__ import annotations

import json

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.cli import main
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import (
    AnalysisCaseBuilder,
    AnalysisCaseValidator,
    InterfaceGeneratorSpec,
    analyze_interface_topology,
    build_preprocessor_snapshot,
    save_case_spec,
)


def _build_case_with_raw_wall_interface():
    spec = build_demo_case()
    spec.interfaces = (
        InterfaceGeneratorSpec(
            kind='boundary_adjacent_region_contact_pairs',
            parameters={
                'name': 'wall_contact_raw',
                'left_region': 'wall',
                'right_selector': {'patterns': ('soil*',)},
                'min_shared_faces': 4,
                'avoid_identical_pairs': False,
            },
        ),
    )
    return spec


def test_interface_topology_detects_split_plan_for_identical_pairs() -> None:
    prepared = AnalysisCaseBuilder(_build_case_with_raw_wall_interface()).build()
    topology = analyze_interface_topology(prepared.model)
    assert topology.metadata['n_split_plans'] >= 1
    assert any(item.reason == 'identical_slave_master_pairs' for item in topology.split_plans)


def test_preprocessor_snapshot_includes_interface_topology_metadata() -> None:
    artifact = build_preprocessor_snapshot(build_demo_case())
    payload = artifact.snapshot.to_dict()
    assert 'interface_topology' in payload
    assert 'node_split_plans' in payload
    assert 'n_node_split_plans' in payload['metadata']


def test_validator_warns_when_interface_node_split_is_recommended() -> None:
    report = AnalysisCaseValidator(_build_case_with_raw_wall_interface()).validate()
    assert any(item.code == 'interface_node_split_recommended' for item in report.issues)


def test_cli_topology_case_outputs_split_plan_summary(tmp_path, capsys) -> None:
    case_path = save_case_spec(_build_case_with_raw_wall_interface(), tmp_path / 'pit_case_raw_interface.json')
    main(['topology-case', str(case_path)])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload['metadata']['n_interfaces'] >= 1
    assert 'split_plans' in payload
