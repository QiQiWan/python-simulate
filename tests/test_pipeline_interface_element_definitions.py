from __future__ import annotations

import json

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.cli import main
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import AnalysisCaseBuilder, InterfaceGeneratorSpec, build_preprocessor_snapshot, save_case_spec


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
    spec.mesh_preparation.interface_element_mode = 'explicit'
    return spec


def test_builder_materializes_explicit_interface_elements() -> None:
    prepared = AnalysisCaseBuilder(_build_auto_split_case()).build()
    assert prepared.model.interface_elements
    first = prepared.model.interface_elements[0]
    assert first.interface_name
    assert first.element_kind in {'line2', 'tria3', 'quad4'} or first.element_kind.startswith('polygon')
    assert len(first.slave_point_ids) == len(first.master_point_ids)
    assert tuple(first.slave_point_ids) != tuple(first.master_point_ids)
    assert prepared.report.metadata['n_interface_elements'] == len(prepared.model.interface_elements)


def test_preprocessor_snapshot_includes_interface_element_definitions() -> None:
    artifact = build_preprocessor_snapshot(_build_auto_split_case())
    payload = artifact.snapshot.to_dict()
    assert payload['metadata']['n_interface_elements'] > 0
    assert payload['interface_element_definitions']
    assert payload['interface_element_definitions'][0]['interface_name']


def test_cli_export_interface_elements_writes_json(tmp_path) -> None:
    case_path = save_case_spec(_build_auto_split_case(), tmp_path / 'pit_case_interface_elements.json')
    out_path = tmp_path / 'interface_elements.json'
    main(['export-interface-elements', str(case_path), '--out', str(out_path)])
    payload = json.loads(out_path.read_text(encoding='utf-8'))
    assert payload['summary']['n_interface_elements'] > 0
    assert payload['interface_elements']


def test_interface_element_mode_off_disables_materialization() -> None:
    spec = _build_auto_split_case()
    spec.mesh_preparation.interface_element_mode = 'off'
    prepared = AnalysisCaseBuilder(spec).build()
    assert prepared.model.interface_elements == []
    assert prepared.report.metadata['n_interface_elements'] == 0
