from geoai_simkit.core.model import GeometryObjectRecord, SimulationModel


class DummyMesh:
    n_cells = 0
    n_points = 0


def test_object_visibility_flags_roundtrip():
    model = SimulationModel(name="m", mesh=DummyMesh(), object_records=[
        GeometryObjectRecord(key="a", name="A", object_type="IfcWall"),
        GeometryObjectRecord(key="b", name="B", object_type="IfcBeam"),
    ])
    model.set_object_visibility(["a"], False)
    assert model.object_record("a").visible is False
    assert model.object_record("a").pickable is False
    assert "a" not in model.visible_object_keys()
    model.set_object_visibility(["a"], True, pickable=False)
    assert model.object_record("a").visible is True
    assert model.object_record("a").pickable is False
    model.show_all_objects()
    assert model.pickable_object_keys() == {"a", "b"}


def test_object_lock_disables_picking_until_unlocked():
    model = SimulationModel(name="m", mesh=DummyMesh(), object_records=[
        GeometryObjectRecord(key="a", name="A", object_type="IfcWall"),
        GeometryObjectRecord(key="b", name="B", object_type="IfcBeam"),
    ])
    model.set_object_locked(["a"], True)
    assert model.object_record("a").locked is True
    assert model.object_record("a").pickable is False
    assert model.pickable_object_keys() == {"b"}
    model.show_all_objects()
    assert model.object_record("a").visible is True
    assert model.object_record("a").pickable is False
    model.set_object_locked(["a"], False)
    assert model.object_record("a").locked is False
    assert model.object_record("a").pickable is True
