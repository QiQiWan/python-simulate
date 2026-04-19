
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
    compute_region_boundary_surfaces,
    compute_region_surface_interface_candidates,
    region_surface_summary_rows,
    save_case_spec,
)


def test_region_boundary_surfaces_exist_for_demo_case() -> None:
    prepared = AnalysisCaseBuilder(build_demo_case()).build()
    surfaces = compute_region_boundary_surfaces(prepared.model)
    assert len(surfaces) >= 4
    wall = next(item for item in surfaces if item.region_name == 'wall')
    assert wall.face_count > 0
    assert wall.interface_face_count > 0


def test_preprocessor_snapshot_reports_surface_and_candidate_counts() -> None:
    artifact = build_preprocessor_snapshot(build_demo_case())
    payload = artifact.snapshot.to_dict()
    assert payload['metadata']['n_region_surfaces'] >= 4
    assert payload['metadata']['n_interface_candidates'] >= 1
    assert len(payload['region_surfaces']) == payload['metadata']['n_region_surfaces']


def test_cli_preprocess_case_outputs_snapshot(tmp_path, capsys) -> None:
    case_path = save_case_spec(build_demo_case(), tmp_path / 'pit_case.json')
    main(['preprocess-case', str(case_path)])
    captured = capsys.readouterr().out.strip()
    payload = json.loads(captured[captured.find('{'):])
    assert payload['case_name'] == 'pit-demo'
    assert payload['metadata']['n_region_surfaces'] >= 4
    assert payload['metadata']['n_interface_candidates'] >= 1


def test_surface_boundary_interface_generator_is_registered_and_generates_interfaces() -> None:
    spec = build_demo_case()
    spec.interfaces = (
        InterfaceGeneratorSpec(
            kind='surface_boundary_adjacent_contact_pairs',
            parameters={
                'name': 'wall_surface_contact',
                'left_region': 'wall',
                'right_selector': {'patterns': ('soil*',)},
                'min_shared_faces': 4,
                'search_radius_factor': 2.25,
            },
        ),
    )
    prepared = AnalysisCaseBuilder(spec).build()
    assert prepared.report.metadata['n_interfaces'] > 0
    assert any(item.metadata.get('surface_candidate_generated_by') == 'pipeline.surface_boundary_adjacent_contact_pairs' for item in prepared.model.interfaces)


def test_cli_export_preprocess_writes_file(tmp_path, capsys) -> None:
    case_path = save_case_spec(build_demo_case(), tmp_path / 'pit_case.json')
    out_path = tmp_path / 'preprocess_snapshot.json'
    main(['export-preprocess', str(case_path), '--out', str(out_path)])
    written = out_path.read_text(encoding='utf-8')
    payload = json.loads(written)
    assert payload['case_name'] == 'pit-demo'
    assert payload['metadata']['n_boundary_adjacencies'] >= 1
