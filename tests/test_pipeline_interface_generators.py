from __future__ import annotations

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.examples.pit_example import build_demo_case, build_demo_model
from geoai_simkit.pipeline import AnalysisCaseBuilder, AnalysisCaseSpec, AnalysisCaseValidator, GeometrySource, InterfaceGeneratorSpec, MeshAssemblySpec, MaterialAssignmentSpec, case_spec_from_dict, case_spec_to_dict, registered_interface_generators


def test_registered_interface_generators_include_demo_and_generic_contact() -> None:
    names = set(registered_interface_generators())
    assert {'contact_pair', 'selector_contact_pairs', 'demo_wall_interfaces'}.issubset(names)


def test_demo_case_generates_interfaces_via_pipeline() -> None:
    prepared = AnalysisCaseBuilder(build_demo_case()).build()
    assert prepared.report.metadata['n_interfaces'] > 0
    assert prepared.report.metadata['n_generated_interfaces'] > 0
    assert any(item.metadata.get('source') == 'parametric_pit_auto_wall' for item in prepared.model.interfaces)


def test_case_roundtrip_preserves_interface_generator_specs() -> None:
    spec = build_demo_case()
    payload = case_spec_to_dict(spec)
    restored = case_spec_from_dict(payload)
    assert isinstance(restored.interfaces[0], InterfaceGeneratorSpec)
    assert restored.interfaces[0].kind == 'demo_wall_interfaces'


def test_validator_reports_unknown_interface_generator() -> None:
    spec = build_demo_case()
    spec.interfaces = (InterfaceGeneratorSpec(kind='missing_interface_generator'),)
    report = AnalysisCaseValidator(spec).validate()
    codes = {issue.code for issue in report.issues}
    assert 'interface_generator' in codes
    assert report.ok is False


def test_single_contact_pair_generator_builds_interface_on_meshed_model() -> None:
    demo_model = build_demo_model()
    case = AnalysisCaseSpec(
        name='contact-generator-case',
        geometry=GeometrySource(data=demo_model.mesh),
        mesh=MeshAssemblySpec(merge_points=True),
        materials=(
            MaterialAssignmentSpec(region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'), material_name='linear_elastic', parameters={'E': 1e7, 'nu': 0.3}),
            MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E': 3e10, 'nu': 0.2}),
        ),
        interfaces=(InterfaceGeneratorSpec(kind='contact_pair', parameters={'name': 'wall_to_soil_gen', 'slave_region': 'wall', 'master_region': 'soil_mass', 'active_stages': ('initial', 'wall_activation')}),),
    )
    prepared = AnalysisCaseBuilder(case).build()
    iface = next((item for item in prepared.model.interfaces if item.name == 'wall_to_soil_gen'), None)
    assert iface is not None
    assert len(iface.slave_point_ids) == len(iface.master_point_ids)
    assert len(iface.slave_point_ids) > 0
