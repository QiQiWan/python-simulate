from __future__ import annotations

from dataclasses import dataclass

from geoai_simkit.validation_rules import normalize_region_name
from typing import Any

from geoai_simkit.core.model import AnalysisStage, SimulationModel
from geoai_simkit.geometry.demo_pit import interface_group_options, support_group_options


@dataclass(frozen=True, slots=True)
class GeometryStructuresRow:
    object_name: str
    role: str
    region: str
    material: str
    structure_status: str
    mesh_control: str


@dataclass(frozen=True, slots=True)
class MeshModeRow:
    object_name: str
    requested_family: str
    actual_family: str
    target_size: str
    refine_ratio: str
    status: str


@dataclass(frozen=True, slots=True)
class StagesModeRow:
    stage_name: str
    stage_role: str
    activate_regions: str
    deactivate_regions: str
    supports: str
    interfaces: str
    solver_profile: str


WORKFLOW_MODE_LABELS: dict[str, str] = {
    'geometry_structures': 'Geometry / Structures',
    'mesh': 'Mesh Mode',
    'stages': 'Stages Mode',
}


def _role_for_record(rec) -> str:
    return str((rec.metadata or {}).get('role') or rec.object_type or '-').strip() or '-'


def _mesh_control_label(metadata: dict[str, Any] | None) -> str:
    ctl = dict((metadata or {}).get('mesh_control') or {})
    if not ctl:
        return 'inherit'
    if not bool(ctl.get('enabled', True)):
        return 'disabled'
    family = str(ctl.get('element_family') or 'inherit').strip() or 'inherit'
    size = ctl.get('target_size')
    ratio = ctl.get('refinement_ratio')
    parts = [family]
    if size not in (None, '', 0):
        try:
            parts.append(f"h={float(size):g}")
        except Exception:
            parts.append(f"h={size}")
    if ratio not in (None, ''):
        try:
            parts.append(f"r={float(ratio):.2f}")
        except Exception:
            parts.append(f"r={ratio}")
    return ' | '.join(parts)


def build_geometry_structures_rows(model: SimulationModel | None) -> list[GeometryStructuresRow]:
    if model is None:
        return []
    structure_sources = {str((item.metadata or {}).get('source_object') or '') for item in model.structures}
    interface_sources = {str((item.metadata or {}).get('source_object') or '') for item in model.interfaces}
    rows: list[GeometryStructuresRow] = []
    for rec in model.object_records:
        mat = model.material_for_region(rec.region_name or '') if rec.region_name else None
        structure_parts: list[str] = []
        if rec.key in structure_sources or rec.name in structure_sources:
            structure_parts.append('structure')
        if rec.key in interface_sources or rec.name in interface_sources:
            structure_parts.append('interface')
        rows.append(
            GeometryStructuresRow(
                object_name=str(rec.name or rec.key),
                role=_role_for_record(rec),
                region=str(rec.region_name or '-'),
                material=str(mat.material_name if mat is not None else '-'),
                structure_status=', '.join(structure_parts) if structure_parts else 'geometry-only',
                mesh_control=_mesh_control_label(rec.metadata),
            )
        )
    return rows


def build_mesh_mode_rows(model: SimulationModel | None) -> list[MeshModeRow]:
    if model is None:
        return []
    region_meta = {region.name: dict(region.metadata or {}) for region in model.region_tags}
    rows: list[MeshModeRow] = []
    for rec in model.object_records:
        ctl = dict((rec.metadata or {}).get('mesh_control') or {})
        requested = str(ctl.get('element_family') or 'inherit').strip() or 'inherit'
        if requested == 'inherit':
            requested = str((rec.metadata or {}).get('preferred_element_family') or model.metadata.get('mesh_engine.requested_family') or 'auto')
        target_size = ctl.get('target_size') or (rec.metadata or {}).get('mesh_target_size') or model.metadata.get('mesh_engine.global_target_size')
        refine = ctl.get('refinement_ratio')
        region_info = region_meta.get(rec.region_name or '', {})
        actual = str(region_info.get('actual_family') or region_info.get('requested_family') or ('meshed' if model.has_volume_mesh() else '-'))
        fallback = str(region_info.get('fallback_reason') or '').strip()
        if not model.has_volume_mesh():
            status = 'geometry-only'
        elif fallback:
            status = f'fallback: {fallback}'
        else:
            status = 'ok'
        rows.append(
            MeshModeRow(
                object_name=str(rec.name or rec.key),
                requested_family=requested,
                actual_family=actual,
                target_size='-' if target_size in (None, '') else f"{float(target_size):g}" if isinstance(target_size, (int, float)) else str(target_size),
                refine_ratio='-' if refine in (None, '') else f"{float(refine):.2f}" if isinstance(refine, (int, float)) else str(refine),
                status=status,
            )
        )
    return rows


