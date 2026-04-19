from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any

import numpy as np

from geoai_simkit.core.model import SimulationModel, StructuralElementDefinition
from geoai_simkit.pipeline.preprocess import _filter_point_ids_by_target
from geoai_simkit.pipeline.selectors import collect_region_point_ids, union_region_names
from geoai_simkit.pipeline.specs import StructureGeneratorSpec

StructureGenerator = Callable[[SimulationModel, dict[str, Any]], list[StructuralElementDefinition]]

_STRUCTURE_GENERATORS: dict[str, StructureGenerator] = {}


def register_structure_generator(kind: str, builder: StructureGenerator) -> None:
    key = str(kind).strip()
    if not key:
        raise ValueError('Structure generator kind must be a non-empty string.')
    _STRUCTURE_GENERATORS[key] = builder


def registered_structure_generators() -> tuple[str, ...]:
    return tuple(sorted(_STRUCTURE_GENERATORS))


def resolve_registered_structure_generator(kind: str, model: SimulationModel, parameters: dict[str, Any] | None = None) -> list[StructuralElementDefinition]:
    key = str(kind).strip()
    if key not in _STRUCTURE_GENERATORS:
        raise KeyError(f'Unknown structure generator kind: {kind!r}')
    return list(_STRUCTURE_GENERATORS[key](model, dict(parameters or {})))


def _apply_structure_metadata(items: Iterable[StructuralElementDefinition], extra: dict[str, Any] | None = None) -> list[StructuralElementDefinition]:
    payload = dict(extra or {})
    if not payload:
        return [replace(item) for item in items]
    out: list[StructuralElementDefinition] = []
    for item in items:
        meta = dict(item.metadata or {})
        meta.update(payload)
        out.append(replace(item, metadata=meta))
    return out


def _selector_from_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    from geoai_simkit.pipeline.specs import RegionSelectorSpec

    return RegionSelectorSpec(
        names=tuple(str(v) for v in payload.get('names', ())),
        patterns=tuple(str(v) for v in payload.get('patterns', ())),
        metadata=dict(payload.get('metadata') or {}),
        exclude_names=tuple(str(v) for v in payload.get('exclude_names', ())),
        exclude_patterns=tuple(str(v) for v in payload.get('exclude_patterns', ())),
    )


def _resolve_structure_region_names(model: SimulationModel, parameters: dict[str, Any]) -> tuple[str, ...]:
    explicit = tuple(str(v) for v in parameters.get('region_names', ()) if str(v))
    selector = _selector_from_payload(parameters.get('selector'))
    return union_region_names(model, explicit_names=explicit, selector=selector)


def _dedupe_sorted_point_ids(points: np.ndarray, point_ids: np.ndarray, axis: int, *, tol: float) -> list[int]:
    if point_ids.size == 0:
        return []
    coords = np.asarray(points[point_ids], dtype=float)
    order = np.argsort(coords[:, axis], kind='mergesort')
    ordered = np.asarray(point_ids[order], dtype=np.int64)
    out: list[int] = []
    last_point: np.ndarray | None = None
    for pid in ordered.tolist():
        pt = np.asarray(points[int(pid)], dtype=float)
        if last_point is not None and float(np.linalg.norm(pt - last_point)) <= float(max(tol, 1.0e-9)):
            continue
        out.append(int(pid))
        last_point = pt
    return out


def _resolve_sort_axis(points: np.ndarray, point_ids: np.ndarray, axis_name: str) -> int:
    norm = str(axis_name or 'auto').strip().lower()
    mapping = {'x': 0, 'y': 1, 'z': 2}
    if norm in mapping:
        return mapping[norm]
    pts = np.asarray(points[point_ids], dtype=float)
    if pts.size == 0:
        return 0
    spans = np.ptp(pts, axis=0)
    return int(np.argmax(spans[: min(3, spans.shape[0])]))


