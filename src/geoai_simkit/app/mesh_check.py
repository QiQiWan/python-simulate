from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter, defaultdict
from typing import Any
import math
import numpy as np

from geoai_simkit.core.model import SimulationModel

VTK_CELL_NAMES = {
    1: 'vertex', 3: 'line', 5: 'triangle', 7: 'polygon', 9: 'quad', 10: 'tetra',
    12: 'hexahedron', 13: 'wedge', 14: 'pyramid', 24: 'quadratic tetra', 25: 'quadratic hexahedron'
}
SURFACE_TYPES = {3, 5, 7, 9}
VOLUME_TYPES = {10, 12, 13, 14, 24, 25}
HEX_EDGES = ((0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7))
TET_EDGES = ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))

@dataclass(slots=True)
class MeshRegionInfo:
    region_name: str
    cells: int
    center: tuple[float, float, float] | None = None
    bounds: tuple[float, float, float, float, float, float] | None = None
    bad_cells: int = 0
    min_volume: float | None = None
    max_aspect_ratio: float | None = None

@dataclass(slots=True)
class MeshCheckReport:
    ok: bool
    n_points: int = 0
    n_cells: int = 0
    n_regions: int = 0
    cell_type_counts: dict[str, int] = field(default_factory=dict)
    regions: list[MeshRegionInfo] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    min_cell_volume: float | None = None
    max_aspect_ratio: float | None = None
    bad_cell_ids: list[int] = field(default_factory=list)
    quality_summary: str = ''

    def summary_text(self) -> str:
        types = ', '.join(f'{k}:{v}' for k, v in self.cell_type_counts.items()) or '-'
        q = self.quality_summary or '-'
        return f'nodes={self.n_points} | cells={self.n_cells} | regions={self.n_regions} | cell_types={types} | quality={q}'


def _edge_lengths(points: np.ndarray, pairs: tuple[tuple[int, int], ...]) -> list[float]:
    vals: list[float] = []
    for a, b in pairs:
        vals.append(float(np.linalg.norm(points[a] - points[b])))
    return vals


def _tet_volume(points: np.ndarray) -> float:
    a, b, c, d = points[:4]
    return float(abs(np.linalg.det(np.vstack([b - a, c - a, d - a]))) / 6.0)


def _hex_center_jacobian(points: np.ndarray) -> float:
    dxi = np.array([-1,1,1,-1,-1,1,1,-1], dtype=float) / 8.0
    deta = np.array([-1,-1,1,1,-1,-1,1,1], dtype=float) / 8.0
    dzeta = np.array([-1,-1,-1,-1,1,1,1,1], dtype=float) / 8.0
    J = np.zeros((3,3), dtype=float)
    for i in range(8):
        x, y, z = points[i]
        J[0,0] += dxi[i]*x; J[0,1] += deta[i]*x; J[0,2] += dzeta[i]*x
        J[1,0] += dxi[i]*y; J[1,1] += deta[i]*y; J[1,2] += dzeta[i]*y
        J[2,0] += dxi[i]*z; J[2,1] += deta[i]*z; J[2,2] += dzeta[i]*z
    return float(np.linalg.det(J))


def _cell_quality(grid, cell_id: int) -> tuple[float | None, float | None, bool]:
    try:
        ctype = int(grid.celltypes[cell_id])
        ids = np.asarray(grid.get_cell(cell_id).point_ids, dtype=int)
        pts = np.asarray(grid.points[ids], dtype=float)
    except Exception:
        return None, None, True
    try:
        if ctype == 12 and len(pts) >= 8:
            lengths = _edge_lengths(pts[:8], HEX_EDGES)
            aspect = max(lengths) / max(min(lengths), 1.0e-12)
            mins = pts.min(axis=0); maxs = pts.max(axis=0)
            vol = float(max(np.prod(np.maximum(maxs - mins, 0.0)), 0.0))
            jac = _hex_center_jacobian(pts[:8])
            bad = (jac <= 0.0) or (aspect > 15.0) or (vol <= 1.0e-12) or (not math.isfinite(aspect))
            return vol, aspect, bad
        if ctype == 10 and len(pts) >= 4:
            lengths = _edge_lengths(pts[:4], TET_EDGES)
            aspect = max(lengths) / max(min(lengths), 1.0e-12)
            vol = _tet_volume(pts[:4])
            bad = (vol <= 1.0e-14) or (aspect > 15.0) or (not math.isfinite(aspect))
            return vol, aspect, bad
        mins = pts.min(axis=0); maxs = pts.max(axis=0)
        ext = np.maximum(maxs - mins, 1.0e-12)
        aspect = float(ext.max() / ext.min())
        vol = float(np.prod(ext))
        bad = aspect > 20.0 or vol <= 1.0e-14
        return vol, aspect, bad
    except Exception:
        return None, None, True