def build_stages_mode_rows(model: SimulationModel | None) -> list[StagesModeRow]:
    if model is None:
        return []
    rows: list[StagesModeRow] = []
    for stage in model.stages:
        meta = dict(stage.metadata or {})
        supports = meta.get('active_support_groups') or []
        interfaces = meta.get('active_interface_groups') or []
        preset = str(meta.get('solver_preset') or '-').strip() or '-'
        profile = str(meta.get('compute_profile') or '-').strip() or '-'
        role = str(meta.get('stage_role') or stage.name).strip() or '-'
        strategy = str(meta.get('solver_strategy') or '-').strip() or '-'
        rows.append(
            StagesModeRow(
                stage_name=str(stage.name),
                stage_role=role,
                activate_regions=', '.join(stage.activate_regions) if stage.activate_regions else '-',
                deactivate_regions=', '.join(stage.deactivate_regions) if stage.deactivate_regions else '-',
                supports=', '.join(str(x) for x in supports) if supports else '-',
                interfaces=', '.join(str(x) for x in interfaces) if interfaces else '-',
                solver_profile=f'{preset} / {profile} / {strategy}',
            )
        )
    return rows


def filter_workflow_rows(rows: list[Any], fields: list[str], query: str = '', *, issues_only: bool = False) -> list[Any]:
    q = str(query or '').strip().lower()
    filtered: list[Any] = []
    for row in rows:
        if issues_only:
            text = ' | '.join(str(getattr(row, field, '') or '') for field in fields).lower()
            if not any(token in text for token in ('fallback', 'geometry-only', 'disabled', '-', 'custom')):
                continue
        if q:
            hay = ' | '.join(str(getattr(row, field, '') or '') for field in fields).lower()
            if q not in hay:
                continue
        filtered.append(row)
    return filtered


def _stage_activation_snapshot(model: SimulationModel) -> list[tuple[str, dict[str, bool], list[str], list[str]]]:
    snapshots: list[tuple[str, dict[str, bool], list[str], list[str]]] = []
    current: dict[str, bool] = {}
    known_regions = [str(region.name) for region in model.region_tags]
    region_lookup = {normalize_region_name(name): name for name in known_regions}
    for stage in model.stages:
        meta = dict(stage.metadata or {})
        activation_map = meta.get('activation_map')
        if isinstance(activation_map, dict) and activation_map:
            state = dict(current)
            for key, enabled in activation_map.items():
                actual = region_lookup.get(normalize_region_name(key), str(key))
                state[actual] = bool(enabled)
        else:
            state = dict(current)
            for name in known_regions:
                state.setdefault(name, True)
            for name in stage.activate_regions:
                state[str(name)] = True
            for name in stage.deactivate_regions:
                state[str(name)] = False
        supports = [str(x) for x in (meta.get('active_support_groups') or [])]
        interfaces = [str(x) for x in (meta.get('active_interface_groups') or [])]
        snapshots.append((str(stage.name), state, supports, interfaces))
        current = state
    return snapshots


def stage_activation_map_for_stage(model: SimulationModel | None, stage_name: str) -> dict[str, bool] | None:
    if model is None:
        return None
    for name, state, _supports, _interfaces in _stage_activation_snapshot(model):
        if name == stage_name:
            return dict(state)
    return None


def build_stage_activation_matrix(model: SimulationModel | None) -> tuple[list[str], list[list[str]]]:
    if model is None or not model.stages:
        return (['Stage'], [])
    region_names = sorted({str(region.name) for region in model.region_tags})
    support_groups = list(support_group_options().keys())
    interface_groups = list(interface_group_options().keys())
    support_headers = [f'S:{name}' for name in support_groups]
    interface_headers = [f'I:{name}' for name in interface_groups]
    headers = ['Stage', 'Role', *region_names, *support_headers, *interface_headers]
    rows: list[list[str]] = []
    for stage_name, state, supports, interfaces in _stage_activation_snapshot(model):
        stage_obj = next((s for s in model.stages if str(s.name) == stage_name), None)
        role = str(((stage_obj.metadata if stage_obj is not None else {}) or {}).get('stage_role') or stage_name)
        row = [stage_name, role]
        support_set = {str(x) for x in supports}
        interface_set = {str(x) for x in interfaces}
        for region in region_names:
            row.append('on' if state.get(region, False) else 'off')
        for group in support_groups:
            row.append('on' if group in support_set else 'off')
        for group in interface_groups:
            row.append('on' if group in interface_set else 'off')
        rows.append(row)
    return headers, rows


