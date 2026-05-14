from __future__ import annotations

"""Headless payload and one-click actions for the 1.3.0 Beta demo center."""

from pathlib import Path
from typing import Any

from geoai_simkit.examples.release_1_3_0_workflow import build_release_1_3_0_gui_payload, build_release_1_3_0_project, run_release_1_3_0_workflow
from geoai_simkit.services.demo_project_runner import build_demo_catalog, load_demo_project, run_demo_complete_calculation
from geoai_simkit.services.release_acceptance_130 import audit_release_1_3_0


def create_release_1_3_0_demo_project() -> Any:
    return load_demo_project("foundation_pit_3d_beta")


def run_release_1_3_0_demo(output_dir: str | Path | None = None) -> dict[str, Any]:
    return run_demo_complete_calculation("foundation_pit_3d_beta", output_dir=output_dir).to_dict(include_project=True)


def build_release_1_3_0_showcase_payload(project: Any | None = None) -> dict[str, Any]:
    if project is None:
        project, _ = build_release_1_3_0_project()
    pipeline = dict(getattr(project, "metadata", {}).get("release_1_3_0_pipeline", {}) or {})
    artifacts = dict(getattr(project, "metadata", {}).get("release_1_3_0_artifacts", {}) or {})
    gui_payload = build_release_1_3_0_gui_payload(project)
    acceptance = audit_release_1_3_0(project, pipeline=pipeline, artifacts=artifacts, gui_payload=gui_payload).to_dict()
    mesh = project.mesh_model.mesh_document
    return {
        "contract": "release_1_3_0_showcase_panel_v1",
        "release": project.metadata.get("release", "1.3.0-beta"),
        "catalog": build_demo_catalog(),
        "demo_center": gui_payload["demo_center"],
        "phase_ids": project.phase_ids(),
        "mesh": None if mesh is None else {"node_count": mesh.node_count, "cell_count": mesh.cell_count, "cell_types": sorted(set(mesh.cell_types)), "metadata": dict(mesh.metadata)},
        "acceptance": acceptance,
        "pipeline": pipeline,
        "actions": ["load_demo_project", "run_complete_calculation", "export_demo_bundle"],
        "workflow_contract": "geoai_simkit_release_1_3_0_workflow_v1",
    }


__all__ = [
    "create_release_1_3_0_demo_project",
    "run_release_1_3_0_demo",
    "build_release_1_3_0_showcase_payload",
    "run_release_1_3_0_workflow",
]
