from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "geoai_simkit"


def test_contract_project_exports_strict_summary_dtos() -> None:
    from geoai_simkit.contracts import (
        ProjectCompiledPhaseSummary,
        ProjectGeometrySummary,
        ProjectMaterialSummary,
        ProjectMeshSummary,
        ProjectResultStoreSummary,
        ProjectStageSummary,
    )

    assert ProjectGeometrySummary(keys=("a",)).to_dict()["geometry_count"] == 1
    assert ProjectMeshSummary(has_mesh=True, node_count=2, cell_count=1).to_dict()["cell_count"] == 1
    assert ProjectStageSummary(stage_ids=("initial",)).to_dict()["stage_count"] == 1
    assert ProjectMaterialSummary(material_ids=("soil",)).to_dict()["material_count"] == 1
    assert ProjectResultStoreSummary(stage_ids=("s1",), field_count=3).to_dict()["field_count"] == 3
    assert ProjectCompiledPhaseSummary(compiled=True).to_dict()["compiled"] is True


def test_workflow_service_continues_to_avoid_implementation_imports() -> None:
    text = (ROOT / "services" / "workflow_service.py").read_text(encoding="utf-8")
    banned = (
        "geoai_simkit.app",
        "geoai_simkit.solver.",
        "geoai_simkit.mesh.",
        "geoai_simkit.results.",
        "geoai_simkit.geoproject",
        "geoai_simkit.pipeline",
    )
    for needle in banned:
        assert needle not in text


def test_solver_registry_exposes_at_least_two_real_backends() -> None:
    from geoai_simkit.modules import module_plugin_catalog, validate_plugin_catalog

    catalog = module_plugin_catalog()
    validation = validate_plugin_catalog(catalog)
    assert validation["ok"] is True
    solver_keys = {row["key"] for row in catalog["solver_backends"]}
    assert {"reference_cpu", "linear_static_cpu"}.issubset(solver_keys)