def update_stage_region_activation(model: SimulationModel | None, stage_name: str, region_name: str, active: bool) -> bool:
    if model is None:
        return False
    snapshots = _stage_activation_snapshot(model)
    stage_index = next((i for i, (name, _state, _supports, _interfaces) in enumerate(snapshots) if name == stage_name), None)
    if stage_index is None:
        return False
    region_names = {str(region.name) for region in model.region_tags}
    if region_name not in region_names:
        return False
    prev_state = dict(snapshots[stage_index - 1][1]) if stage_index > 0 else {}
    current_state = dict(snapshots[stage_index][1])
    current_state[region_name] = bool(active)
    stage = model.stages[stage_index]
    metadata = dict(stage.metadata or {})
    metadata['activation_map'] = dict(current_state)
    activate = tuple(name for name in region_names if current_state.get(name, False) and not prev_state.get(name, True))
    deactivate = tuple(name for name in region_names if (not current_state.get(name, False)) and prev_state.get(name, True))
    model.stages[stage_index] = AnalysisStage(
        name=stage.name,
        activate_regions=activate,
        deactivate_regions=deactivate,
        boundary_conditions=stage.boundary_conditions,
        loads=stage.loads,
        steps=stage.steps,
        metadata=metadata,
    )
    return True


def _update_stage_group_membership(model: SimulationModel | None, stage_name: str, group_name: str, active: bool, *, key: str, valid_groups: set[str]) -> bool:
    if model is None or group_name not in valid_groups:
        return False
    stage_index = next((i for i, stage in enumerate(model.stages) if str(stage.name) == stage_name), None)
    if stage_index is None:
        return False
    stage = model.stages[stage_index]
    metadata = dict(stage.metadata or {})
    groups = [str(x) for x in (metadata.get(key) or []) if str(x)]
    group_set = set(groups)
    if active:
        group_set.add(group_name)
    else:
        group_set.discard(group_name)
    ordered = [name for name in valid_groups if name in group_set]
    preferred_order = list(support_group_options().keys()) if key == 'active_support_groups' else list(interface_group_options().keys())
    metadata[key] = [name for name in preferred_order if name in group_set]
    model.stages[stage_index] = AnalysisStage(
        name=stage.name,
        activate_regions=stage.activate_regions,
        deactivate_regions=stage.deactivate_regions,
        boundary_conditions=stage.boundary_conditions,
        loads=stage.loads,
        steps=stage.steps,
        metadata=metadata,
    )
    return True


def update_stage_support_group(model: SimulationModel | None, stage_name: str, group_name: str, active: bool) -> bool:
    return _update_stage_group_membership(model, stage_name, group_name, active, key='active_support_groups', valid_groups=set(support_group_options().keys()))


def update_stage_interface_group(model: SimulationModel | None, stage_name: str, group_name: str, active: bool) -> bool:
    return _update_stage_group_membership(model, stage_name, group_name, active, key='active_interface_groups', valid_groups=set(interface_group_options().keys()))


def summarize_workflow_modes(model: SimulationModel | None) -> dict[str, str]:
    if model is None:
        return {
            'geometry_structures': '未载入模型。',
            'mesh': '未载入模型。',
            'stages': '未载入模型。',
        }
    bound_regions = sum(1 for rec in model.object_records if rec.region_name and model.material_for_region(rec.region_name))
    geo_text = (
        f'objects={len(model.object_records)} | materials={len(model.materials)} | '
        f'bound_objects={bound_regions} | structures={len(model.structures)} | interfaces={len(model.interfaces)}'
    )
    completed = list(model.metadata.get('mesh_engine.completed_targets') or [])
    requested = sorted({str(item.get('requested_family') or '') for item in completed if item.get('requested_family')})
    actual = sorted({str(item.get('actual_family') or '') for item in completed if item.get('actual_family')})
    mesh_text = (
        f'state={model.geometry_state()} | targets={len(completed)} | '
        f'requested={"/".join(requested) if requested else "-"} | '
        f'actual={"/".join(actual) if actual else "-"}'
    )
    workflow = str(model.metadata.get('demo_stage_workflow') or '-')
    weld_groups = list(((model.metadata.get('mesh_engine') or {}).get('shared_point_weld_groups') or []))
    stage_text = (
        f'stages={len(model.stages)} | results={len(model.results)} | '
        f'workflow={workflow} | welded={"/".join(weld_groups) if weld_groups else "-"} | '
        f'current_pipeline={" -> ".join(stage.name for stage in model.stages[:6]) if model.stages else "-"}'
    )
    return {
        'geometry_structures': geo_text,
        'mesh': mesh_text,
        'stages': stage_text,
    }
