from __future__ import annotations

"""Unified desktop workbench launcher and fallback payload builder.

This module intentionally uses the new VisualModelingSystem for default payloads.
Older WorkbenchService documents are still accepted when explicitly supplied,
but startup no longer blocks on the legacy project/model presenter chain.
"""

from importlib import import_module
import os
from typing import Any

from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def _module_available(name: str) -> bool:
    try:
        import_module(name)
        return True
    except Exception:
        return False


def _prefer_qt_only_workbench() -> bool:
    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    return platform in {"offscreen", "minimal"} or os.environ.get("GEOAI_SIMKIT_DISABLE_PYVISTA", "").strip() == "1"


def _benchmark_panel() -> dict[str, Any]:
    try:
        from geoai_simkit.app.completion_matrix import build_completion_matrix

        matrix = build_completion_matrix()
        return {
            "report_dir": "reports",
            "core_smoke": dict(matrix.get("test_results", {}) or {}),
            "solver_benchmark": dict(matrix.get("benchmark_results", {}) or {}),
        }
    except Exception as exc:
        return {"report_dir": "reports", "error": str(exc)}


def _visual_system_payload() -> dict[str, Any]:
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    system.run_results()
    return system.to_payload()


def build_unified_workbench_payload(document: Any | None = None) -> dict[str, Any]:
    """Build a lightweight GUI-readable payload for all operation pages.

    When no legacy document is supplied, the new integrated visual modeling
    system is used.  This avoids the previous fallback failure path where
    WorkbenchService required attributes that were no longer part of the modern
    document model.
    """

    if document is None:
        visual_payload = _visual_system_payload()
        doc_summary = dict(visual_payload.get("document", {}) or {})
        return {
            "contract": "unified_workbench_payload_v2",
            "header": {
                "case_name": doc_summary.get("name", "integrated-block-pit"),
                "mode": "visual_modeling",
                "dirty": bool(visual_payload.get("dirty", {}).get("is_dirty", False)),
            },
            "workspace": {
                "backend": "VisualModelingSystem",
                "blocks": doc_summary.get("blocks", 0),
                "faces": doc_summary.get("faces", 0),
                "contacts": doc_summary.get("contacts", 0),
                "stages": doc_summary.get("stages", 0),
                "active_stage_id": doc_summary.get("active_stage_id"),
            },
            "pages": visual_payload.get("operation_pages", {}),
            "visual_modeling": visual_payload,
            "benchmark_panel": _benchmark_panel(),
        }

    # Legacy compatibility path for WorkbenchDocument-like objects.
    try:
        from geoai_simkit.app.fem_workflow_pages import build_fem_workflow_pages

        pages = build_fem_workflow_pages(document)
    except Exception as exc:
        pages = {"error": {"message": str(exc), "panels": [], "operations": []}}
    workspace = dict(getattr(document, "metadata", {}).get("workspace_session", {}) or {})
    try:
        from geoai_simkit.app.modeling_architecture import build_visual_modeling_payload_from_workbench_document

        visual_modeling = build_visual_modeling_payload_from_workbench_document(document)
    except Exception as exc:
        visual_modeling = {"contract": "visual_modeling_architecture_v1", "error": str(exc)}
    return {
        "contract": "unified_workbench_payload_v1_legacy",
        "header": {
            "case_name": getattr(getattr(document, "case", None), "name", "untitled"),
            "mode": getattr(document, "mode", "geometry"),
            "dirty": bool(getattr(document, "dirty", False)),
        },
        "workspace": workspace,
        "pages": pages,
        "visual_modeling": visual_modeling,
        "benchmark_panel": _benchmark_panel(),
    }


class UnifiedWorkbenchController:
    """Controller used by the Tk fallback and startup smoke tests."""

    def __init__(self, document: Any | None = None) -> None:
        self.document = document

    def refresh_payload(self) -> dict[str, Any]:
        return build_unified_workbench_payload(self.document)

    @property
    def payload(self) -> dict[str, Any]:
        """Compatibility payload for older GUI shell tests and callers."""

        payload = self.refresh_payload()
        pages = dict(payload.get("pages", {}) or {})
        page_order = ["modeling", "mesh", "solve", "results", "benchmark", "advanced"]
        ordered_pages = {key: pages[key] for key in page_order if key in pages}
        navigation = [
            {"key": key, "label": key.title() if key != "results" else "Results", "target": key}
            for key in ordered_pages
        ]
        return {
            **payload,
            "fem_pages": ordered_pages,
            "navigation": {
                "active_space": next(iter(ordered_pages), "modeling"),
                "primary_navigation": navigation,
            },
        }


def launch_unified_workbench() -> None:
    """Launch the best available desktop workbench."""

    has_pyvista = _module_available("pyvista") and _module_available("pyvistaqt") and not _prefer_qt_only_workbench()
    fallback_error: Exception | None = None
    if has_pyvista:
        try:
            from geoai_simkit.app.workbench_window import launch_nextgen_workbench

            launch_nextgen_workbench()
            return
        except Exception as exc:
            fallback_error = exc
    else:
        fallback_error = RuntimeError(
            "PySide6 is available, but pyvista/pyvistaqt are not available; "
            "using the lightweight PySide workbench."
        )

    try:
        from geoai_simkit.app.modern_qt_workbench import launch_modern_qt_workbench

        launch_modern_qt_workbench()
        return
    except Exception as exc:
        if fallback_error is None:
            fallback_error = exc

    try:
        from geoai_simkit.app.main_window import launch_main_window

        launch_main_window()
        return
    except Exception as exc:
        if fallback_error is None:
            fallback_error = exc
        from geoai_simkit.app.fallback_gui import launch_tk_fallback_workbench

        launch_tk_fallback_workbench(str(fallback_error))


__all__ = ["UnifiedWorkbenchController", "build_unified_workbench_payload", "launch_unified_workbench"]
