from __future__ import annotations

import json

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.cli import main
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import (
    AnalysisCaseBuilder,
    InterfaceGeneratorSpec,
    build_preprocessor_snapshot,
    compute_interface_face_elements,
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


def test_interface_face_elements_exist_after_auto_split() -> None:
    prepared = AnalysisCaseBuilder(_build_auto_split_case()).build()
    snapshot = compute_interface_face_elements(prepared.model)
    assert snapshot.metadata['n_elements'] > 0
    assert snapshot.metadata['n_groups'] > 0
    first = snapshot.elements[0]
    assert len(first.slave_point_ids) == len(first.master_point_ids)
    assert tuple(first.slave_point_ids) != tuple(first.master_point_ids)


def test_preprocessor_snapshot_includes_interface_face_elements() -> None:
    artifact = build_preprocessor_snapshot(_build_auto_split_case())
    payload = artifact.snapshot.to_dict()
    assert payload['metadata']['n_interface_face_elements'] > 0
    assert payload['interface_face_groups']
    assert payload['interface_face_elements']


def test_cli_interface_elements_case_outputs_face_preview(tmp_path, capsys) -> None:
    case_path = save_case_spec(_build_auto_split_case(), tmp_path / 'pit_case_interface_faces.json')
    main(['interface-elements-case', str(case_path)])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload['metadata']['n_elements'] > 0
    assert payload['interface_face_groups']
    assert payload['summary']['interface_ready_applied'] is True
