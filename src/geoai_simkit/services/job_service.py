from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.services.blueprint_progress import build_blueprint_progress_snapshot, blueprint_progress_summary, build_release_gate_snapshot, render_blueprint_progress_markdown
from geoai_simkit.services.system_readiness import build_system_readiness_report, render_system_readiness_markdown
from geoai_simkit.pipeline import AnalysisCaseSpec, AnalysisExportSpec, AnalysisTaskSpec, GeneralFEMSolver, build_execution_plan, build_solver_settings, recommend_backend_route
from geoai_simkit.results import ResultDatabase, build_result_database, build_result_database_from_runtime_store
from geoai_simkit.runtime import RuntimeBundleManager, RuntimeCompiler


@dataclass(slots=True)
class JobPlanSummary:
    case_name: str
    profile: str
    device: str
    has_cuda: bool
    thread_count: int
    note: str
    metadata: dict[str, Any] = field(default_factory=dict)
    estimated_partitions: int | None = None
    estimated_peak_memory_bytes: int | None = None
    partition_advisory: dict[str, Any] = field(default_factory=dict)
    stage_execution_diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JobRunSummary:
    case_name: str
    profile: str
    device: str
    out_path: Path | None
    stage_count: int
    field_count: int
    result_db: ResultDatabase
    metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint_ids: tuple[str, ...] = ()
    increment_checkpoint_ids: tuple[str, ...] = ()
    failure_checkpoint_ids: tuple[str, ...] = ()
    telemetry_summary: dict[str, object] = field(default_factory=dict)
    compile_report: dict[str, object] = field(default_factory=dict)
    partition_advisory: dict[str, object] = field(default_factory=dict)
    runtime_metadata: dict[str, object] = field(default_factory=dict)
    runtime_manifest_path: Path | None = None
    runtime_bundle_path: Path | None = None


