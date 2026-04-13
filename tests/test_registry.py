from geoai_simkit.materials import registry


def test_builtin_materials_registered() -> None:
    available = registry.available()
    assert "linear_elastic" in available
    assert "mohr_coulomb" in available
    assert "hss" in available