def analyze_mesh(model: SimulationModel | None) -> MeshCheckReport:
    if model is None:
        return MeshCheckReport(ok=False, messages=['No model loaded.'])
    try:
        grid = model.to_unstructured_grid()
    except Exception as exc:
        return MeshCheckReport(ok=False, messages=[f'Unable to build a solver grid: {exc}'])

    n_points = int(getattr(grid, 'n_points', 0) or 0)
    n_cells = int(getattr(grid, 'n_cells', 0) or 0)
    messages: list[str] = []
    warnings: list[str] = []
    celltypes = [int(v) for v in getattr(grid, 'celltypes', [])]
    counts = Counter(celltypes)
    named_counts = {VTK_CELL_NAMES.get(k, str(k)): v for k, v in sorted(counts.items())}

    if n_points <= 0:
        messages.append('Mesh has no points.')
    if n_cells <= 0:
        messages.append('Mesh has no cells/elements.')
    if counts and counts.keys() <= SURFACE_TYPES:
        messages.append('Current mesh is still surface-only; generate a volume mesh before solving.')
    if counts and not any(k in VOLUME_TYPES for k in counts):
        warnings.append('No recognised 3D volume cells were found in the current mesh.')

    per_region_bad: dict[str, int] = defaultdict(int)
    per_region_minv: dict[str, float] = {}
    per_region_maxar: dict[str, float] = {}
    bad_cell_ids: list[int] = []
    global_minv: float | None = None
    global_maxar: float | None = None
    region_names_by_cell: list[str | None] = [None] * n_cells
    for region in model.region_tags:
        for cid in map(int, region.cell_ids):
            if 0 <= cid < n_cells:
                region_names_by_cell[cid] = region.name
    for cid in range(n_cells):
        vol, ar, bad = _cell_quality(grid, cid)
        if vol is not None:
            global_minv = vol if global_minv is None else min(global_minv, vol)
        if ar is not None:
            global_maxar = ar if global_maxar is None else max(global_maxar, ar)
        region_name = region_names_by_cell[cid]
        if region_name:
            if vol is not None:
                per_region_minv[region_name] = vol if region_name not in per_region_minv else min(per_region_minv[region_name], vol)
            if ar is not None:
                per_region_maxar[region_name] = ar if region_name not in per_region_maxar else max(per_region_maxar[region_name], ar)
        if bad:
            bad_cell_ids.append(cid)
            if region_name:
                per_region_bad[region_name] += 1

    if bad_cell_ids:
        warnings.append(f'Quality check flagged {len(bad_cell_ids)} suspect cells (extreme aspect ratio or invalid volume/Jacobian).')

    regions: list[MeshRegionInfo] = []
    for region in model.region_tags:
        info = MeshRegionInfo(region_name=region.name, cells=len(region.cell_ids))
        try:
            sub = grid.extract_cells(region.cell_ids)
            if int(getattr(sub, 'n_cells', 0) or 0) > 0:
                b = tuple(float(x) for x in sub.bounds)
                info.bounds = b
                info.center = ((b[0] + b[1]) / 2.0, (b[2] + b[3]) / 2.0, (b[4] + b[5]) / 2.0)
                info.bad_cells = int(per_region_bad.get(region.name, 0))
                info.min_volume = per_region_minv.get(region.name)
                info.max_aspect_ratio = per_region_maxar.get(region.name)
            else:
                warnings.append(f'Region "{region.name}" is empty in the current mesh.')
        except Exception:
            warnings.append(f'Unable to extract region "{region.name}" from the current mesh.')
        regions.append(info)

    q = []
    if global_minv is not None:
        q.append(f'min_vol={global_minv:.3e}')
    if global_maxar is not None:
        q.append(f'max_ar={global_maxar:.2f}')
    if bad_cell_ids:
        q.append(f'bad={len(bad_cell_ids)}')
    quality_summary = ', '.join(q) if q else 'n/a'

    return MeshCheckReport(
        ok=not messages,
        n_points=n_points,
        n_cells=n_cells,
        n_regions=len(model.region_tags),
        cell_type_counts=named_counts,
        regions=regions,
        messages=messages,
        warnings=warnings,
        min_cell_volume=global_minv,
        max_aspect_ratio=global_maxar,
        bad_cell_ids=bad_cell_ids,
        quality_summary=quality_summary,
    )
