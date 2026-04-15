from __future__ import annotations

import pytest

pv = pytest.importorskip('pyvista')

from geoai_simkit.geometry.parametric import ParametricPitScene


def test_parametric_pit_scene_builds_split_excavation_regions() -> None:
    scene = ParametricPitScene(length=24.0, width=12.0, depth=12.0, soil_depth=20.0, nx=8, ny=6, nz=6, wall_thickness=0.6)
    mesh = scene.build()
    keys = set(mesh.keys())
    assert {'soil_mass', 'soil_excavation_1', 'soil_excavation_2', 'retaining_wall'} <= keys
    assert mesh['soil_mass'].n_cells > 0
    assert mesh['soil_excavation_1'].n_cells > 0
    assert mesh['soil_excavation_2'].n_cells > 0
    assert mesh['retaining_wall'].n_cells > 0
