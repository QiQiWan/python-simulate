from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from geoai_simkit.app.workbench import WorkbenchDocument

PrimarySpace = Literal['modeling', 'mesh', 'solve', 'results', 'benchmark', 'advanced', 'project', 'model', 'diagnostics', 'delivery']
WorkbenchViewMode = Literal['workflow', 'scene', 'expert']


@dataclass(slots=True)
class NavigationItem:
    key: PrimarySpace
    label: str
    state: str = 'idle'
    summary: str = ''
    badge: str | None = None
    recommended: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'key': self.key,
            'label': self.label,
            'state': self.state,
            'summary': self.summary,
            'badge': self.badge,
            'recommended': self.recommended,
            'metadata': dict(self.metadata),
        }


@dataclass(slots=True)
class ViewModeOption:
    key: WorkbenchViewMode
    label: str
    enabled: bool = True
    recommended: bool = False
    summary: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'key': self.key,
            'label': self.label,
            'enabled': self.enabled,
            'recommended': self.recommended,
            'summary': self.summary,
        }


def build_primary_navigation(document: WorkbenchDocument) -> tuple[NavigationItem, ...]:
    validation = document.validation
    preprocess = document.preprocess
    results = document.results
    readiness = dict(document.metadata.get('system_readiness', {}) or {})
    issues = 0 if validation is None else int(validation.error_count + validation.warning_count)
    bundle_path = document.metadata.get('runtime_bundle_path') or document.metadata.get('resumed_runtime_bundle_path')
    return (
        NavigationItem(
            key='modeling',
            label='Modeling',
            state='ready' if document.file_path else 'draft',
            summary=document.file_path or f"{document.case.name} modelling workspace",
            badge='dirty' if document.dirty else None,
            recommended=document.file_path is None,
        ),
        NavigationItem(
            key='mesh',
            label='Mesh',
            state=str(document.browser.geometry_state or 'unknown'),
            summary=f"{document.browser.object_count} objects · {len(document.browser.blocks)} blocks · mesh/stage context",
            badge=str(len(document.browser.blocks)) if document.browser.blocks else None,
            recommended=document.mode in {'geometry', 'partition', 'mesh', 'assign', 'stage'},
        ),
        NavigationItem(
            key='solve',
            label='Solve',
            state='ready' if (validation is not None and validation.ok and preprocess is not None) else 'attention',
            summary=(
                f"Validation ok · {preprocess.n_interface_candidates} interface candidates"
                if validation is not None and validation.ok and preprocess is not None
                else ('Validation pending' if validation is None else f"{validation.error_count} errors · {validation.warning_count} warnings")
            ),
            badge=None if validation is None else str(validation.error_count + validation.warning_count),
            recommended=validation is None or not validation.ok,
            metadata={'compile_report_available': bool(document.compile_report), 'checkpoint_count': len(document.checkpoint_ids)},
        ),
        NavigationItem(
            key='results',
            label='Results',
            state='ready' if results is not None else 'empty',
            summary=f"{results.stage_count} stages · {results.field_count} fields" if results is not None else 'No result database loaded yet',
            badge=None if results is None else str(results.stage_count),
            recommended=results is not None,
        ),
        NavigationItem(
            key='benchmark',
            label='Benchmark',
            state='attention' if issues else 'ready',
            summary=(f"{issues} validation/benchmark issues · {len(document.messages)} messages" if issues else f"Benchmark and diagnostics · {len(document.messages)} messages"),
            badge=str(issues) if issues else None,
            recommended=issues > 0,
        ),
        NavigationItem(
            key='advanced',
            label='Advanced',
            state='ready' if bundle_path else str(readiness.get('readiness_level', 'planning')),
            summary=str(bundle_path) if bundle_path else 'GPU / OCC / UQ advanced tracks and export tools',
            badge='bundle' if bundle_path else None,
            recommended=bool(bundle_path),
            metadata={'runtime_bundle_path': bundle_path, 'readiness': readiness},
        ),
    )


def build_view_mode_options(document: WorkbenchDocument) -> tuple[ViewModeOption, ...]:
    has_scene = not bool(getattr(document.model, 'metadata', {}).get('headless_placeholder')) if document.model is not None else False
    has_results = document.results is not None
    issues = 0 if document.validation is None else int(document.validation.error_count + document.validation.warning_count)
    return (
        ViewModeOption('workflow', 'Workflow', enabled=True, recommended=document.mode in {'solve', 'stage', 'geometry'}, summary='Step-by-step case editing, validation, run, and export.'),
        ViewModeOption('scene', 'Scene', enabled=has_scene, recommended=has_scene and document.mode in {'geometry', 'partition', 'mesh', 'assign', 'stage'}, summary='Scene-centric editing with model/stage context and viewport assets.'),
        ViewModeOption('expert', 'Expert', enabled=True, recommended=bool(document.compile_report or document.telemetry_summary or issues or has_results), summary='Compile/runtime details, diagnostics, readiness, and delivery assets.'),
    )
