
from __future__ import annotations

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import AnalysisCaseBuilder, compute_region_surface_interface_candidates


def test_surface_interface_candidates_include_wall_to_soil_pairs() -> None:
    prepared = AnalysisCaseBuilder(build_demo_case()).build()
    candidates = compute_region_surface_interface_candidates(
        prepared.model,
        left_region_names=('wall',),
        right_region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'),
        min_shared_faces=4,
    )
    assert candidates
    assert any(item.region_a == 'wall' and item.region_b.startswith('soil_') for item in candidates)
    assert max(item.shared_face_count for item in candidates) >= 4
