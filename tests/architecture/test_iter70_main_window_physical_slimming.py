from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.services.gui_slimming import build_gui_slimming_report, main_window_slimming_metric


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


def test_main_window_is_thin_entrypoint_after_physical_slimming() -> None:
    main_path = Path("src/geoai_simkit/app/main_window.py")
    impl_path = Path("src/geoai_simkit/app/main_window_impl.py")
    assert main_path.exists()
    assert impl_path.exists()
    assert len(main_path.read_text(encoding="utf-8").splitlines()) < 100
    assert len(impl_path.read_text(encoding="utf-8").splitlines()) > 4000


def test_main_window_entrypoint_has_no_direct_geometry_solver_post_imports() -> None:
    imports = _absolute_imports(Path("src/geoai_simkit/app/main_window.py"))
    forbidden_prefixes = (
        "geoai_simkit.geometry",
        "geoai_simkit.solver.warp_backend",
        "geoai_simkit.solver.gpu_runtime",
        "geoai_simkit.post",
        "geoai_simkit.materials",
    )
    assert not [item for item in imports if any(item == prefix or item.startswith(prefix + ".") for prefix in forbidden_prefixes)]
    assert "geoai_simkit.services.legacy_gui_backends" in imports


def test_gui_slimming_budget_is_now_physical_not_legacy_budget() -> None:
    metric = main_window_slimming_metric()
    assert metric.max_lines == 4000
    assert metric.line_count < 100
    assert metric.direct_internal_import_count == 0
    assert metric.ok is True
    report = build_gui_slimming_report()
    data = report.to_dict()
    assert data["ok"] is True
    assert data["metadata"]["contract_version"] == "gui_slimming_report_v2"
    assert data["metadata"]["physical_slimming_version"] == "gui_slimming_report_v3"
    assert data["metrics"][0]["metadata"]["implementation_module"] == "app/main_window_impl.py"


def test_main_window_public_compatibility_symbols_remain_importable() -> None:
    import geoai_simkit.app.main_window as main_window

    assert main_window.MainWindow is not None
    assert main_window.SolverSettings(backend="solid_linear_static_cpu").backend == "solid_linear_static_cpu"
    assert callable(main_window.launch_main_window)
