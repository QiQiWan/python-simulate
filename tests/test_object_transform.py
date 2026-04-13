import pytest

pv = pytest.importorskip('pyvista')

from geoai_simkit.core.model import SimulationModel, GeometryObjectRecord


def test_translate_object_blocks_moves_selected_block_points():
    cube = pv.Cube().triangulate()
    mb = pv.MultiBlock({'blk': cube.copy()})
    model = SimulationModel(name='m', mesh=mb)
    model.object_records = [GeometryObjectRecord(key='o1', name='obj', object_type='IfcWall', source_block='blk')]
    p0 = mb['blk'].points.copy()
    moved = model.translate_object_blocks(['o1'], (1.0, 2.0, -0.5))
    assert moved == 1
    p1 = mb['blk'].points
    assert ((p1 - p0)[0] == pytest.approx([1.0, 2.0, -0.5])).all()
