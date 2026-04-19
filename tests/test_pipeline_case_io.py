from __future__ import annotations

import json

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.examples.general_case import build_general_excavation_case
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import AnalysisCaseBuilder, case_spec_from_dict, case_spec_to_dict, load_case_spec, registered_geometry_sources, registered_structure_generators, save_case_spec


def test_demo_case_roundtrip_dict_preserves_registered_geometry_kind() -> None:
    spec = build_demo_case()
    payload = case_spec_to_dict(spec)
    restored = case_spec_from_dict(payload)
    assert restored.geometry.kind == 'parametric_pit'
    assert restored.geometry.parameters['length'] == spec.geometry.parameters['length']
    assert restored.metadata['boundary_preset'] == spec.metadata['boundary_preset']


def test_general_case_json_roundtrip_prepares_successfully(tmp_path) -> None:
    spec = build_general_excavation_case()
    path = save_case_spec(spec, tmp_path / 'general_case.json')
    restored = load_case_spec(path)
    prepared = AnalysisCaseBuilder(restored).build()
    assert [stage.name for stage in prepared.model.stages] == ['initial', 'wall_activation', 'excavate_level_1', 'excavate_level_2']
    assert prepared.model.metadata['pipeline.case_name'] == 'general-excavation-case'


def test_registered_geometry_sources_include_parametric_pit() -> None:
    assert 'parametric_pit' in registered_geometry_sources()


def test_registered_structure_generators_include_demo_supports() -> None:
    assert 'demo_pit_supports' in registered_structure_generators()



def test_stage_predecessor_roundtrip_preserves_graph_metadata() -> None:
    spec = build_demo_case()
    from geoai_simkit.pipeline import StageSpec

    spec.stages = (
        StageSpec(name='initial', predecessor=None),
        StageSpec(name='wall_activation', predecessor='initial'),
        StageSpec(name='excavate_level_1', predecessor='wall_activation'),
    )
    payload = case_spec_to_dict(spec)
    restored = case_spec_from_dict(payload)
    assert restored.stages[1].predecessor == restored.stages[0].name
    assert payload['case_format_version'] >= 4
