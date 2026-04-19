from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip('pyvista')
import pyvista as pv

from geoai_simkit.core.model import RegionTag, SimulationModel
from geoai_simkit.pipeline import StructureGeneratorSpec, registered_structure_generators
from geoai_simkit.pipeline.structures import resolve_registered_structure_generator


def _line_model() -> SimulationModel:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    cells = np.hstack([[4, 0, 1, 2, 3]])
    celltypes = np.array([pv.CellType.QUAD], dtype=np.uint8)
    grid = pv.UnstructuredGrid(cells, celltypes, points)
    return SimulationModel(name='line-structure-case', mesh=grid, region_tags=[RegionTag(name='support_line', cell_ids=np.array([0], dtype=np.int64))])


def test_registered_structure_generators_include_generic_variants() -> None:
    names = set(registered_structure_generators())
    assert {'region_point_chain', 'region_extreme_pair'}.issubset(names)


def test_region_point_chain_generator_builds_consecutive_trusses() -> None:
    model = _line_model()
    items = resolve_registered_structure_generator('region_point_chain', model, {'region_names': ['support_line'], 'element_kind': 'truss2', 'name_prefix': 'strut'})
    assert [item.name for item in items] == ['strut_001', 'strut_002', 'strut_003']
    assert [item.point_ids for item in items] == [(0, 1), (1, 2), (2, 3)]


def test_region_extreme_pair_generator_picks_outermost_points() -> None:
    model = _line_model()
    items = resolve_registered_structure_generator('region_extreme_pair', model, {'region_names': ['support_line'], 'sort_axis': 'x', 'name': 'span'})
    assert len(items) == 1
    assert items[0].name == 'span'
    assert items[0].point_ids == (0, 3)
