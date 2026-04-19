from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from geoai_simkit.core.model import BlockRecord, SimulationModel
from geoai_simkit.pipeline import AnalysisCaseBuilder, AnalysisCaseSpec, MaterialAssignmentSpec, StageSpec
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


def _workbench_meta(case: AnalysisCaseSpec) -> dict[str, Any]:
    meta = case.metadata.setdefault('workbench', {})
    if not isinstance(meta, dict):
        case.metadata['workbench'] = {}
        meta = case.metadata['workbench']
    return meta


def _block_overrides(case: AnalysisCaseSpec) -> dict[str, Any]:
    meta = _workbench_meta(case)
    overrides = meta.setdefault('block_overrides', {})
    if not isinstance(overrides, dict):
        meta['block_overrides'] = {}
        overrides = meta['block_overrides']
    return overrides


class CaseService:
    """High-level bridge between portable cases and GUI/browser state."""

    def load_case(self, path: str | Path) -> AnalysisCaseSpec:
        return load_case_spec(path)

    def save_case(self, case: AnalysisCaseSpec, path: str | Path) -> Path:
        return save_case_spec(case, path)

    def prepare_case(self, case: AnalysisCaseSpec) -> SimulationModel:
        return AnalysisCaseBuilder(case).build().model

    def build_browser_summary(self, model: SimulationModel, *, case: AnalysisCaseSpec | None = None) -> ModelBrowserSummary:
        stage_rows: list[StageBrowserRow] = []
        if case is not None and case.stages:
            model_stage_map = {stage.name: stage for stage in model.stages}
            for case_stage in case.stages:
                prepared_stage = model_stage_map.get(case_stage.name)
                stage_rows.append(StageBrowserRow(
                    name=case_stage.name,
                    predecessor=case_stage.predecessor,
                    activate_regions=tuple(prepared_stage.activate_regions if prepared_stage is not None else case_stage.activate_regions),
                    deactivate_regions=tuple(prepared_stage.deactivate_regions if prepared_stage is not None else case_stage.deactivate_regions),
                    boundary_condition_count=len(prepared_stage.boundary_conditions) if prepared_stage is not None else len(case_stage.boundary_conditions),
                    load_count=len(prepared_stage.loads) if prepared_stage is not None else len(case_stage.loads),
                    metadata={**(dict(prepared_stage.metadata) if prepared_stage is not None else {}), **dict(case_stage.metadata)},
                ))
        else:
            predecessor: str | None = None
            for stage in model.stages:
                stage_rows.append(StageBrowserRow(
                    name=stage.name,
                    predecessor=predecessor,
                    activate_regions=tuple(stage.activate_regions),
                    deactivate_regions=tuple(stage.deactivate_regions),
                    boundary_condition_count=len(stage.boundary_conditions),
                    load_count=len(stage.loads),
                    metadata=dict(stage.metadata),
                ))
                predecessor = stage.name
        blocks = tuple(model.derive_block_records())
        if case is not None:
            overrides = _block_overrides(case)
            patched: list[BlockRecord] = []
            for block in blocks:
                override = overrides.get(block.name) or overrides.get(block.region_name or '') or {}
                if isinstance(override, dict) and override:
                    patched.append(replace(
                        block,
                        visible=bool(override.get('visible', block.visible)),
                        locked=bool(override.get('locked', block.locked)),
                        metadata={**dict(block.metadata), 'display_name': str(override.get('display_name', block.name))},
                    ))
                else:
                    patched.append(block)
            blocks = tuple(patched)
        return ModelBrowserSummary(
            model_name=model.name,
            geometry_state=model.geometry_state(),
            blocks=blocks,
            stage_rows=tuple(stage_rows),
            object_count=len(model.object_records),
            interface_count=len(model.interfaces),
            interface_element_count=len(model.interface_elements),
            structure_count=len(model.structures),
            result_stage_names=tuple(model.result_stage_names()),
            metadata={
                'region_count': len(model.region_tags),
                'material_binding_count': len(model.materials),
                'boundary_condition_count': len(model.boundary_conditions),
            },
        )

    def list_region_names(self, case: AnalysisCaseSpec) -> tuple[str, ...]:
        model = self.prepare_case(case)
        return tuple(model.list_region_names())

    def set_block_material(self, case: AnalysisCaseSpec, block_name: str, material_name: str, *, parameters: dict[str, Any] | None = None) -> None:
        payload = dict(parameters or {})
        explicit_assignments: list[MaterialAssignmentSpec] = []
        carried_selector_assignments: list[MaterialAssignmentSpec] = []
        for item in case.materials:
            if item.selector is not None:
                carried_selector_assignments.append(item)
                continue
            for region_name in item.region_names:
                explicit_assignments.append(MaterialAssignmentSpec(region_names=(str(region_name),), material_name=item.material_name, parameters=dict(item.parameters), metadata=dict(item.metadata)))
        explicit_assignments = [item for item in explicit_assignments if item.region_names and item.region_names[0] != block_name]
        explicit_assignments.append(MaterialAssignmentSpec(region_names=(block_name,), material_name=material_name, parameters=payload))
        explicit_assignments.sort(key=lambda item: item.region_names[0] if item.region_names else '')
        case.materials = tuple([*explicit_assignments, *carried_selector_assignments])

    def set_block_flags(self, case: AnalysisCaseSpec, block_name: str, *, visible: bool | None = None, locked: bool | None = None, display_name: str | None = None) -> None:
        overrides = _block_overrides(case)
        entry = overrides.setdefault(block_name, {})
        if not isinstance(entry, dict):
            entry = {}
            overrides[block_name] = entry
        if visible is not None:
            entry['visible'] = bool(visible)
        if locked is not None:
            entry['locked'] = bool(locked)
        if display_name is not None:
            entry['display_name'] = str(display_name)

    def add_stage(self, case: AnalysisCaseSpec, name: str, *, copy_from: str | None = None) -> None:
        stages = list(case.stages)
        if any(stage.name == name for stage in stages):
            raise ValueError(f'Stage already exists: {name}')
        if copy_from is None:
            predecessor = stages[-1].name if stages else None
            stages.append(StageSpec(name=name, predecessor=predecessor))
        else:
            source = next((stage for stage in stages if stage.name == copy_from), None)
            if source is None:
                raise KeyError(f'Stage not found: {copy_from}')
            stages.append(replace(source, name=name, predecessor=source.name, metadata=dict(source.metadata)))
        case.stages = tuple(stages)

    def clone_stage(self, case: AnalysisCaseSpec, source_name: str, new_name: str) -> None:
        self.add_stage(case, new_name, copy_from=source_name)

    def remove_stage(self, case: AnalysisCaseSpec, stage_name: str) -> None:
        removed = next((stage for stage in case.stages if stage.name == stage_name), None)
        if removed is None:
            return
        rewired: list[StageSpec] = []
        for stage in case.stages:
            if stage.name == stage_name:
                continue
            predecessor = stage.predecessor
            if predecessor == stage_name:
                predecessor = removed.predecessor
            rewired.append(replace(stage, predecessor=predecessor))
        case.stages = tuple(rewired)

    def set_stage_predecessor(self, case: AnalysisCaseSpec, stage_name: str, predecessor: str | None) -> None:
        stage_names = {stage.name for stage in case.stages}
        if stage_name not in stage_names:
            raise KeyError(f'Stage not found: {stage_name}')
        if predecessor is not None and predecessor not in stage_names:
            raise KeyError(f'Predecessor stage not found: {predecessor}')
        updated: list[StageSpec] = []
        for stage in case.stages:
            if stage.name == stage_name:
                updated.append(replace(stage, predecessor=predecessor))
            else:
                updated.append(stage)
        case.stages = tuple(updated)

    def set_stage_region_state(self, case: AnalysisCaseSpec, stage_name: str, region_name: str, active: bool) -> None:
        stages = list(case.stages)
        for idx, stage in enumerate(stages):
            if stage.name != stage_name:
                continue
            activation_map = dict(stage.activation_map or stage.metadata.get('activation_map') or {})
            activation_map[str(region_name)] = bool(active)
            activate_regions = [name for name in stage.activate_regions if name != region_name]
            deactivate_regions = [name for name in stage.deactivate_regions if name != region_name]
            if active:
                activate_regions.append(region_name)
            else:
                deactivate_regions.append(region_name)
            metadata = dict(stage.metadata)
            metadata['activation_map'] = activation_map
            stages[idx] = replace(
                stage,
                activation_map=activation_map,
                activate_regions=tuple(dict.fromkeys(activate_regions)),
                deactivate_regions=tuple(dict.fromkeys(deactivate_regions)),
                metadata=metadata,
            )
            case.stages = tuple(stages)
            return
        raise KeyError(f'Stage not found: {stage_name}')

    def stage_activation_state(self, case: AnalysisCaseSpec, stage_name: str, region_name: str) -> bool | None:
        stage = next((item for item in case.stages if item.name == stage_name), None)
        if stage is None:
            return None
        activation_map = dict(stage.activation_map or stage.metadata.get('activation_map') or {})
        if region_name in activation_map:
            return bool(activation_map[region_name])
        if region_name in stage.activate_regions:
            return True
        if region_name in stage.deactivate_regions:
            return False
        return None

    def set_mesh_global_size(self, case: AnalysisCaseSpec, size: float) -> None:
        case.mesh = replace(case.mesh, global_size=float(size))


__all__ = ['CaseService', 'ModelBrowserSummary', 'StageBrowserRow']
