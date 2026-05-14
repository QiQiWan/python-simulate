from pathlib import Path


def test_new_gui_workbench_contracts_are_dependency_light():
    root = Path("src/geoai_simkit/contracts")
    text = (root / "gui_workflow.py").read_text() + (root / "viewport.py").read_text()
    forbidden = ["PySide6", "pyvista", "gmsh", "meshio", "geoai_simkit.solver", "geoai_simkit.geometry"]
    assert not any(item in text for item in forbidden)
    assert "Any" not in text


def test_phase_service_and_tool_runtime_are_headless():
    files = [
        Path("src/geoai_simkit/services/workbench_phase_service.py"),
        Path("src/geoai_simkit/app/viewport/tool_runtime.py"),
        Path("src/geoai_simkit/app/viewport/pick_adapter.py"),
        Path("src/geoai_simkit/app/viewport/preview_overlay.py"),
        Path("src/geoai_simkit/app/controllers/workbench_phase_actions.py"),
    ]
    forbidden = ["from PySide6", "import PySide6", "import pyvista", "from pyvista", "import vtk", "from vtk", "import gmsh", "import meshio", "geoai_simkit.solver.runtime_solver"]
    for path in files:
        text = path.read_text()
        assert not any(item in text for item in forbidden), path


def test_main_window_remains_thin_entrypoint():
    path = Path("src/geoai_simkit/app/main_window.py")
    assert len(path.read_text().splitlines()) < 100
