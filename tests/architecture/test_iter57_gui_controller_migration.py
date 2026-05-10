from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "geoai_simkit"
CONTROLLERS = ROOT / "app" / "controllers"


def _text(name: str) -> str:
    return (CONTROLLERS / name).read_text(encoding="utf-8")


def test_new_gui_action_controllers_do_not_import_implementation_internals() -> None:
    banned = (
        "from geoai_simkit.solver",
        "import geoai_simkit.solver",
        "from geoai_simkit.geometry",
        "import geoai_simkit.geometry",
        "from geoai_simkit.geoproject",
        "import geoai_simkit.geoproject",
        "from geoai_simkit.pipeline",
        "import geoai_simkit.pipeline",
        "from PySide6",
        "import PySide6",
        "import pyvista",
    )
    for name in ["project_actions.py", "mesh_actions.py", "stage_actions.py", "solver_actions.py", "result_actions.py"]:
        text = _text(name)
        for needle in banned:
            assert needle not in text, f"{name} imports banned implementation detail: {needle}"


def test_gui_action_controllers_are_importable_and_headless() -> None:
    from geoai_simkit.app.controllers import (
        MeshActionController,
        ProjectActionController,
        ResultActionController,
        SolverActionController,
        StageActionController,
    )
    from geoai_simkit.modules import document_model

    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="controller-smoke")
    assert ProjectActionController(project).resource_summary()["snapshot"]["name"] == "controller-smoke"
    assert isinstance(MeshActionController(project).summary(), dict)
    assert StageActionController(project).summary()["stage_count"] >= 1
    assert "linear_static_cpu" in SolverActionController(project).supported_backends()
    assert ResultActionController(project).summary()["stage_count"] >= 0