class JobService:
    def plan_case(
        self,
        case: AnalysisCaseSpec,
        *,
        execution_profile: str = 'auto',
        device: str | None = None,
        partition_count: int | None = None,
        communicator_backend: str = 'local',
        checkpoint_policy: str = 'stage-and-failure',
        checkpoint_dir: str | None = None,
        checkpoint_every_n_increments: int | None = None,
        checkpoint_keep_last_n: int | None = None,
        max_cutbacks: int | None = None,
        max_stage_retries: int | None = None,
        telemetry_level: str = 'standard',
        deterministic: bool = False,
        resume_checkpoint_id: str | None = None,
        backend_preference: str = 'auto',
        native_compatibility_mode: str = 'auto',
        nonlinear_policy: str = 'balanced',
        solver_strategy: str | None = None,
        preconditioner: str | None = None,
        nonlinear_max_iterations: int | None = None,
        tolerance: float | None = None,
        line_search: bool | None = None,
    ) -> JobPlanSummary:
        solver = GeneralFEMSolver()
        plan = build_execution_plan(
            execution_profile,
            device=device,
            partition_count=partition_count,
            communicator_backend=communicator_backend,
            checkpoint_policy=checkpoint_policy,
            checkpoint_dir=checkpoint_dir,
            checkpoint_every_n_increments=checkpoint_every_n_increments,
            checkpoint_keep_last_n=checkpoint_keep_last_n,
            max_cutbacks=max_cutbacks,
            max_stage_retries=max_stage_retries,
            telemetry_level=telemetry_level,
            deterministic=deterministic,
            resume_checkpoint_id=resume_checkpoint_id,
            backend_preference=backend_preference,
            native_compatibility_mode=native_compatibility_mode,
            nonlinear_policy=nonlinear_policy,
            solver_strategy=solver_strategy,
            preconditioner=preconditioner,
            nonlinear_max_iterations=nonlinear_max_iterations,
            tolerance=tolerance,
            line_search=line_search,
        )
        prepared = solver.prepare_case(case)
        bundle = RuntimeCompiler().compile_case(prepared, plan.compile_config)
        solver_settings = build_solver_settings(
            execution_profile,
            device=device,
            partition_count=plan.compile_config.partition_count,
            communicator_backend=communicator_backend,
            checkpoint_policy=checkpoint_policy,
            checkpoint_dir=checkpoint_dir,
            checkpoint_every_n_increments=checkpoint_every_n_increments,
            checkpoint_keep_last_n=checkpoint_keep_last_n,
            max_cutbacks=max_cutbacks,
            max_stage_retries=max_stage_retries,
            telemetry_level=telemetry_level,
            deterministic=deterministic,
            resume_checkpoint_id=resume_checkpoint_id,
            backend_preference=backend_preference,
            native_compatibility_mode=native_compatibility_mode,
            nonlinear_policy=nonlinear_policy,
            solver_strategy=solver_strategy,
            preconditioner=preconditioner,
            nonlinear_max_iterations=nonlinear_max_iterations,
            tolerance=tolerance,
            line_search=line_search,
        )
        stage_execution_diagnostics = dict(
            solver.backend.stage_execution_diagnostics(prepared.model, solver_settings)
        )
        metadata = dict(plan.metadata)
        metadata['compile_report'] = dict(bundle.compile_report.metadata)
        metadata['stage_execution_diagnostics'] = dict(stage_execution_diagnostics)
        metadata['backend_routing'] = recommend_backend_route(
            execution_profile=plan.profile,
            device=plan.device,
            partition_count=plan.compile_config.partition_count,
            communicator_backend=communicator_backend,
            backend_preference=backend_preference,
            native_compatibility_mode=native_compatibility_mode,
            stage_execution_diagnostics=stage_execution_diagnostics,
        )
        return JobPlanSummary(
            case_name=case.name,
            profile=plan.profile,
            device=plan.device,
            has_cuda=plan.has_cuda,
            thread_count=plan.thread_count,
            note=plan.note,
            metadata=metadata,
            estimated_partitions=int(bundle.compile_report.metadata.get('partition_count', plan.compile_config.partition_count)),
            estimated_peak_memory_bytes=int(bundle.compile_report.metadata.get('estimated_peak_memory_bytes', 0) or 0),
            partition_advisory=dict(bundle.compile_report.metadata.get('partition_advisory', {}) or {}),
            stage_execution_diagnostics=stage_execution_diagnostics,
        )

    def run_case(
        self,
        case: AnalysisCaseSpec,
        out_dir: Path,
        *,
        execution_profile: str = 'auto',
        device: str | None = None,
        export_stage_series: bool = True,
        partition_count: int | None = None,
        communicator_backend: str = 'local',
        checkpoint_policy: str = 'stage-and-failure',
        checkpoint_dir: str | None = None,
        checkpoint_every_n_increments: int | None = None,
        checkpoint_keep_last_n: int | None = None,
        max_cutbacks: int | None = None,
        max_stage_retries: int | None = None,
        telemetry_level: str = 'standard',
        deterministic: bool = False,
        resume_checkpoint_id: str | None = None,
        backend_preference: str = 'auto',
        native_compatibility_mode: str = 'auto',
        nonlinear_policy: str = 'balanced',
        solver_strategy: str | None = None,
        preconditioner: str | None = None,
        nonlinear_max_iterations: int | None = None,
        tolerance: float | None = None,
        line_search: bool | None = None,
    ) -> JobRunSummary:
        plan = build_execution_plan(
            execution_profile,
            device=device,
            partition_count=partition_count,
            communicator_backend=communicator_backend,
            checkpoint_policy=checkpoint_policy,
            checkpoint_dir=checkpoint_dir,
            checkpoint_every_n_increments=checkpoint_every_n_increments,
            checkpoint_keep_last_n=checkpoint_keep_last_n,
            max_cutbacks=max_cutbacks,
            max_stage_retries=max_stage_retries,
            telemetry_level=telemetry_level,
            deterministic=deterministic,
            resume_checkpoint_id=resume_checkpoint_id,
            backend_preference=backend_preference,
            native_compatibility_mode=native_compatibility_mode,
            nonlinear_policy=nonlinear_policy,
            solver_strategy=solver_strategy,
            preconditioner=preconditioner,
            nonlinear_max_iterations=nonlinear_max_iterations,
            tolerance=tolerance,
            line_search=line_search,
        )
        task = AnalysisTaskSpec(case=case, execution_profile=execution_profile, device=device, compile_config=plan.compile_config, runtime_config=plan.runtime_config, export=AnalysisExportSpec(out_dir=out_dir, stem=case.name, export_model=True, export_stage_series=export_stage_series, export_runtime_manifest=True, export_runtime_bundle=True))
        result = GeneralFEMSolver().run_task(task)
        if result.result_store is not None:
            db = build_result_database_from_runtime_store(result.result_store)
        elif result.result_db is not None:
            db = result.result_db
        else:
            db = build_result_database(result.solved_model)
        out_path = out_dir / f'{case.name}.vtu'
        return JobRunSummary(
            case_name=case.name,
            profile=execution_profile,
            device=device or 'auto',
            out_path=out_path,
            stage_count=len(db.stage_names()),
            field_count=len(db.fields),
            result_db=db,
            metadata=dict(result.metadata),
            checkpoint_ids=tuple(result.metadata.get('checkpoint_ids', ()) or ()),
            increment_checkpoint_ids=tuple(result.metadata.get('increment_checkpoint_ids', ()) or ()),
            failure_checkpoint_ids=tuple(result.metadata.get('failure_checkpoint_ids', ()) or ()),
            telemetry_summary=dict(result.metadata.get('telemetry_summary', {}) or {}),
            compile_report=dict(result.metadata.get('compile_report', {}) or {}),
            partition_advisory=dict(result.metadata.get('partition_advisory', {}) or {}),
            runtime_metadata=dict(result.metadata.get('runtime_metadata', {}) or {}),
            runtime_manifest_path=(None if not result.metadata.get('runtime_manifest_path') else Path(str(result.metadata.get('runtime_manifest_path')))),
            runtime_bundle_path=(None if result.runtime_bundle_path is None else Path(result.runtime_bundle_path)),
        )

    def resume_runtime_bundle(
        self,
        bundle_dir: Path | str,
        out_dir: Path,
        *,
        execution_profile: str = 'auto',
        device: str | None = None,
        export_stage_series: bool = True,
        partition_count: int | None = None,
        communicator_backend: str | None = None,
        checkpoint_policy: str | None = None,
        checkpoint_dir: str | None = None,
        checkpoint_every_n_increments: int | None = None,
        checkpoint_keep_last_n: int | None = None,
        max_cutbacks: int | None = None,
        max_stage_retries: int | None = None,
        telemetry_level: str = 'standard',
        deterministic: bool = False,
        resume_checkpoint_id: str | None = None,
        backend_preference: str = 'auto',
        native_compatibility_mode: str = 'auto',
        nonlinear_policy: str = 'balanced',
        solver_strategy: str | None = None,
        preconditioner: str | None = None,
        nonlinear_max_iterations: int | None = None,
        tolerance: float | None = None,
        line_search: bool | None = None,
    ) -> JobRunSummary:
        result = GeneralFEMSolver().run_runtime_bundle(
            bundle_dir,
            out_dir,
            execution_profile=execution_profile,
            device=device,
            export_stage_series=export_stage_series,
            partition_count=partition_count,
            communicator_backend=communicator_backend,
            checkpoint_policy=checkpoint_policy,
            checkpoint_dir=checkpoint_dir,
            checkpoint_every_n_increments=checkpoint_every_n_increments,
            checkpoint_keep_last_n=checkpoint_keep_last_n,
            max_cutbacks=max_cutbacks,
            max_stage_retries=max_stage_retries,
            telemetry_level=telemetry_level,
            deterministic=deterministic,
            resume_checkpoint_id=resume_checkpoint_id,
            backend_preference=backend_preference,
            native_compatibility_mode=native_compatibility_mode,
            nonlinear_policy=nonlinear_policy,
            solver_strategy=solver_strategy,
            preconditioner=preconditioner,
            nonlinear_max_iterations=nonlinear_max_iterations,
            tolerance=tolerance,
            line_search=line_search,
        )
        if result.result_store is not None:
            db = build_result_database_from_runtime_store(result.result_store)
        elif result.result_db is not None:
            db = result.result_db
        else:
            db = build_result_database(result.solved_model)
        case_name = str(result.metadata.get('case_name', 'bundle-resume'))
        out_path = Path(out_dir) / f'{case_name}_resume.vtu'
        metadata = dict(result.metadata)
        metadata['runtime_bundle_source'] = str(bundle_dir)
        return JobRunSummary(
            case_name=case_name,
            profile=execution_profile,
            device=device or 'auto',
            out_path=out_path,
            stage_count=len(db.stage_names()),
            field_count=len(db.fields),
            result_db=db,
            metadata=metadata,
            checkpoint_ids=tuple(result.metadata.get('checkpoint_ids', ()) or ()),
            increment_checkpoint_ids=tuple(result.metadata.get('increment_checkpoint_ids', ()) or ()),
            failure_checkpoint_ids=tuple(result.metadata.get('failure_checkpoint_ids', ()) or ()),
            telemetry_summary=dict(result.metadata.get('telemetry_summary', {}) or {}),
            compile_report=dict(result.metadata.get('compile_report', {}) or {}),
            partition_advisory=dict(result.metadata.get('partition_advisory', {}) or {}),
            runtime_metadata=dict(result.metadata.get('runtime_metadata', {}) or {}),
            runtime_manifest_path=(None if not result.metadata.get('runtime_manifest_path') else Path(str(result.metadata.get('runtime_manifest_path')))),
            runtime_bundle_path=(None if result.runtime_bundle_path is None else Path(result.runtime_bundle_path)),
        )


    def blueprint_progress_snapshot(self) -> dict[str, object]:
        return {
            'summary': blueprint_progress_summary(),
            'modules': [item.to_dict() for item in build_blueprint_progress_snapshot()],
            'release_gates': build_release_gate_snapshot(),
        }

    def delivery_audit(self, *, runtime_bundle_dir: str | Path | None = None) -> dict[str, object]:
        return RuntimeBundleManager().delivery_audit_report(runtime_bundle_dir)

    def export_delivery_package(
        self,
        delivery_dir: str | Path,
        *,
        runtime_bundle_dir: str | Path | None = None,
        include_demo_case: bool = True,
        include_blueprint_progress: bool = True,
        include_environment_report: bool = True,
        write_archive: bool = False,
        recovery_report: dict[str, object] | None = None,
        recovery_asset_paths: dict[str, str | Path] | None = None,
    ):
        return RuntimeBundleManager().export_delivery_package(
            delivery_dir,
            runtime_bundle_dir=runtime_bundle_dir,
            include_demo_case=include_demo_case,
            include_blueprint_progress=include_blueprint_progress,
            include_environment_report=include_environment_report,
            write_archive=write_archive,
            recovery_report=recovery_report,
            recovery_asset_paths=recovery_asset_paths,
        )

    def validate_delivery_package(self, delivery_dir: str | Path) -> dict[str, object]:
        return RuntimeBundleManager().validate_delivery_package(delivery_dir)


    def delivery_runtime_profile(self, delivery_dir: str | Path) -> dict[str, object]:
        return RuntimeBundleManager().delivery_runtime_profile(delivery_dir)

    def delivery_profile_markdown(self, delivery_dir: str | Path) -> str:
        return RuntimeBundleManager().render_delivery_profile_markdown(delivery_dir)

    def delivery_smoke_test(self, delivery_dir: str | Path) -> dict[str, object]:
        return RuntimeBundleManager().delivery_smoke_test(delivery_dir)

    def delivery_scene_report(self, delivery_dir: str | Path, *, source: str = 'runtime-bundle') -> dict[str, object]:
        return RuntimeBundleManager().delivery_scene_report(delivery_dir, source=source)

    def delivery_scene_markdown(self, delivery_dir: str | Path, *, source: str = 'runtime-bundle') -> str:
        return RuntimeBundleManager().delivery_scene_markdown(delivery_dir, source=source)

    def blueprint_progress_markdown(self, *, title: str = 'Blueprint Progress Snapshot') -> str:
        return render_blueprint_progress_markdown(title=title)

    def system_readiness_report(
        self,
        *,
        runtime_bundle_dir: str | Path | None = None,
        delivery_dir: str | Path | None = None,
    ) -> dict[str, object]:
        return build_system_readiness_report(
            runtime_bundle_dir=runtime_bundle_dir,
            delivery_dir=delivery_dir,
        ).to_dict()

    def system_readiness_markdown(
        self,
        *,
        runtime_bundle_dir: str | Path | None = None,
        delivery_dir: str | Path | None = None,
        title: str = 'System Readiness Report',
    ) -> str:
        return render_system_readiness_markdown(
            runtime_bundle_dir=runtime_bundle_dir,
            delivery_dir=delivery_dir,
            title=title,
        )



    def runtime_bundle_structural_report(self, bundle_dir: Path | str) -> dict[str, object]:
        return RuntimeBundleManager().bundle_structural_report(bundle_dir)

    def runtime_bundle_structural_markdown(self, bundle_dir: Path | str) -> str:
        return RuntimeBundleManager().render_structural_report_markdown(
            RuntimeBundleManager().bundle_structural_report(bundle_dir)
        )

    def runtime_bundle_tet4_report(self, bundle_dir: Path | str) -> dict[str, object]:
        return RuntimeBundleManager().bundle_tet4_report(bundle_dir)

    def runtime_bundle_tet4_markdown(self, bundle_dir: Path | str) -> str:
        return RuntimeBundleManager().render_tet4_report_markdown(
            RuntimeBundleManager().bundle_tet4_report(bundle_dir)
        )

    def runtime_bundle_native_compatibility_report(self, bundle_dir: Path | str) -> dict[str, object]:
        return RuntimeBundleManager().bundle_native_compatibility_report(bundle_dir)

    def runtime_bundle_native_compatibility_markdown(self, bundle_dir: Path | str) -> str:
        return RuntimeBundleManager().render_native_compatibility_markdown(
            RuntimeBundleManager().bundle_native_compatibility_report(bundle_dir)
        )

    def runtime_bundle_health(self, bundle_dir: Path | str) -> dict[str, object]:
        return RuntimeBundleManager().bundle_health_report(bundle_dir)

    def compare_runtime_bundles(
        self,
        baseline_bundle_dir: Path | str,
        candidate_bundle_dir: Path | str,
        *,
        abs_tol: float = 1.0e-8,
        rel_tol: float = 1.0e-8,
    ) -> dict[str, object]:
        return RuntimeBundleManager().compare_bundles(
            baseline_bundle_dir,
            candidate_bundle_dir,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
        )



    def compare_runtime_bundle_collection(
        self,
        baseline_bundle_dir: Path | str,
        candidate_bundle_dirs: list[Path | str] | tuple[Path | str, ...],
        *,
        abs_tol: float = 1.0e-8,
        rel_tol: float = 1.0e-8,
    ) -> dict[str, object]:
        return RuntimeBundleManager().compare_bundle_collection(
            baseline_bundle_dir,
            candidate_bundle_dirs,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
        )

    def runtime_bundle_lineage(self, bundle_dir: Path | str, *, max_depth: int = 32) -> dict[str, object]:
        return RuntimeBundleManager().bundle_lineage(bundle_dir, max_depth=max_depth)

    def run_runtime_bundle_regression_suite(
        self,
        suite_spec: dict[str, object] | Path | str,
        *,
        write_json_path: Path | str | None = None,
        write_markdown_path: Path | str | None = None,
    ) -> dict[str, object]:
        return RuntimeBundleManager().run_regression_suite(
            suite_spec,
            write_json_path=write_json_path,
            write_markdown_path=write_markdown_path,
        )


__all__ = ['JobPlanSummary', 'JobRunSummary', 'JobService']
