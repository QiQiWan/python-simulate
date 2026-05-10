from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "geoai_simkit"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _py_files(package: str) -> list[Path]:
    return sorted((ROOT / package).rglob("*.py"))


def test_contracts_do_not_import_implementation_heavy_packages() -> None:
    forbidden = (
        "geoai_simkit.app",
        "geoai_simkit.solver",
        "geoai_simkit.pipeline",
        "geoai_simkit.geometry",
        "geoai_simkit.mesh",
        "PySide6",
        "pyvista",
        "warp",
    )
    offenders: list[str] = []
    for path in _py_files("contracts"):
        for item in _imports(path):
            if item.startswith(forbidden):
                offenders.append(f"{path.relative_to(ROOT)} imports {item}")
    assert offenders == []


def test_services_do_not_import_gui_or_rendering_frameworks() -> None:
    forbidden = ("PySide6", "pyvista", "pyvistaqt", "warp")
    offenders: list[str] = []
    for path in _py_files("services"):
        for item in _imports(path):
            if item.startswith(forbidden):
                offenders.append(f"{path.relative_to(ROOT)} imports {item}")
    assert offenders == []


def test_solver_and_mesh_do_not_import_app_layer() -> None:
    offenders: list[str] = []
    for package in ("solver", "mesh"):
        for path in _py_files(package):
            for item in _imports(path):
                if item.startswith("geoai_simkit.app"):
                    offenders.append(f"{path.relative_to(ROOT)} imports {item}")
    assert offenders == []
