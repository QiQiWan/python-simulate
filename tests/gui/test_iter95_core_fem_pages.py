from __future__ import annotations

from geoai_simkit.app.shell.unified_workbench_window import UnifiedWorkbenchController
from geoai_simkit.app.completion_matrix import build_completion_matrix


def test_gui_payload_has_six_independent_core_pages():
    payload = UnifiedWorkbenchController().payload
    pages = payload["fem_pages"]
    assert list(pages.keys()) == ["modeling", "mesh", "solve", "results", "benchmark", "advanced"]
    assert payload["navigation"]["active_space"] in pages
    labels = [item["label"] for item in payload["navigation"]["primary_navigation"]]
    assert labels == ["Modeling", "Mesh", "Solve", "Results", "Benchmark", "Advanced"]


def test_completion_matrix_uses_test_result_shape():
    matrix = build_completion_matrix()
    assert len(matrix["core_fem"]) == 7
    assert "test_results" in matrix
    for row in matrix["core_fem"]:
        assert "test_result" in row
        assert "test_driven_status" in row
