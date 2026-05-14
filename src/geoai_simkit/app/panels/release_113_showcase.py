from __future__ import annotations

"""Headless payload for the 1.1.3 release showcase panel."""

from typing import Any

from geoai_simkit.examples.release_1_1_3_workflow import build_release_1_1_3_project, run_release_1_1_3_workflow
from geoai_simkit.services.release_acceptance_113 import audit_release_1_1_3


def create_release_1_1_3_showcase_project() -> Any:
    project, _ = build_release_1_1_3_project()
    return project


def build_release_1_1_3_showcase_payload(project: Any | None = None) -> dict[str, Any]:
    if project is None:
        project = create_release_1_1_3_showcase_project()
    acceptance = audit_release_1_1_3(project)
    mesh = project.mesh_model.mesh_document
    return {
        "contract": "release_1_1_3_showcase_panel_v1",
        "release": project.metadata.get("release", "1.1.3-basic"),
        "phase_ids": project.phase_ids(),
        "mesh": None if mesh is None else {"node_count": mesh.node_count, "cell_count": mesh.cell_count, "cell_types": sorted(set(mesh.cell_types)), "metadata": dict(mesh.metadata)},
        "acceptance": acceptance.to_dict(),
        "nonlinear_mohr_coulomb": dict(project.solver_model.metadata.get("last_staged_mohr_coulomb_solve", {}) or {}),
        "hydro": dict(project.solver_model.metadata.get("hydro_mechanical_state", {}) or {}),
        "contact": dict(project.solver_model.metadata.get("contact_interface_enhancement", {}) or {}),
        "actions": ["run_release_1_1_3_workflow", "export_release_1_1_3_bundle", "audit_release_1_1_3"],
    }


__all__ = ["create_release_1_1_3_showcase_project", "build_release_1_1_3_showcase_payload", "run_release_1_1_3_workflow"]
