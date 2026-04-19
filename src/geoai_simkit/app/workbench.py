from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import inspect
from typing import Any, Literal

from geoai_simkit.app.case_service import CaseService, ModelBrowserSummary
from geoai_simkit.app.job_service import JobPlanSummary, JobRunSummary, JobService
from geoai_simkit.app.preprocess_service import PreprocessOverview, PreprocessService
from geoai_simkit.app.results_service import ResultsOverview, ResultsService
from geoai_simkit.app.validation_service import ValidationOverview, ValidationService
from geoai_simkit.core.model import SimulationModel
from geoai_simkit.pipeline import AnalysisCaseSpec, StageSpec
from geoai_simkit.results import ResultDatabase

WorkbenchMode = Literal['geometry', 'partition', 'mesh', 'assign', 'stage', 'solve', 'results']


@dataclass(slots=True)
class WorkbenchDocument:
    case: AnalysisCaseSpec
    model: SimulationModel
    mode: WorkbenchMode
    browser: ModelBrowserSummary
    preprocess: PreprocessOverview | None = None
    results: ResultsOverview | None = None
    validation: ValidationOverview | None = None
    result_db: ResultDatabase | None = None
    job_plan: JobPlanSummary | None = None
    compile_report: dict[str, Any] | None = None
    telemetry_summary: dict[str, Any] = field(default_factory=dict)
    checkpoint_ids: tuple[str, ...] = ()
    increment_checkpoint_ids: tuple[str, ...] = ()
    failure_checkpoint_ids: tuple[str, ...] = ()
    file_path: str | None = None
    dirty: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


