from __future__ import annotations

import json

from geoai_simkit.contracts import CompleteModularizationReport, ModuleManifest
from geoai_simkit.services.module_kernel import (
    build_complete_modularization_report,
    legacy_boundary_markers,
    modular_layer_specs,
    module_dependency_edges,
    module_manifests,
)
from geoai_simkit.services import build_module_governance_report


def test_complete_modularization_report_is_ok_and_serializable() -> None:
    report = build_complete_modularization_report()
    assert isinstance(report, CompleteModularizationReport)
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["version"] == "complete_modularization_v2"
    assert payload["issue_count"] == 0
    assert payload["metadata"]["architecture_status"] == "fully_modular_with_contained_legacy_bridges"
    json.dumps(payload, sort_keys=True)


def test_module_manifests_cover_public_modules_and_interfaces() -> None:
    manifests = module_manifests()
    assert {manifest.key for manifest in manifests} >= {
        "document_model",
        "geology_import",
        "meshing",
        "stage_planning",
        "fem_solver",
        "geotechnical",
        "postprocessing",
    }
    for manifest in manifests:
        assert isinstance(manifest, ModuleManifest)
        assert manifest.owned_namespaces
        assert manifest.interface is not None
        assert manifest.interface.entrypoints
        assert manifest.to_dict()["metadata"]["contract"] == "module_manifest_v1"


def test_module_dependency_edges_are_valid_dag_edges() -> None:
    edges = module_dependency_edges()
    assert edges
    assert all(edge.allowed for edge in edges)
    assert all(edge.source != edge.target for edge in edges)
    assert any(edge.source == "geotechnical" and edge.target == "fem_solver" for edge in edges)


def test_layers_and_legacy_boundaries_are_explicit() -> None:
    layers = modular_layer_specs()
    assert [layer.key for layer in layers][:2] == ["contracts", "adapters"]
    assert layers[-1].key == "app.shell"
    legacy = legacy_boundary_markers()
    assert {item.key for item in legacy} >= {"legacy_qt_main_window_impl", "legacy_gui_backend_bridge", "document_adapter_bridge"}
    assert all(item.status == "contained" for item in legacy)


def test_module_governance_embeds_complete_modularization_report() -> None:
    report = build_module_governance_report().to_dict()
    complete = report["metadata"]["complete_modularization"]
    assert complete["ok"] is True
    assert complete["issue_count"] == 0
    assert complete["metadata"]["module_count"] >= 8
