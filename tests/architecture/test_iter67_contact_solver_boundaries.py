from __future__ import annotations

from pathlib import Path


def test_contact_contracts_are_dependency_light() -> None:
    text = Path("src/geoai_simkit/contracts/contact.py").read_text(encoding="utf-8")
    forbidden = ("PySide6", "pyvista", "warp", "geoai_simkit.app", "geoai_simkit.geoproject", "geoai_simkit.solver")
    assert not any(token in text for token in forbidden)


def test_contact_core_has_no_gui_or_runtime_solver_dependencies() -> None:
    text = Path("src/geoai_simkit/solver/contact_core.py").read_text(encoding="utf-8")
    forbidden = ("PySide6", "pyvista", "warp", "geoai_simkit.app", "runtime_solver", "geoproject.runtime_solver")
    assert not any(token in text for token in forbidden)


def test_contact_backend_catalog_mentions_contact_solver_contract() -> None:
    from geoai_simkit.solver.backend_registry import solver_backend_capabilities

    contact = [row for row in solver_backend_capabilities() if row["key"] == "contact_interface_cpu"][0]
    plugin = contact["capabilities"]
    features = set(plugin["features"])
    assert "contact_interface_solver_v1" in features
    assert "stick_slip" in features
    assert plugin["metadata"]["contract"] == "contact_interface_solver_v1"


def test_geotechnical_facade_exports_contact_report_without_gui_dependency() -> None:
    text = Path("src/geoai_simkit/modules/geotechnical.py").read_text(encoding="utf-8")
    assert "def contact_report" in text
    assert "PySide6" not in text
    assert "pyvista" not in text
