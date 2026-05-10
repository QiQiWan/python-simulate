from __future__ import annotations

"""Solver backend adapter for the current GeoProjectDocument runtime solver."""

from typing import Any

from geoai_simkit.contracts import PluginCapability, PluginHealth, SolveRequest, SolveResult, SolverCapabilities


class ReferenceCPUSolverBackend:
    """Stable backend wrapper around the current dependency-light staged solver."""

    key = "reference_cpu"
    label = "Reference CPU staged GeoProject solver"
    capabilities = SolverCapabilities(
        key=key,
        label=label,
        devices=("cpu",),
        stage_solve=True,
        nonlinear=False,
        gpu=False,
        deterministic=True,
        metadata={
            "source": "geoai_simkit.geoproject.runtime_solver",
            "plugin_capability": PluginCapability(
                key=key,
                label=label,
                category="solver_backend",
                version="1",
                features=("staged_solve", "headless", "result_store_write"),
                devices=("cpu",),
                supported_inputs=("GeoProjectDocument", "ProjectReadPort"),
                supported_outputs=("SolveResult", "ResultStore"),
                health=PluginHealth(available=True),
            ).to_dict(),
        },
    )

    def can_solve(self, request: SolveRequest) -> bool:
        target = request.target()
        return target is not None and hasattr(target, "compile_phase_models") and hasattr(target, "result_store")

    def solve(self, request: SolveRequest) -> SolveResult:
        if not self.can_solve(request):
            raise TypeError("ReferenceCPUSolverBackend expects a GeoProjectDocument-like target.")
        from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
        from geoai_simkit.mesh.solid_readiness import validate_solid_analysis_readiness

        project = request.target()
        readiness = validate_solid_analysis_readiness(project)
        if not readiness.ready:
            metadata: dict[str, Any] = {"backend": self.key, "solid_readiness": readiness.to_dict(), **dict(request.metadata)}
            return SolveResult(
                accepted=False,
                status="rejected",
                backend_key=self.key,
                solved_model=project,
                result_store=getattr(project, "result_store", None),
                summary=readiness,
                metadata=metadata,
            )
        summary = run_geoproject_incremental_solve(
            project,
            compile_if_needed=bool(request.compile_if_needed),
            write_results=bool(request.write_results),
        )
        phase_records = tuple(getattr(summary, "phase_records", ()) or ())
        metadata: dict[str, Any] = dict(request.metadata)
        if hasattr(summary, "to_dict"):
            metadata["summary"] = summary.to_dict()
        metadata.setdefault("backend", self.key)
        return SolveResult(
            accepted=bool(getattr(summary, "accepted", False)),
            status="accepted" if bool(getattr(summary, "accepted", False)) else "rejected",
            backend_key=self.key,
            solved_model=project,
            result_store=getattr(project, "result_store", None),
            summary=summary,
            phase_records=phase_records,
            metadata=metadata,
        )


class LinearStaticCPUSolverBackend:
    """CPU linear-static backend backed by the dependency-light FEM kernel.

    This is a real numerical backend (not a dummy test double).  In project
    workflows it currently runs the stable core FEM linear-static benchmark and
    returns a standard ``SolveResult``; mesh/load extraction can be expanded
    behind the same backend contract without changing callers.
    """

    key = "linear_static_cpu"
    label = "Linear static CPU FEM backend"
    capabilities = SolverCapabilities(
        key=key,
        label=label,
        devices=("cpu",),
        stage_solve=False,
        nonlinear=False,
        gpu=False,
        deterministic=True,
        metadata={
            "source": "geoai_simkit.fem.linear_static",
            "plugin_capability": PluginCapability(
                key=key,
                label=label,
                category="solver_backend",
                version="1",
                features=("linear_static", "sparse_cpu", "benchmark_grade", "headless"),
                devices=("cpu",),
                supported_inputs=("MeshDocument", "ProjectReadPort"),
                supported_outputs=("SolveResult", "benchmark_report"),
                health=PluginHealth(available=True),
                metadata={"kernel": "solve_sparse_linear_static", "benchmark": "hex8_linear_patch"},
            ).to_dict(),
        },
    )

    def can_solve(self, request: SolveRequest) -> bool:
        return str(request.backend_preference or "") in {self.key, "linear_static", "cpu_linear_static"}

    def solve(self, request: SolveRequest) -> SolveResult:
        from geoai_simkit.fem.linear_static import run_hex8_linear_patch_benchmark

        benchmark = run_hex8_linear_patch_benchmark()
        accepted = bool(benchmark.get("passed"))
        metadata: dict[str, Any] = {"plugin": self.key, "benchmark": benchmark, **dict(request.metadata)}
        return SolveResult(
            accepted=accepted,
            status="accepted" if accepted else "rejected",
            backend_key=self.key,
            solved_model=request.target(),
            result_store=getattr(request.target(), "result_store", None),
            summary=benchmark,
            metadata=metadata,
        )


