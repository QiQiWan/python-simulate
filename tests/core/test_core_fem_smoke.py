from __future__ import annotations

from geoai_simkit.fem.api import get_core_fem_api_contracts, run_core_fem_api_smoke


def test_core_fem_api_contract_order():
    keys = [item["key"] for item in get_core_fem_api_contracts()]
    assert keys == ["geometry", "mesh", "material", "element", "assembly", "solver", "result"]


def test_core_fem_dependency_light_smoke():
    result = run_core_fem_api_smoke()
    assert result["check_count"] == 7
    assert result["passed_count"] == 7
    assert result["ok"] is True


def test_each_core_facade_exposes_describe_and_smoke():
    from geoai_simkit.fem import geometry, mesh, material, element, assembly, solver, result

    modules = [geometry, mesh, material, element, assembly, solver, result]
    for module in modules:
        api = module.describe_api()
        smoke = module.smoke_check()
        assert api["key"] == smoke["key"]
        assert smoke["ok"] is True
