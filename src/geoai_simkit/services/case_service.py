from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from geoai_simkit.core.model import BlockRecord, SimulationModel
from geoai_simkit.pipeline import AnalysisCaseBuilder, AnalysisCaseSpec
from geoai_simkit.pipeline.io import load_case_spec, save_case_spec

@dataclass(slots=True)
class StageBrowserRow:
    name: str
    predecessor: str | None = None
    activate_regions: tuple[str, ...] = ()
    deactivate_regions: tuple[str, ...] = ()
    boundary_condition_count: int = 0
    load_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ModelBrowserSummary:
    model_name: str
    geometry_state: str
    blocks: tuple[BlockRecord, ...]
    stage_rows: tuple[StageBrowserRow, ...]
    object_count: int
    interface_count: int
    interface_element_count: int
    structure_count: int
    result_stage_names: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

class CaseService:
    def load_case(self, path: str | Path) -> AnalysisCaseSpec: return load_case_spec(path)
    def save_case(self, case: AnalysisCaseSpec, path: str | Path) -> Path: return save_case_spec(case, path)
    def prepare_case(self, case: AnalysisCaseSpec) -> SimulationModel: return AnalysisCaseBuilder(case).build().model
    def build_browser_summary(self, model: SimulationModel, *, case: AnalysisCaseSpec | None = None) -> ModelBrowserSummary:
        stages = tuple(getattr(case, 'stages', ()) or ()) if case is not None and getattr(case, 'stages', ()) else tuple(getattr(model, 'stages', ()) or ())
        stage_rows = []
        for s in stages:
            stage_rows.append(StageBrowserRow(str(getattr(s,'name','stage')), getattr(s,'predecessor',None), tuple(getattr(s,'activate_regions',()) or ()), tuple(getattr(s,'deactivate_regions',()) or ()), len(tuple(getattr(s,'boundary_conditions',()) or ())), len(tuple(getattr(s,'loads',()) or ())), dict(getattr(s,'metadata',{}) or {})))
        try: blocks = tuple(model.derive_block_records())
        except Exception: blocks = ()
        return ModelBrowserSummary(
            model_name=model.name,
            geometry_state=model.geometry_state() if hasattr(model, 'geometry_state') else 'geometry',
            blocks=blocks,
            stage_rows=tuple(stage_rows),
            object_count=len(getattr(model, 'object_records', ()) or ()),
            interface_count=len(getattr(model, 'interfaces', ()) or ()),
            interface_element_count=len(getattr(model, 'interface_elements', ()) or ()),
            structure_count=len(getattr(model, 'structures', ()) or ()),
            result_stage_names=tuple(model.result_stage_names()) if hasattr(model, 'result_stage_names') else (),
            metadata={'region_count': len(getattr(model, 'region_tags', ()) or ()), 'material_binding_count': len(getattr(model, 'materials', ()) or ()), 'boundary_condition_count': len(getattr(model, 'boundary_conditions', ()) or ())},
        )
    def list_region_names(self, case: AnalysisCaseSpec) -> tuple[str, ...]: return tuple(self.prepare_case(case).list_region_names())
    def modern_workspace_state(self, case: AnalysisCaseSpec, *, active_space: str, active_view: str, messages=None, document_dirty=False, file_path=None, model_metadata=None):
        return {'contract':'modern_workspace_state_v2', 'active_space': active_space, 'active_view': active_view, 'status_bar': {'case_name': case.name, 'dirty': bool(document_dirty)}, 'notification_center': {'messages': list(messages or [])}, 'command_palette': {'active_space': active_space, 'commands': []}, 'solve_readiness_gate': {'ready': True}}
    def command_palette(self, case: AnalysisCaseSpec, *, active_space: str, active_view: str): return {'active_space': active_space, 'active_view': active_view, 'commands': []}
    def notification_center(self, case: AnalysisCaseSpec, messages=None): return {'messages': list(messages or [])}
    def write_autosave(self, case: AnalysisCaseSpec, root_dir=None, retention=10): return {'autosave_id': 'headless-autosave', 'root_dir': str(root_dir or 'autosave')}