class SolidLinearStaticCPUSolverBackend:
    """Project-level 3D solid linear-static CPU backend.

    Unlike ``linear_static_cpu`` (which is intentionally retained as a core FEM
    benchmark backend for compatibility), this backend reads the active
    ``GeoProjectDocument``/``ProjectReadPort`` mesh, materials, boundary
    conditions and loads, runs the staged solid FEM assembly, and writes nodal
    displacement, cell stress/strain and reaction-force fields to ResultStore.
    """

    key = "solid_linear_static_cpu"
    label = "Project 3D solid linear-static CPU backend"
    capabilities = SolverCapabilities(
        key=key,
        label=label,
        devices=("cpu",),
        stage_solve=True,
        nonlinear=False,
        gpu=False,
        deterministic=True,
        metadata={
            "source": "geoai_simkit.geoproject.runtime_solver",
            "plugin_capability": PluginCapability(
                key=key,
                label=label,
                category="solver_backend",
                version="1",
                features=("project_mesh", "solid_volume", "tet4", "hex8", "linear_static", "result_store_write", "reaction_forces"),
                devices=("cpu",),
                supported_inputs=("GeoProjectDocument", "ProjectReadPort", "MeshDocument:solid_volume"),
                supported_outputs=("SolveResult", "ResultStore", "StageResult"),
                health=PluginHealth(available=True),
                metadata={"contract": "solid_linear_static_project_v1", "volume_cell_types": ("tet4", "hex8")},
            ).to_dict(),
        },
    )

    def can_solve(self, request: SolveRequest) -> bool:
        preferred = str(request.backend_preference or "")
        if preferred not in {self.key, "solid_linear_static", "project_solid_linear_static", "solid_cpu"}:
            return False
        target = request.target()
        return target is not None and hasattr(target, "compile_phase_models") and hasattr(target, "result_store")

    def solve(self, request: SolveRequest) -> SolveResult:
        if not self.can_solve(request):
            raise TypeError("SolidLinearStaticCPUSolverBackend expects a GeoProjectDocument-like target and explicit backend preference.")
        from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
        from geoai_simkit.mesh.solid_readiness import validate_solid_analysis_readiness

        project = request.target()
        populate = getattr(project, "populate_default_framework_content", None)
        if callable(populate):
            populate()
        readiness = validate_solid_analysis_readiness(project)
        base_metadata: dict[str, Any] = {
            "backend": self.key,
            "contract": "solid_linear_static_project_v1",
            "solid_readiness": readiness.to_dict(),
            **dict(request.metadata),
        }
        if not readiness.ready:
            return SolveResult(
                accepted=False,
                status="rejected",
                backend_key=self.key,
                solved_model=project,
                result_store=getattr(project, "result_store", None),
                summary=readiness,
                metadata=base_metadata,
            )
        summary = run_geoproject_incremental_solve(
            project,
            compile_if_needed=bool(request.compile_if_needed),
            write_results=bool(request.write_results),
        )
        phase_records = tuple(getattr(summary, "phase_records", ()) or ())
        result_store = getattr(project, "result_store", None)
        phase_result_fields: dict[str, list[str]] = {}
        if result_store is not None:
            for phase_id, stage_result in dict(getattr(result_store, "phase_results", {}) or {}).items():
                phase_result_fields[str(phase_id)] = sorted(dict(getattr(stage_result, "fields", {}) or {}).keys())
        summary_dict = summary.to_dict() if hasattr(summary, "to_dict") else {"value": str(summary)}
        metadata = {
            **base_metadata,
            "summary": summary_dict,
            "phase_result_fields": phase_result_fields,
            "result_field_contract": {
                "node": ["displacement", "ux", "uy", "uz", "reaction_force"],
                "cell": ["cell_stress", "cell_strain", "cell_stress_zz", "cell_von_mises", "cell_equivalent_strain"],
            },
        }
        accepted = bool(getattr(summary, "accepted", False)) and bool(phase_records)
        return SolveResult(
            accepted=accepted,
            status="accepted" if accepted else "rejected",
            backend_key=self.key,
            solved_model=project,
            result_store=result_store,
            summary=summary,
            phase_records=phase_records,
            metadata=metadata,
        )


