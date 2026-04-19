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


def _build_auto_split_case():
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
    spec.mesh_preparation.interface_node_split_mode = 'auto'
    spec.mesh_preparation.interface_duplicate_side = 'slave'
    return spec


def test_interface_ready_preprocessing_remaps_raw_interfaces() -> None:
    prepared = AnalysisCaseBuilder(_build_auto_split_case()).build()
    report = dict(prepared.model.metadata.get('pipeline.interface_ready') or {})
    assert report.get('applied') is True
    assert report.get('duplicated_point_count', 0) > 0
    topology = analyze_interface_topology(prepared.model)
    assert len(topology.split_plans) == 0
    assert all(not any(int(s) == int(m) for s, m in zip(item.slave_point_ids, item.master_point_ids, strict=False)) for item in prepared.model.interfaces)


def test_validator_no_longer_warns_after_auto_interface_ready() -> None:
    report = AnalysisCaseValidator(_build_auto_split_case()).validate()
    assert not any(item.code == 'interface_node_split_recommended' for item in report.issues)
    assert report.summary['interface_ready_applied'] is True


def test_preprocessor_snapshot_includes_interface_ready_metadata() -> None:
    artifact = build_preprocessor_snapshot(_build_auto_split_case())
    payload = artifact.snapshot.to_dict()
    assert payload['interface_ready']['applied'] is True
    assert payload['metadata']['interface_ready_applied'] is True


def test_cli_interface_ready_case_reports_applied_split(tmp_path, capsys) -> None:
    case_path = save_case_spec(_build_auto_split_case(), tmp_path / 'pit_case_interface_ready.json')
    main(['interface-ready-case', str(case_path)])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload['interface_ready']['applied'] is True
    assert payload['summary']['interface_ready_applied'] is True
