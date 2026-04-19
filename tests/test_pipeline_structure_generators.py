from __future__ import annotations

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import AnalysisCaseBuilder, AnalysisCaseValidator, StructureGeneratorSpec, case_spec_from_dict, case_spec_to_dict, registered_structure_generators


def test_registered_structure_generators_include_demo_supports() -> None:
    assert 'demo_pit_supports' in registered_structure_generators()


def test_demo_case_generates_support_structures_via_pipeline() -> None:
    prepared = AnalysisCaseBuilder(build_demo_case()).build()
    names = {item.metadata.get('support_group') for item in prepared.model.structures}
    assert prepared.report.metadata['n_structures'] > 0
    assert prepared.report.metadata['n_generated_structures'] > 0
    assert {'crown_beam', 'strut_level_1', 'strut_level_2'}.issubset(names)


def test_case_roundtrip_preserves_structure_generator_specs() -> None:
    spec = build_demo_case()
    payload = case_spec_to_dict(spec)
    restored = case_spec_from_dict(payload)
    assert isinstance(restored.structures[0], StructureGeneratorSpec)
    assert restored.structures[0].kind == 'demo_pit_supports'


def test_validator_reports_unknown_structure_generator() -> None:
    spec = build_demo_case()
    spec.structures = (StructureGeneratorSpec(kind='missing_generator'),)
    report = AnalysisCaseValidator(spec).validate()
    codes = {issue.code for issue in report.issues}
    assert 'structure_generator' in codes
    assert report.ok is False
