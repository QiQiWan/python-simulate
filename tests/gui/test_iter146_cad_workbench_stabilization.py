from pathlib import Path


def test_version_and_single_requirements_file():
    from geoai_simkit._version import __version__

    assert __version__ in {"1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    root = Path(__file__).resolve().parents[2]
    scattered = sorted(p.name for p in root.glob("requirements-*.txt"))
    assert scattered == []
    req = (root / "requirements.txt").read_text(encoding="utf-8")
    for name in ["PySide6", "vtk", "pyvista", "pyvistaqt", "gmsh", "meshio", "cadquery-ocp", "ifcopenshell", "matplotlib", "pytest"]:
        assert name in req


def test_dependency_preflight_checks_all_main_runtime_dependencies():
    from geoai_simkit.services.dependency_preflight import DEFAULT_DEPENDENCIES

    keys = {spec.key for spec in DEFAULT_DEPENDENCIES}
    expected = {
        "numpy", "scipy", "typing_extensions", "pyside6", "qtpy", "vtk", "pyvista", "pyvistaqt",
        "gmsh", "meshio", "ocp", "ifcopenshell", "matplotlib", "pillow", "pooch", "scooby",
        "packaging", "requests", "rich", "pytest",
    }
    assert expected.issubset(keys)
    required = {spec.key for spec in DEFAULT_DEPENDENCIES if spec.required}
    assert expected.issubset(required)


def test_cad_workbench_payload_exposes_stabilization_contract():
    from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload

    payload = build_phase_workbench_qt_payload("geology")
    ux = payload["cad_ux_stabilization"]
    assert ux["persistent_project_state"] is True
    assert ux["flicker_reduction"] is True
    assert ux["tool_activation_does_not_reset_model"] is True
    assert ux["dockable_panels"] is True
    assert ux["floating_toolbars"] is True
    assert payload["geometry_interaction"]["mouse_creation"] is True


def test_phase_workbench_uses_dockable_modern_cad_layout_and_dirty_only_render():
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert "QDockWidget" in source
    assert "addToolBar" in source
    assert "setMovable(True)" in source
    assert "setFloatable(True)" in source
    assert "_last_render_revision" in source
    assert "scene_not_dirty" in source
    assert "tool_activation_does_not_reset_model" in source
    assert "self._populate_panels(state, render=render)" in source


def test_tool_activation_no_longer_repopulates_or_rerenders_scene():
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    start = source.index("def _activate_tool")
    end = source.index("def _activate_runtime_tool")
    body = source[start:end]
    assert "_populate_panels" not in body
    assert "_render_scene" not in body
