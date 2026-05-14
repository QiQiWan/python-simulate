from __future__ import annotations

"""Headless payload for the 1.2.4 release showcase panel."""

from typing import Any

from geoai_simkit.examples.release_1_2_4_workflow import build_release_1_2_4_project, run_release_1_2_4_workflow
from geoai_simkit.services.release_acceptance_124 import audit_release_1_2_4


def create_release_1_2_4_showcase_project() -> Any:
    project, _ = build_release_1_2_4_project()
    return project


def build_release_1_2_4_showcase_payload(project: Any | None = None) -> dict[str, Any]:
    if project is None:
        project = create_release_1_2_4_showcase_project()
    newton = dict(project.solver_model.metadata.get("last_global_mohr_coulomb_newton_solve", {}) or {})
    acceptance = audit_release_1_2_4(project, newton_summary=newton)
    mesh = project.mesh_model.mesh_document
    return {
        "contract": "release_1_2_4_showcase_panel_v1",
        "release": project.metadata.get("release", "1.2.4-basic"),
        "phase_ids": project.phase_ids(),
        "mesh": None if mesh is None else {"node_count": mesh.node_count, "cell_count": mesh.cell_count, "cell_types": sorted(set(mesh.cell_types)), "metadata": dict(mesh.metadata)},
        "acceptance": acceptance.to_dict(),
        "global_newton": newton,
        "gmsh_exchange": dict(project.mesh_model.metadata.get("last_gmsh_occ_native_exchange", {}) or {}),
        "consolidation": dict(project.solver_model.metadata.get("consolidation_coupling_state", {}) or {}),
        "interface_iteration": dict(project.solver_model.metadata.get("interface_contact_iteration", {}) or {}),
        "gui_recording": dict(project.metadata.get("release_1_2_4_build", {}).get("gui_recording", {}) or {}),
        "actions": ["run_release_1_2_4_workflow", "export_release_1_2_4_bundle", "audit_release_1_2_4", "launch_phase_workbench_qt"],
    }


__all__ = ["create_release_1_2_4_showcase_project", "build_release_1_2_4_showcase_payload", "run_release_1_2_4_workflow"]