class NonlinearMohrCoulombCPUSolverBackend:
    """Project-level Mohr-Coulomb engineering-preview backend.

    The backend runs the verified project solid linear-static solve, then updates
    each cell's strain through the built-in Mohr-Coulomb material law and writes
    plasticity fields to ResultStore. It is intentionally labeled as an
    engineering preview until a full global Newton/plasticity loop is added.
    """

    key = "nonlinear_mohr_coulomb_cpu"
    label = "Project Mohr-Coulomb nonlinear soil preview CPU backend"
    capabilities = SolverCapabilities(
        key=key,
        label=label,
        devices=("cpu",),
        stage_solve=True,
        nonlinear=True,
        gpu=False,
        deterministic=True,
        metadata={
            "source": "geoai_simkit.solver.nonlinear_project",
            "plugin_capability": PluginCapability(
                key=key,
                label=label,
                category="solver_backend",
                version="1",
                features=("project_mesh", "solid_volume", "mohr_coulomb", "plasticity_fields", "engineering_preview", "result_store_write"),
                devices=("cpu",),
                supported_inputs=("GeoProjectDocument", "ProjectReadPort", "MeshDocument:solid_volume"),
                supported_outputs=("SolveResult", "ResultStore", "plasticity_fields"),
                health=PluginHealth(available=True, status="engineering_preview", diagnostics=("Uses linear global displacement solve plus Mohr-Coulomb material update preview; not a full global Newton return-mapping solver yet.",)),
                metadata={"contract": "nonlinear_mohr_coulomb_preview_v1", "base_backend": "solid_linear_static_cpu"},
            ).to_dict(),
        },
    )

    def can_solve(self, request: SolveRequest) -> bool:
        preferred = str(request.backend_preference or "")
        return preferred in {self.key, "mohr_coulomb_cpu", "nonlinear_cpu", "plastic_cpu"} and request.target() is not None

    def solve(self, request: SolveRequest) -> SolveResult:
        if not self.can_solve(request):
            raise TypeError("NonlinearMohrCoulombCPUSolverBackend expects an explicit nonlinear_mohr_coulomb_cpu preference.")
        base_request = SolveRequest(
            model=request.model,
            project=request.project,
            stage_ids=request.stage_ids,
            settings=request.settings,
            compile_if_needed=request.compile_if_needed,
            write_results=request.write_results,
            backend_preference="solid_linear_static_cpu",
            metadata={"requested_backend": self.key, **dict(request.metadata)},
        )
        base = SolidLinearStaticCPUSolverBackend().solve(base_request)
        project = base.solved_model
        nonlinear_report = {"ok": False, "skipped": True}
        if base.ok and project is not None:
            from geoai_simkit.solver.nonlinear_project import apply_mohr_coulomb_state_update

            nonlinear_report = apply_mohr_coulomb_state_update(project, source_backend=base.backend_key)
        metadata = {
            **dict(base.metadata),
            "backend": self.key,
            "base_backend": base.backend_key,
            "nonlinear_report": nonlinear_report,
            "contract": "nonlinear_mohr_coulomb_preview_v1",
        }
        return SolveResult(
            accepted=bool(base.accepted),
            status="accepted_with_nonlinear_preview" if base.ok else base.status,
            backend_key=self.key,
            solved_model=project,
            result_store=base.result_store,
            summary=base.summary,
            phase_records=base.phase_records,
            metadata=metadata,
        )


