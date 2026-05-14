from __future__ import annotations

"""Headless canonical workflow service for module interoperability.

This service is the P0-P4 completion path: GUI/CLI callers can orchestrate the
canonical module chain without importing meshing, solver or result internals.
Each step goes through the public module facade and stable contracts.
"""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import (
    ProjectWorkflowReport,
    ProjectWorkflowRequest,
    WorkflowStepReport,
    project_port_capabilities,
    workflow_artifact_ref_from_payload,
)
from geoai_simkit.modules import fem_solver, meshing, postprocessing, stage_planning
from geoai_simkit.services.production_meshing_validation import build_production_meshing_validation_report
from geoai_simkit.services.complete_3d_mesh import build_complete_3d_mesh_report
from geoai_simkit.services.geometry_kernel import build_geometry_kernel_report


@dataclass(slots=True)
class ProjectWorkflowService:
    """Run the canonical module-interoperability chain through facades only."""

    continue_on_error: bool = True

    def run(self, request: ProjectWorkflowRequest) -> ProjectWorkflowReport:
        context = as_project_context(request.project)
        snapshot_before = context.snapshot()
        steps: list[WorkflowStepReport] = []
        artifacts: dict[str, Any] = {}
        artifact_refs = []

        def add_step(key: str, ok: bool, *, status: str = "ok", diagnostics: tuple[str, ...] = (), metadata: dict[str, Any] | None = None) -> None:
            steps.append(
                WorkflowStepReport(
                    key=key,
                    ok=bool(ok),
                    status=status,
                    diagnostics=tuple(str(item) for item in diagnostics),
                    metadata=dict(metadata or {}),
                )
            )

        capabilities = project_port_capabilities(context).to_dict()
        add_step("project_port", True, metadata={"capabilities": capabilities, "snapshot": snapshot_before.to_dict()})

        try:
            mesh_result = meshing.generate_project_mesh(
                context,
                mesh_kind=request.mesh_kind,
                attach=True,
                options=dict(request.metadata.get("mesh_options", {}) or {}),
                metadata={"workflow": "canonical_interop", **dict(request.metadata)},
            )
            artifacts["mesh"] = mesh_result
            artifact_refs.append(workflow_artifact_ref_from_payload("mesh", mesh_result, producer="meshing"))
            add_step("meshing", mesh_result.ok, metadata=mesh_result.to_dict())
            mesh_metadata = dict(getattr(mesh_result, "metadata", {}) or {})
            include_validation = bool(
                request.metadata.get("include_mesh_validation_artifact")
                or mesh_metadata.get("solid_readiness")
                or str(mesh_result.mesh_kind).lower() in {"gmsh_tet4_from_stl", "conformal_tet4_from_stl_regions", "voxel_hex8_from_stl", "soil_layered_volume_from_stl", "gmsh_occ_fragment_tet4_from_stl", "gmsh_occ_fragment_strata", "production_gmsh_occ_tet4", "occ_fragment_tet4_from_stl"}
            )
            if include_validation:
                validation = build_production_meshing_validation_report(context, solver_backend=request.solver_backend)
                artifacts["mesh_validation"] = validation
                artifact_refs.append(workflow_artifact_ref_from_payload("mesh_validation", validation, producer="production_meshing_validation", kind="quality"))
            include_mesh3d = bool(
                request.metadata.get("include_complete_3d_mesh_artifact")
                or mesh_metadata.get("complete_3d_mesh")
                or str(mesh_result.mesh_kind).lower() in {"structured_hex8_box", "structured_tet4_box", "gmsh_tet4_from_stl", "conformal_tet4_from_stl_regions", "voxel_hex8_from_stl", "soil_layered_volume_from_stl", "stratigraphic_surface_volume_from_stl", "stl_stratigraphic_surfaces", "surface_layered_volume_from_stl", "surface_strata_tet4_from_stl", "surface_strata_hex8_from_stl", "gmsh_occ_fragment_tet4_from_stl", "gmsh_occ_fragment_strata", "production_gmsh_occ_tet4", "occ_fragment_tet4_from_stl"}
            )
            if include_mesh3d:
                mesh3d_report = build_complete_3d_mesh_report(context, solver_backend=request.solver_backend)
                artifacts["mesh3d"] = mesh3d_report
                artifact_refs.append(workflow_artifact_ref_from_payload("mesh3d", mesh3d_report, producer="complete_3d_mesh", kind="mesh"))

            include_geometry_kernel = bool(
                request.metadata.get("include_geometry_kernel_artifact")
                or str(mesh_result.mesh_kind).lower() in {"soil_layered_volume_from_stl", "stl_soil_layers", "layered_hex8_from_stl", "layered_tet4_from_stl", "stratigraphic_surface_volume_from_stl", "stl_stratigraphic_surfaces", "surface_layered_volume_from_stl", "surface_strata_tet4_from_stl", "surface_strata_hex8_from_stl", "gmsh_occ_fragment_tet4_from_stl", "gmsh_occ_fragment_strata", "production_gmsh_occ_tet4", "occ_fragment_tet4_from_stl"}
            )
            if include_geometry_kernel:
                geometry_kernel_report = build_geometry_kernel_report(context, include_optimization=False)
                artifacts["geometry_kernel"] = geometry_kernel_report
                artifact_refs.append(workflow_artifact_ref_from_payload("geometry_kernel", geometry_kernel_report, producer="geometry_kernel", kind="mesh"))
        except Exception as exc:  # pragma: no cover - exercised by failure tests via messages
            add_step("meshing", False, status="error", diagnostics=(f"{type(exc).__name__}: {exc}",))
            if not self.continue_on_error:
                return self._finish(context, snapshot_before, steps, artifacts, artifact_refs, request)

        if request.compile_stages:
            try:
                stage_result = stage_planning.compile_project_stages(
                    context,
                    metadata={"workflow": "canonical_interop", **dict(request.metadata)},
                )
                artifacts["stages"] = stage_result
                artifact_refs.append(workflow_artifact_ref_from_payload("stages", stage_result, producer="stage_planning"))
                add_step("stage_planning", stage_result.ok, metadata=stage_result.to_dict())
            except Exception as exc:  # pragma: no cover
                add_step("stage_planning", False, status="error", diagnostics=(f"{type(exc).__name__}: {exc}",))
                if not self.continue_on_error:
                    return self._finish(context, snapshot_before, steps, artifacts, artifact_refs, request)

        if request.solve:
            try:
                solve_result = fem_solver.solve_project(
                    context,
                    backend_preference=request.solver_backend,
                    metadata={"workflow": "canonical_interop", **dict(request.metadata)},
                )
                artifacts["solve"] = solve_result
                artifact_refs.append(workflow_artifact_ref_from_payload("solve", solve_result, producer="fem_solver"))
                add_step("fem_solver", solve_result.ok, metadata=solve_result.to_dict())
            except Exception as exc:  # pragma: no cover
                add_step("fem_solver", False, status="error", diagnostics=(f"{type(exc).__name__}: {exc}",))
                if not self.continue_on_error:
                    return self._finish(context, snapshot_before, steps, artifacts, artifact_refs, request)

        if request.summarize:
            try:
                summary = postprocessing.summarize_results(
                    context,
                    processor=request.postprocessor,
                    metadata={"workflow": "canonical_interop", **dict(request.metadata)},
                )
                artifacts["summary"] = summary
                artifact_refs.append(workflow_artifact_ref_from_payload("summary", summary, producer="postprocessing"))
                add_step("postprocessing", summary.accepted, metadata=summary.to_dict())
            except Exception as exc:  # pragma: no cover
                add_step("postprocessing", False, status="error", diagnostics=(f"{type(exc).__name__}: {exc}",))
                if not self.continue_on_error:
                    return self._finish(context, snapshot_before, steps, artifacts, artifact_refs, request)

        return self._finish(context, snapshot_before, steps, artifacts, artifact_refs, request)

    def _finish(
        self,
        context: Any,
        snapshot_before: Any,
        steps: list[WorkflowStepReport],
        artifacts: dict[str, Any],
        artifact_refs: list[Any],
        request: ProjectWorkflowRequest,
    ) -> ProjectWorkflowReport:
        snapshot_after = context.snapshot()
        return ProjectWorkflowReport(
            ok=all(step.ok for step in steps),
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            steps=tuple(steps),
            artifacts=artifacts,
            artifact_refs=tuple(artifact_refs),
            metadata={
                "mesh_kind": request.mesh_kind,
                "solver_backend": request.solver_backend,
                "postprocessor": request.postprocessor,
                "workflow_artifacts_contract": "workflow_artifact_ref_v1",
                "workflow_artifact_manifest_contract": "workflow_artifact_manifest_v2",
                "production_meshing_validation_contract": "production_meshing_validation_report_v1",
                "complete_3d_mesh_contract": "complete_3d_mesh_report_v1",
                "geometry_kernel_contract": "geometry_kernel_report_v1",
                **dict(request.metadata),
            },
        )


def run_project_workflow(project: Any, **kwargs: Any) -> ProjectWorkflowReport:
    """Convenience entrypoint for GUI, CLI and tests."""

    request = ProjectWorkflowRequest(project=project, **kwargs)
    return ProjectWorkflowService().run(request)


__all__ = ["ProjectWorkflowService", "run_project_workflow"]
