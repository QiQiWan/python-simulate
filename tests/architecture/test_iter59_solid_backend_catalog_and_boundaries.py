from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "geoai_simkit"


def test_solver_catalog_exposes_project_solid_linear_static_backend() -> None:
    from geoai_simkit.modules import module_plugin_catalog, validate_plugin_catalog

    catalog = module_plugin_catalog()
    validation = validate_plugin_catalog(catalog)
    assert validation["ok"] is True
    solver_rows = {row["key"]: row for row in catalog["solver_backends"]}
    assert {"reference_cpu", "linear_static_cpu", "solid_linear_static_cpu"}.issubset(solver_rows)
    features = set(solver_rows["solid_linear_static_cpu"]["capabilities"].get("features", []))
    assert {"project_mesh", "solid_volume", "linear_static", "result_store_write"}.issubset(features)


def test_solid_backend_lives_in_adapter_layer_not_services_or_workflow() -> None:
    workflow_text = (ROOT / "services" / "workflow_service.py").read_text(encoding="utf-8")
    assert "solid_linear_static_cpu" not in workflow_text
    adapter_text = (ROOT / "adapters" / "legacy_solver_adapter.py").read_text(encoding="utf-8")
    assert "class SolidLinearStaticCPUSolverBackend" in adapter_text
    assert "run_geoproject_incremental_solve" in adapter_text
