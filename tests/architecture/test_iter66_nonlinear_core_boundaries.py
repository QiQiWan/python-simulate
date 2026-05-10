from __future__ import annotations

from pathlib import Path


def test_nonlinear_contracts_are_dependency_light() -> None:
    text = Path("src/geoai_simkit/contracts/nonlinear.py").read_text(encoding="utf-8")
    forbidden = ("PySide6", "pyvista", "warp", "geoai_simkit.app", "geoai_simkit.geoproject", "geoai_simkit.solver")
    assert not any(token in text for token in forbidden)


def test_nonlinear_core_has_no_gui_or_runtime_dependencies() -> None:
    text = Path("src/geoai_simkit/solver/nonlinear_core.py").read_text(encoding="utf-8")
    forbidden = ("PySide6", "pyvista", "warp", "geoai_simkit.app", "runtime_solver", "geoproject.runtime_solver")
    assert not any(token in text for token in forbidden)


def test_staged_backend_catalog_mentions_nonlinear_core_contract() -> None:
    from geoai_simkit.solver.backend_registry import solver_backend_capabilities

    staged = [row for row in solver_backend_capabilities() if row["key"] == "staged_mohr_coulomb_cpu"][0]
    plugin = staged["capabilities"]
    features = set(plugin["features"])
    assert "nonlinear_solver_core_v1" in features
    assert plugin["metadata"]["contract"] == "staged_mohr_coulomb_boundary_v2"