class WorkbenchService:
    def __init__(self) -> None:
        self.case_service = CaseService()
        self.preprocess_service = PreprocessService()
        self.results_service = ResultsService()
        self.job_service = JobService()
        self.validation_service = ValidationService()

    def document_from_case(self, case: AnalysisCaseSpec, *, mode: WorkbenchMode = 'geometry', file_path: str | None = None) -> WorkbenchDocument:
        model = self.case_service.prepare_case(case)
        return self.document_from_model(model, case=case, mode=mode, file_path=file_path)

    def document_from_model(self, model: SimulationModel, *, case: AnalysisCaseSpec, mode: WorkbenchMode = 'geometry', file_path: str | None = None) -> WorkbenchDocument:
        browser = self.case_service.build_browser_summary(model, case=case)
        preprocess = self.preprocess_service.build_overview(case)
        result_db = self.results_service.build_database(model) if model.results else None
        results = self.results_service.overview_from_database(result_db) if result_db is not None else None
        validation = self.validation_service.build_overview(case)
        return WorkbenchDocument(
            case=case,
            model=model,
            mode=mode,
            browser=browser,
            preprocess=preprocess,
            results=results,
            validation=validation,
            result_db=result_db,
            file_path=file_path,
            metadata={'model_name': model.name, 'has_results': bool(model.results)},
        )

    def load_document(self, path: str | Path, *, mode: WorkbenchMode = 'geometry') -> WorkbenchDocument:
        case = self.case_service.load_case(path)
        return self.document_from_case(case, mode=mode, file_path=str(path))

    def save_document(self, document: WorkbenchDocument, path: str | Path | None = None) -> Path:
        target = Path(path or document.file_path or f'{document.case.name}.json')
        saved = self.case_service.save_case(document.case, target)
        document.file_path = str(saved)
        document.dirty = False
        document.messages.append(f'Saved case to {saved}')
        return saved

    def refresh_document(self, document: WorkbenchDocument, *, preserve_results: bool = False) -> WorkbenchDocument:
        refreshed = self.document_from_case(document.case, mode=document.mode, file_path=document.file_path)
        refreshed.dirty = document.dirty
        if preserve_results:
            refreshed.results = document.results
            refreshed.result_db = document.result_db
            refreshed.compile_report = document.compile_report
            refreshed.telemetry_summary = dict(document.telemetry_summary)
            refreshed.checkpoint_ids = tuple(document.checkpoint_ids)
            refreshed.increment_checkpoint_ids = tuple(document.increment_checkpoint_ids)
            refreshed.failure_checkpoint_ids = tuple(document.failure_checkpoint_ids)
            refreshed.metadata.update(dict(document.metadata))
        refreshed.messages = ['Refreshed model/preprocess/validation state from case edits.', *document.messages]
        return refreshed

    def validate_document(self, document: WorkbenchDocument) -> ValidationOverview:
        validation = self.validation_service.build_overview(document.case)
        document.validation = validation
        document.messages.append(
            f'Validation updated: ok={validation.ok} errors={validation.error_count} warnings={validation.warning_count}.'
        )
        return validation

    def set_mode(self, document: WorkbenchDocument, mode: WorkbenchMode) -> None:
        document.mode = mode

    def _materialize_stage_rows(self, document: WorkbenchDocument) -> None:
        explicit_stage_names = {stage.name for stage in document.case.stages}
        if explicit_stage_names == {row.name for row in document.browser.stage_rows} and explicit_stage_names:
            return
        document.case.stages = tuple(
            StageSpec(
                name=row.name,
                predecessor=row.predecessor,
                activate_regions=tuple(row.activate_regions),
                deactivate_regions=tuple(row.deactivate_regions),
                metadata=dict(row.metadata),
            )
            for row in document.browser.stage_rows
        )

    def set_block_material(self, document: WorkbenchDocument, block_name: str, material_name: str, *, parameters: dict[str, Any] | None = None) -> None:
        self.case_service.set_block_material(document.case, block_name, material_name, parameters=parameters)
        document.dirty = True
        document.messages.append(f'Updated material for {block_name} -> {material_name}.')

    def set_block_flags(self, document: WorkbenchDocument, block_name: str, *, visible: bool | None = None, locked: bool | None = None, display_name: str | None = None) -> None:
        self.case_service.set_block_flags(document.case, block_name, visible=visible, locked=locked, display_name=display_name)
        document.dirty = True
        document.messages.append(f'Updated block flags for {block_name}.')

    def add_stage(self, document: WorkbenchDocument, stage_name: str, *, copy_from: str | None = None) -> None:
        explicit_stage_names = {stage.name for stage in document.case.stages}
        if copy_from is None or copy_from in explicit_stage_names:
            self.case_service.add_stage(document.case, stage_name, copy_from=copy_from)
        else:
            source_row = next((row for row in document.browser.stage_rows if row.name == copy_from), None)
            if source_row is None:
                raise KeyError(f'Stage not found: {copy_from}')
            stages = list(document.case.stages)
            stages.append(StageSpec(
                name=stage_name,
                activate_regions=tuple(source_row.activate_regions),
                deactivate_regions=tuple(source_row.deactivate_regions),
                metadata=dict(source_row.metadata),
            ))
            document.case.stages = tuple(stages)
        source_row = next((row for row in document.browser.stage_rows if row.name == (copy_from or '')), None)
        new_row = replace(
            source_row,
            name=stage_name,
            predecessor=source_row.name,
        ) if source_row is not None else None
        if new_row is None:
            predecessor = document.case.stages[-1].predecessor if document.case.stages else None
            from geoai_simkit.app.case_service import StageBrowserRow

            new_row = StageBrowserRow(name=stage_name, predecessor=predecessor)
        document.browser = replace(
            document.browser,
            stage_rows=tuple([*document.browser.stage_rows, new_row]),
        )
        document.dirty = True
        document.messages.append(f'Added stage {stage_name}.')

    def clone_stage(self, document: WorkbenchDocument, source_name: str, new_name: str) -> None:
        self.add_stage(document, new_name, copy_from=source_name)
        document.messages.append(f'Cloned stage {source_name} -> {new_name}.')

    def remove_stage(self, document: WorkbenchDocument, stage_name: str) -> None:
        self._materialize_stage_rows(document)
        self.case_service.remove_stage(document.case, stage_name)
        document.dirty = True
        document.messages.append(f'Removed stage {stage_name}.')

    def set_stage_predecessor(self, document: WorkbenchDocument, stage_name: str, predecessor: str | None) -> None:
        self._materialize_stage_rows(document)
        self.case_service.set_stage_predecessor(document.case, stage_name, predecessor)
        document.dirty = True
        document.messages.append(f'Set predecessor for {stage_name} -> {predecessor or "<root>"}.')

    def set_stage_region_state(self, document: WorkbenchDocument, stage_name: str, region_name: str, active: bool) -> None:
        self._materialize_stage_rows(document)
        self.case_service.set_stage_region_state(document.case, stage_name, region_name, active)
        document.dirty = True
        document.messages.append(f'Set {region_name} active={active} in stage {stage_name}.')

    def stage_region_state(self, document: WorkbenchDocument, stage_name: str, region_name: str) -> bool | None:
        return self.case_service.stage_activation_state(document.case, stage_name, region_name)

    def set_mesh_global_size(self, document: WorkbenchDocument, size: float) -> None:
        self.case_service.set_mesh_global_size(document.case, size)
        document.dirty = True
        document.messages.append(f'Updated global mesh size -> {size}.')

    def plan_document(
        self,
        document: WorkbenchDocument,
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
    ) -> JobPlanSummary:
        call_kwargs = {
            'execution_profile': execution_profile,
            'device': device,
            'partition_count': partition_count,
            'communicator_backend': communicator_backend,
            'checkpoint_policy': checkpoint_policy,
            'checkpoint_dir': checkpoint_dir,
            'checkpoint_every_n_increments': checkpoint_every_n_increments,
            'checkpoint_keep_last_n': checkpoint_keep_last_n,
            'max_cutbacks': max_cutbacks,
            'max_stage_retries': max_stage_retries,
            'telemetry_level': telemetry_level,
            'deterministic': deterministic,
            'resume_checkpoint_id': resume_checkpoint_id,
        }
        supported = inspect.signature(self.job_service.plan_case).parameters
        plan = self.job_service.plan_case(document.case, **{key: value for key, value in call_kwargs.items() if key in supported})
        document.job_plan = plan
        document.compile_report = dict(plan.metadata.get('compile_report', {}) or {})
        document.metadata['partition_advisory'] = dict(plan.partition_advisory)
        document.metadata['stage_execution_diagnostics'] = dict(plan.stage_execution_diagnostics)
        document.messages.append(f'Planned job profile={plan.profile} device={plan.device}.')
        return plan

    def run_document(
        self,
        document: WorkbenchDocument,
        out_dir: str | Path,
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
    ) -> JobRunSummary:
        call_kwargs = {
            'execution_profile': execution_profile,
            'device': device,
            'export_stage_series': export_stage_series,
            'partition_count': partition_count,
            'communicator_backend': communicator_backend,
            'checkpoint_policy': checkpoint_policy,
            'checkpoint_dir': checkpoint_dir,
            'checkpoint_every_n_increments': checkpoint_every_n_increments,
            'checkpoint_keep_last_n': checkpoint_keep_last_n,
            'max_cutbacks': max_cutbacks,
            'max_stage_retries': max_stage_retries,
            'telemetry_level': telemetry_level,
            'deterministic': deterministic,
            'resume_checkpoint_id': resume_checkpoint_id,
        }
        supported = inspect.signature(self.job_service.run_case).parameters
        run = self.job_service.run_case(document.case, Path(out_dir), **{key: value for key, value in call_kwargs.items() if key in supported})
        document.result_db = run.result_db
        document.results = self.results_service.overview_from_database(run.result_db)
        document.mode = 'results'
        document.compile_report = dict(run.compile_report)
        document.telemetry_summary = dict(run.telemetry_summary)
        document.checkpoint_ids = tuple(run.checkpoint_ids)
        document.increment_checkpoint_ids = tuple(run.increment_checkpoint_ids)
        document.failure_checkpoint_ids = tuple(run.failure_checkpoint_ids)
        document.metadata['partition_advisory'] = dict(run.partition_advisory)
        document.metadata['runtime_metadata'] = dict(run.runtime_metadata)
        document.metadata['runtime_manifest_path'] = (
            None
            if run.runtime_manifest_path is None
            else str(run.runtime_manifest_path)
        )
        document.messages.append(f'Completed job export -> {run.out_path}.')
        return run


__all__ = ['WorkbenchDocument', 'WorkbenchMode', 'WorkbenchService']