class StagedMohrCoulombCPUSolverBackend:
    """Production-boundary CPU backend for staged Mohr-Coulomb control.

    The backend adds load-increment control, convergence diagnostics and state
    commit metadata around the current project solid solver and Mohr-Coulomb
    material update path. It is the stable solver boundary for future full
    consistent-tangent Newton implementation.
    """

    key = "staged_mohr_coulomb_cpu"
    label = "Staged Mohr-Coulomb production-boundary CPU backend"
    capabilities = SolverCapabilities(
        key=key,
        label=label,
        devices=("cpu",),
        stage_solve=True,
        nonlinear=True,
        gpu=False,
        deterministic=True,
        metadata={
            "source": "geoai_simkit.solver.nonlinear_boundary",
            "plugin_capability": PluginCapability(
                key=key,
                label=label,
                category="solver_backend",
                version="1",
                features=(
                    "project_mesh",
                    "solid_volume",
                    "mohr_coulomb",
                    "load_increments",
                    "convergence_diagnostics",
                    "state_commit_metadata",
                    "production_solver_boundary",
                    "nonlinear_solver_core_v1",
                    "return_mapping",
                    "cutback",
                ),
                devices=("cpu",),
                supported_inputs=("GeoProjectDocument", "ProjectReadPort", "MeshDocument:solid_volume"),
                supported_outputs=("SolveResult", "ResultStore", "NonlinearRunReport"),
                health=PluginHealth(
                    available=True,
                    status="production_boundary",
                    diagnostics=(
                        "Provides staged nonlinear control and diagnostics; global tangent currently reuses the verified linear solid assembly until full consistent-tangent Newton is implemented.",
                    ),
                ),
                metadata={"contract": "staged_mohr_coulomb_boundary_v2", "base_backend": "solid_linear_static_cpu", "nonlinear_core": "nonlinear_solver_core_v1"},
            ).to_dict(),
        },
    )

    def can_solve(self, request: SolveRequest) -> bool:
        preferred = str(request.backend_preference or "")
        return preferred in {self.key, "production_mohr_coulomb_cpu", "staged_nonlinear_cpu"} and request.target() is not None

    def solve(self, request: SolveRequest) -> SolveResult:
        if not self.can_solve(request):
            raise TypeError("StagedMohrCoulombCPUSolverBackend expects an explicit staged_mohr_coulomb_cpu preference.")
        from geoai_simkit.solver.nonlinear_boundary import NonlinearRunControl, run_staged_mohr_coulomb_boundary

        settings = request.settings if isinstance(request.settings, dict) else {}
        control = NonlinearRunControl(
            load_increments=int(settings.get("load_increments", request.metadata.get("load_increments", 3)) or 3),
            max_iterations=int(settings.get("max_iterations", request.metadata.get("max_iterations", 8)) or 8),
            tolerance=float(settings.get("tolerance", request.metadata.get("tolerance", 1.0e-5)) or 1.0e-5),
            cutback_on_failure=bool(settings.get("cutback_on_failure", request.metadata.get("cutback_on_failure", True))),
            metadata={"request_metadata": dict(request.metadata)},
        )
        project = request.target()
        report = run_staged_mohr_coulomb_boundary(
            project,
            control=control,
            compile_if_needed=bool(request.compile_if_needed),
            write_results=bool(request.write_results),
        )
        metadata = {
            "backend": self.key,
            "contract": "staged_mohr_coulomb_boundary_v1",
            "contract_version": "staged_mohr_coulomb_boundary_v2",
            "nonlinear_core": "nonlinear_solver_core_v1",
            "nonlinear_run_report": report.to_dict(),
            **dict(request.metadata),
        }
        phase_records = tuple(getattr(report.base_summary, "phase_records", ()) or ())
        return SolveResult(
            accepted=bool(report.ok),
            status="accepted" if report.ok else report.status,
            backend_key=self.key,
            solved_model=project,
            result_store=getattr(project, "result_store", None),
            summary=report,
            phase_records=phase_records,
            metadata=metadata,
        )


