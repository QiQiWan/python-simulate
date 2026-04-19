from __future__ import annotations

import json

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.cli import main
from geoai_simkit.examples.pit_example import build_demo_case, build_demo_model
from geoai_simkit.pipeline import (
    AnalysisCaseBuilder,
    AnalysisCaseSpec,
    AnalysisCaseValidator,
    GeometrySource,
    InterfaceGeneratorSpec,
    MaterialAssignmentSpec,
    MeshAssemblySpec,
    RegionSelectorSpec,
    compute_region_boundary_adjacency,
    registered_interface_generators,
    save_case_spec,
)


def test_registered_interface_generators_include_boundary_adjacency_generator() -> None:
    names = set(registered_interface_generators())
    assert 'boundary_adjacent_region_contact_pairs' in names



def test_compute_region_boundary_adjacency_finds_demo_wall_neighbors() -> None:
    model = build_demo_model()
    adjacencies = compute_region_boundary_adjacency(model, min_shared_faces=1)
    pairs = {(item.region_a, item.region_b) for item in adjacencies}
    assert ('soil_mass', 'wall') in pairs or ('wall', 'soil_mass') in pairs
    assert any(item.shared_face_count >= 6 for item in adjacencies)
    assert any(item.shared_face_area > 0.0 for item in adjacencies)



def test_boundary_adjacency_generator_builds_interfaces_from_demo_regions() -> None:
    demo_model = build_demo_model()
    case = AnalysisCaseSpec(
        name='boundary-adjacency-generator-case',
        geometry=GeometrySource(data=demo_model.mesh),
        mesh=MeshAssemblySpec(merge_points=True),
        materials=(
            MaterialAssignmentSpec(region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'), material_name='linear_elastic', parameters={'E': 1e7, 'nu': 0.3}),
            MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E': 3e10, 'nu': 0.2}),
        ),
        interfaces=(
            InterfaceGeneratorSpec(
                kind='boundary_adjacent_region_contact_pairs',
                parameters={
                    'name': 'bnd_adj',
                    'left_region': 'wall',
                    'right_selector': RegionSelectorSpec(patterns=('soil_*',)),
                    'active_stages': ('wall_activation',),
                    'min_shared_faces': 1,
                    'avoid_identical_pairs': True,
                },
            ),
        ),
    )
    prepared = AnalysisCaseBuilder(case).build()
    assert len(prepared.model.interfaces) >= 1
    assert all(item.metadata.get('boundary_adjacency_shared_face_count', 0) >= 1 for item in prepared.model.interfaces)
    assert all(item.metadata.get('slave_subset_size', 0) > 0 for item in prepared.model.interfaces)
    assert all(item.metadata.get('master_subset_size', 0) > 0 for item in prepared.model.interfaces)



def test_cli_adjacency_case_supports_face_mode(tmp_path, capsys) -> None:
    case_path = save_case_spec(build_demo_case(), tmp_path / 'pit_case.json')
    main(['adjacency-case', str(case_path), '--mode', 'faces', '--min-shared-points', '1'])
    captured = capsys.readouterr().out.strip()
    payload = json.loads(captured[captured.find('{'):])
    assert payload['case_name'] == 'pit-demo'
    assert payload['adjacency_mode'] == 'faces'
    assert payload['adjacency_count'] > 0
    assert any(
        {'region_a', 'region_b', 'shared_face_count', 'shared_face_area'}.issubset(set(row))
        for row in payload['adjacencies']
    )



def test_validator_summary_includes_boundary_adjacency_count() -> None:
    report = AnalysisCaseValidator(build_demo_case()).validate()
    assert report.summary['n_boundary_adjacencies'] > 0