def _generate_chain_structures(model: SimulationModel, parameters: dict[str, Any]) -> list[StructuralElementDefinition]:
    region_names = _resolve_structure_region_names(model, parameters)
    if not region_names:
        return []
    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    point_ids = collect_region_point_ids(model, region_names)
    point_ids = _filter_point_ids_by_target(points, point_ids, str(parameters.get('target', 'all')), tol=float(parameters.get('target_tolerance', 1.0e-8)))
    if point_ids.size < 2:
        return []
    axis = _resolve_sort_axis(points, point_ids, str(parameters.get('sort_axis', 'auto')))
    tol = float(parameters.get('point_merge_tolerance', 1.0e-8))
    ordered = _dedupe_sorted_point_ids(points, point_ids, axis, tol=tol)
    if len(ordered) < 2:
        return []
    element_kind = str(parameters.get('element_kind', 'truss2'))
    element_parameters = dict(parameters.get('element_parameters') or {})
    active_stages = tuple(str(v) for v in parameters.get('active_stages', ()) if str(v))
    name_prefix = str(parameters.get('name_prefix') or 'chain')
    close_loop = bool(parameters.get('close_loop', False))
    pair_mode = str(parameters.get('pair_mode', 'chain')).strip().lower()
    pairs: list[tuple[int, int]] = []
    if pair_mode == 'pairs':
        for start in range(0, len(ordered) - 1, 2):
            pairs.append((ordered[start], ordered[start + 1]))
    else:
        for start in range(len(ordered) - 1):
            pairs.append((ordered[start], ordered[start + 1]))
        if close_loop and len(ordered) > 2:
            pairs.append((ordered[-1], ordered[0]))
    out: list[StructuralElementDefinition] = []
    for index, (a, b) in enumerate(pairs, start=1):
        meta = {
            'generator_kind': 'region_point_chain',
            'region_names': list(region_names),
            'sort_axis': axis,
            'pair_mode': pair_mode,
            'target': str(parameters.get('target', 'all')),
        }
        out.append(
            StructuralElementDefinition(
                name=f'{name_prefix}_{index:03d}',
                kind=element_kind,
                point_ids=(int(a), int(b)),
                parameters=dict(element_parameters),
                active_stages=active_stages,
                metadata=meta,
            )
        )
    return out


def _generate_extreme_pair(model: SimulationModel, parameters: dict[str, Any]) -> list[StructuralElementDefinition]:
    region_names = _resolve_structure_region_names(model, parameters)
    if not region_names:
        return []
    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    point_ids = collect_region_point_ids(model, region_names)
    point_ids = _filter_point_ids_by_target(points, point_ids, str(parameters.get('target', 'all')), tol=float(parameters.get('target_tolerance', 1.0e-8)))
    if point_ids.size < 2:
        return []
    axis = _resolve_sort_axis(points, point_ids, str(parameters.get('sort_axis', 'auto')))
    coords = np.asarray(points[point_ids], dtype=float)
    order = np.argsort(coords[:, axis], kind='mergesort')
    ordered = np.asarray(point_ids[order], dtype=np.int64)
    first = int(ordered[0])
    last = int(ordered[-1])
    if first == last:
        return []
    name = str(parameters.get('name') or parameters.get('name_prefix') or 'extreme_pair')
    element_kind = str(parameters.get('element_kind', 'truss2'))
    element_parameters = dict(parameters.get('element_parameters') or {})
    active_stages = tuple(str(v) for v in parameters.get('active_stages', ()) if str(v))
    meta = {
        'generator_kind': 'region_extreme_pair',
        'region_names': list(region_names),
        'sort_axis': axis,
        'target': str(parameters.get('target', 'all')),
    }
    return [
        StructuralElementDefinition(
            name=name,
            kind=element_kind,
            point_ids=(first, last),
            parameters=element_parameters,
            active_stages=active_stages,
            metadata=meta,
        )
    ]


def resolve_structure_entries(model: SimulationModel, entries: tuple[StructuralElementDefinition | StructureGeneratorSpec, ...]) -> tuple[list[StructuralElementDefinition], list[str], list[str]]:
    resolved: list[StructuralElementDefinition] = []
    generated_names: list[str] = []
    notes: list[str] = []
    for entry in entries:
        if isinstance(entry, StructuralElementDefinition):
            resolved.append(entry)
            continue
        generated = resolve_registered_structure_generator(entry.kind, model, entry.parameters)
        generated = _apply_structure_metadata(generated, entry.metadata)
        if not generated:
            notes.append(f'Structure generator {entry.kind!r} produced no elements.')
            continue
        resolved.extend(generated)
        generated_names.extend([item.name for item in generated])
    return resolved, generated_names, notes


def _demo_pit_supports(model: SimulationModel, parameters: dict[str, Any]) -> list[StructuralElementDefinition]:
    from geoai_simkit.geometry.demo_pit import AUTO_SUPPORT_SOURCE, build_demo_support_structures, normalize_enabled_support_groups

    enabled = parameters.get('enabled_groups')
    if enabled is not None:
        model.metadata['demo_enabled_support_groups'] = list(normalize_enabled_support_groups(enabled))
    items = build_demo_support_structures(model)
    default_meta = {'generator_kind': 'demo_pit_supports', 'source': AUTO_SUPPORT_SOURCE}
    out: list[StructuralElementDefinition] = []
    for item in items:
        meta = dict(item.metadata or {})
        meta.update(default_meta)
        out.append(replace(item, metadata=meta))
    return out


register_structure_generator('demo_pit_supports', _demo_pit_supports)
register_structure_generator('region_point_chain', _generate_chain_structures)
register_structure_generator('region_extreme_pair', _generate_extreme_pair)
