from __future__ import annotations

from fnmatch import fnmatchcase

import numpy as np

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.pipeline.specs import RegionSelectorSpec


def coerce_region_selector(selector: RegionSelectorSpec | dict | None) -> RegionSelectorSpec | None:
    if selector is None or isinstance(selector, RegionSelectorSpec):
        return selector
    if isinstance(selector, dict):
        return RegionSelectorSpec(
            names=tuple(str(v) for v in selector.get('names', ())),
            patterns=tuple(str(v) for v in selector.get('patterns', ())),
            metadata=dict(selector.get('metadata') or {}),
            exclude_names=tuple(str(v) for v in selector.get('exclude_names', ())),
            exclude_patterns=tuple(str(v) for v in selector.get('exclude_patterns', ())),
        )
    raise TypeError(f'Unsupported selector payload: {type(selector).__name__}')


def resolve_region_selector(model: SimulationModel, selector: RegionSelectorSpec | dict | None) -> tuple[str, ...]:
    selector = coerce_region_selector(selector)
    if selector is None:
        return ()
    model.ensure_regions()
    out: list[str] = []
    for region in model.region_tags:
        name = str(region.name)
        meta = dict(region.metadata or {})
        if selector.names and name not in selector.names:
            continue
        if selector.patterns and not any(fnmatchcase(name, pattern) for pattern in selector.patterns):
            continue
        if selector.metadata and any(meta.get(key) != value for key, value in selector.metadata.items()):
            continue
        if selector.exclude_names and name in selector.exclude_names:
            continue
        if selector.exclude_patterns and any(fnmatchcase(name, pattern) for pattern in selector.exclude_patterns):
            continue
        out.append(name)
    return tuple(dict.fromkeys(out))



def union_region_names(model: SimulationModel, *, explicit_names: tuple[str, ...] = (), selector: RegionSelectorSpec | dict | None = None) -> tuple[str, ...]:
    names = [str(name) for name in explicit_names if str(name)]
    if selector is not None:
        names.extend(resolve_region_selector(model, selector))
    return tuple(dict.fromkeys(names))



def collect_region_point_ids(model: SimulationModel, region_names: tuple[str, ...]) -> np.ndarray:
    if not region_names:
        return np.empty((0,), dtype=np.int64)
    model.ensure_regions()
    grid = model.to_unstructured_grid()
    point_ids: set[int] = set()
    wanted = {str(name) for name in region_names}
    cell_ids: list[int] = []
    for region in model.region_tags:
        if str(region.name) in wanted:
            cell_ids.extend(int(cid) for cid in np.asarray(region.cell_ids, dtype=np.int64).tolist())
    for cid in cell_ids:
        try:
            cell = grid.get_cell(int(cid))
        except Exception:
            continue
        for pid in np.asarray(getattr(cell, 'point_ids', ()), dtype=np.int64).tolist():
            point_ids.add(int(pid))
    if not point_ids:
        return np.empty((0,), dtype=np.int64)
    return np.asarray(sorted(point_ids), dtype=np.int64)