class ContactInterfaceCPUSolverBackend:
    """Project-level Coulomb penalty contact/interface CPU backend.

    The backend evaluates active structural interfaces through the Contact Solver
    Core v1 active-set boundary, writes interface state/traction fields to
    ResultStore, and returns a standard ``SolveResult``. It is designed as the
    stable boundary for future full global contact stiffness coupling.
    """

    key = "contact_interface_cpu"
    label = "Coulomb contact/interface CPU backend"
    capabilities = SolverCapabilities(
        key=key,
        label=label,
        devices=("cpu",),
        stage_solve=True,
        nonlinear=True,
        gpu=False,
        deterministic=True,
        metadata={
            "source": "geoai_simkit.solver.contact_core",
            "plugin_capability": PluginCapability(
                key=key,
                label=label,
                category="solver_backend",
                version="1",
                features=(
                    "contact_interface_solver_v1",
                    "coulomb_penalty",
                    "active_set",
                    "stick_slip",
                    "open_close",
                    "interface_result_fields",
                    "result_store_write",
                ),
                devices=("cpu",),
                supported_inputs=("GeoProjectDocument", "ProjectReadPort", "StructuralInterfaceRecord"),
                supported_outputs=("SolveResult", "ResultStore", "ContactSolverReport"),
                health=PluginHealth(
                    available=True,
                    status="contact_boundary_v1",
                    diagnostics=(
                        "Evaluates Coulomb penalty interface states and writes contact fields; full global contact stiffness assembly is reserved for the next solver-core deepening.",
                    ),
                ),
                metadata={"contract": "contact_interface_solver_v1", "coupling": "penalty_state_fields_v1"},
            ).to_dict(),
        },
    )

    def can_solve(self, request: SolveRequest) -> bool:
        preferred = str(request.backend_preference or "")
        return preferred in {self.key, "interface_contact_cpu", "contact_cpu", "coulomb_contact_cpu"} and request.target() is not None

    def solve(self, request: SolveRequest) -> SolveResult:
        if not self.can_solve(request):
            raise TypeError("ContactInterfaceCPUSolverBackend expects an explicit contact_interface_cpu preference.")
        from geoai_simkit.solver.contact_core import ContactRunControl, run_project_contact_solver

        settings = request.settings if isinstance(request.settings, dict) else {}
        control = ContactRunControl(
            max_active_set_iterations=int(settings.get("max_active_set_iterations", request.metadata.get("max_active_set_iterations", 4)) or 4),
            residual_tolerance=float(settings.get("residual_tolerance", request.metadata.get("residual_tolerance", 1.0e-6)) or 1.0e-6),
            write_results=bool(request.write_results),
            metadata={"request_metadata": dict(request.metadata)},
        )
        project = request.target()
        report = run_project_contact_solver(project, control=control, write_results=bool(request.write_results))
        metadata = {
            "backend": self.key,
            "contract": "contact_interface_solver_v1",
            "contact_report": report.to_dict(),
            **dict(request.metadata),
        }
        return SolveResult(
            accepted=bool(report.ok),
            status=report.status,
            backend_key=self.key,
            solved_model=project,
            result_store=getattr(project, "result_store", None),
            summary=report,
            phase_records=(),
            metadata=metadata,
        )


__all__ = ["ReferenceCPUSolverBackend", "LinearStaticCPUSolverBackend", "SolidLinearStaticCPUSolverBackend", "NonlinearMohrCoulombCPUSolverBackend", "StagedMohrCoulombCPUSolverBackend", "ContactInterfaceCPUSolverBackend"]
