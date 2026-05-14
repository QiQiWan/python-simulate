from __future__ import annotations

"""GUI payload helpers for the 1.0.5 release showcase."""

from typing import Any

from geoai_simkit.examples.release_1_0_5_workflow import build_release_1_0_5_project, run_release_1_0_5_workflow
from geoai_simkit.services.release_acceptance_105 import audit_release_1_0_5


def build_release_1_0_5_showcase_payload(project: Any | None = None) -> dict[str, Any]:
    if project is None:
        project, build = build_release_1_0_5_project()
    else:
        build = dict(getattr(project, "metadata", {}).get("release_1_0_5_build", {}) or {})
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    acceptance = audit_release_1_0_5(project)
    return {
        "contract": "release_1_0_5_showcase_panel_v1",
        "release": getattr(project, "metadata", {}).get("release", "1.0.5-basic"),
        "project_name": getattr(getattr(project, "project_settings", None), "name", ""),
        "phase_ids": project.phase_ids() if hasattr(project, "phase_ids") else [],
        "mesh": None if mesh is None else {
            "node_count": int(getattr(mesh, "node_count", 0)),
            "cell_count": int(getattr(mesh, "cell_count", 0)),
            "cell_types": sorted({str(v) for v in list(getattr(mesh, "cell_types", []) or [])}),
            "metadata": dict(getattr(mesh, "metadata", {}) or {}),
        },
        "build": build,
        "acceptance": acceptance.to_dict(),
        "actions": ["run_release_1_0_5_workflow", "export_release_1_0_5_bundle", "open_release_1_0_5_tutorial"],
    }


def create_release_1_0_5_showcase_project() -> Any:
    return build_release_1_0_5_project()[0]


def run_release_1_0_5_showcase(**kwargs: Any) -> dict[str, Any]:
    return run_release_1_0_5_workflow(**kwargs)


__all__ = ["build_release_1_0_5_showcase_payload", "create_release_1_0_5_showcase_project", "run_release_1_0_5_showcase"]
