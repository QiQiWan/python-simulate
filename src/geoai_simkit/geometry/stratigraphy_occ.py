from __future__ import annotations

from typing import Any


def _safe_name(value: Any, fallback: str = 'layer') -> str:
    text = ''.join(ch if ch.isalnum() or ch in {'_', '-', ':'} else '_' for ch in str(value or '').strip())
    return text or fallback


def _surface_lookup(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get('name') or ''): dict(row) for row in list(plan.get('surfaces', []) or []) if isinstance(row, dict) and str(row.get('name') or '')}


def _boundary_edges(triangles: list[tuple[int, int, int]]) -> list[tuple[int, int]]:
    counts: dict[tuple[int, int], int] = {}
    oriented: dict[tuple[int, int], tuple[int, int]] = {}
    for a, b, c in triangles:
        for edge in ((a, b), (b, c), (c, a)):
            key = tuple(sorted(edge))
            counts[key] = counts.get(key, 0) + 1
            oriented.setdefault(key, edge)
    return [oriented[key] for key, count in counts.items() if count == 1]


def _add_point_cache(gmsh: Any, cache: dict[tuple[float, float, float], int], point: list[float] | tuple[float, float, float], h: float) -> int:
    key = (round(float(point[0]), 10), round(float(point[1]), 10), round(float(point[2]), 10))
    if key not in cache:
        cache[key] = int(gmsh.model.occ.addPoint(key[0], key[1], key[2], h))
    return cache[key]


def _add_line_cache(gmsh: Any, cache: dict[tuple[int, int], int], a: int, b: int) -> int:
    key = (int(a), int(b))
    if key not in cache:
        cache[key] = int(gmsh.model.occ.addLine(int(a), int(b)))
    return cache[key]


def _add_tri_surface(gmsh: Any, line_cache: dict[tuple[int, int], int], pts: tuple[int, int, int]) -> int:
    l1 = _add_line_cache(gmsh, line_cache, pts[0], pts[1])
    l2 = _add_line_cache(gmsh, line_cache, pts[1], pts[2])
    l3 = _add_line_cache(gmsh, line_cache, pts[2], pts[0])
    loop = gmsh.model.occ.addCurveLoop([l1, l2, l3])
    return int(gmsh.model.occ.addPlaneSurface([loop]))


def _add_quad_surface(gmsh: Any, line_cache: dict[tuple[int, int], int], pts: tuple[int, int, int, int]) -> int:
    lines = [
        _add_line_cache(gmsh, line_cache, pts[0], pts[1]),
        _add_line_cache(gmsh, line_cache, pts[1], pts[2]),
        _add_line_cache(gmsh, line_cache, pts[2], pts[3]),
        _add_line_cache(gmsh, line_cache, pts[3], pts[0]),
    ]
    loop = gmsh.model.occ.addCurveLoop(lines)
    return int(gmsh.model.occ.addPlaneSurface([loop]))


def add_stratigraphy_layer_volumes(gmsh: Any, stratigraphy_plan: dict[str, Any] | None, *, characteristic_length: float = 1.0) -> list[dict[str, Any]]:
    """Create OCC volumes between interpolated stratigraphic surface pairs.

    This is an optional executable path for hosts with gmsh/OCC. The source
    entity remains the stratigraphy/BRep layer; users still edit boreholes or
    surfaces and remesh, never mesh cells directly.
    """
    plan = dict(stratigraphy_plan or {})
    if not plan:
        return []
    surfaces = _surface_lookup(plan)
    rows: list[dict[str, Any]] = []
    for idx, layer in enumerate([dict(row) for row in list(plan.get('layer_solids', []) or []) if isinstance(row, dict)], start=1):
        top_name = str(layer.get('top_surface') or '')
        bottom_name = str(layer.get('bottom_surface') or '')
        top = surfaces.get(top_name)
        if top is None:
            continue
        top_grid = [list(map(float, p[:3])) for p in list(top.get('interpolated_grid', []) or []) if len(p) >= 3]
        triangles = [tuple(int(v) for v in tri[:3]) for tri in list(top.get('triangles', []) or []) if len(tri) >= 3]
        if not top_grid or not triangles:
            continue
        bottom = surfaces.get(bottom_name)
        if bottom is not None and list(bottom.get('interpolated_grid', []) or []):
            bottom_grid = [list(map(float, p[:3])) for p in list(bottom.get('interpolated_grid', []) or []) if len(p) >= 3]
        else:
            bounds = list(layer.get('bounds', [0, 0, 0, 0, -10, 0]) or [0, 0, 0, 0, -10, 0])
            z_base = float(bounds[4] if len(bounds) >= 6 else min(p[2] for p in top_grid) - 5.0)
            bottom_grid = [[p[0], p[1], z_base] for p in top_grid]
        if len(bottom_grid) != len(top_grid):
            continue
        point_cache: dict[tuple[float, float, float], int] = {}
        line_cache: dict[tuple[int, int], int] = {}
        top_pts = [_add_point_cache(gmsh, point_cache, p, float(characteristic_length)) for p in top_grid]
        bottom_pts = [_add_point_cache(gmsh, point_cache, p, float(characteristic_length)) for p in bottom_grid]
        shell_surfaces: list[int] = []
        for tri in triangles:
            if max(tri) >= len(top_pts) or min(tri) < 0:
                continue
            shell_surfaces.append(_add_tri_surface(gmsh, line_cache, (top_pts[tri[0]], top_pts[tri[1]], top_pts[tri[2]])))
            shell_surfaces.append(_add_tri_surface(gmsh, line_cache, (bottom_pts[tri[2]], bottom_pts[tri[1]], bottom_pts[tri[0]])))
        for a, b in _boundary_edges(triangles):
            if max(a, b) >= len(top_pts):
                continue
            shell_surfaces.append(_add_quad_surface(gmsh, line_cache, (top_pts[a], top_pts[b], bottom_pts[b], bottom_pts[a])))
        if len(shell_surfaces) < 4:
            continue
        try:
            loop = gmsh.model.occ.addSurfaceLoop(shell_surfaces)
            volume_tag = int(gmsh.model.occ.addVolume([loop]))
        except Exception:
            continue
        rows.append({
            'name': str(layer.get('name') or f'stratigraphy_layer_{idx:02d}'),
            'occ_volume_tag': volume_tag,
            'top_surface': top_name,
            'bottom_surface': bottom_name,
            'surface_patch_count': len(shell_surfaces),
            'contract': 'occ_lofted_stratigraphy_layer_volume_v1',
            'metadata': {'source': 'StratigraphyOCCLayerBuilder', 'edit_policy': 'edit_boreholes_or_surfaces_then_remesh'},
        })
    return rows


__all__ = ['add_stratigraphy_layer_volumes']


def build_stratigraphy_occ_boolean_plan(stratigraphy_plan: dict[str, Any] | None, *, target_domain: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a stable OCC boolean/fragment plan for stratigraphic layer volumes.

    The executable gmsh path can use this plan to create layer shells, fragment
    them with the soil domain and register physical volumes/surfaces. The plan is
    deterministic and also works as a degraded contract when OCC is unavailable.
    """
    plan = dict(stratigraphy_plan or {})
    layers = [dict(row) for row in list(plan.get('layer_solids', []) or []) if isinstance(row, dict)]
    surfaces = _surface_lookup(plan)
    operations: list[dict[str, Any]] = []
    for idx, layer in enumerate(layers, start=1):
        top = str(layer.get('top_surface') or '')
        bottom = str(layer.get('bottom_surface') or '')
        role = str(layer.get('role') or 'soil_layer')
        top_triangles = len(list(dict(surfaces.get(top, {}) or {}).get('triangles', []) or []))
        bottom_triangles = len(list(dict(surfaces.get(bottom, {}) or {}).get('triangles', []) or [])) if bottom else 0
        operations.append({
            'name': str(layer.get('name') or f'stratigraphy_layer_{idx:02d}'),
            'operation': 'loft_shell_then_fragment_domain',
            'top_surface': top,
            'bottom_surface': bottom,
            'surface_pair_valid': bool(top and top in surfaces and (not bottom or bottom in surfaces)),
            'top_triangle_count': top_triangles,
            'bottom_triangle_count': bottom_triangles,
            'target_role': role,
            'physical_volume_name': f"region::{str(layer.get('name') or f'stratigraphy_layer_{idx:02d}')}",
            'physical_surface_prefix': f"face_set::{str(layer.get('name') or f'stratigraphy_layer_{idx:02d}')}",
            'edit_policy': 'edit_boreholes_or_stratigraphy_surfaces_then_remesh',
        })
    return {
        'contract': 'stratigraphy_occ_boolean_fragment_plan_v2',
        'source_contract': plan.get('contract', ''),
        'target_domain': dict(target_domain or {}),
        'operations': operations,
        'summary': {
            'operation_count': len(operations),
            'valid_operation_count': sum(1 for op in operations if op.get('surface_pair_valid')),
            'requires_occ_backend': True,
            'fallback_contract_available': True,
        },
    }


def apply_stratigraphy_occ_boolean_fragment(gmsh: Any, stratigraphy_plan: dict[str, Any] | None, *, target_volume_dimtags: list[tuple[int, int]] | None = None, characteristic_length: float = 1.0) -> dict[str, Any]:
    """Executable OCC layer-volume creation + optional domain fragment.

    Returns volume rows even when the final fragment step fails, so the GUI can
    still show which layer entity caused the issue. This keeps the modeler stable
    for complex geology instead of failing silently.
    """
    created = add_stratigraphy_layer_volumes(gmsh, stratigraphy_plan, characteristic_length=characteristic_length)
    layer_dimtags = [(3, int(row.get('occ_volume_tag'))) for row in created if row.get('occ_volume_tag') not in {None, ''}]
    fragment_rows: list[dict[str, Any]] = []
    fragment_ok = False
    if layer_dimtags:
        try:
            gmsh.model.occ.synchronize()
            if target_volume_dimtags:
                out, mapping = gmsh.model.occ.fragment(list(target_volume_dimtags), layer_dimtags)
            else:
                out, mapping = gmsh.model.occ.fragment(layer_dimtags, [])
            gmsh.model.occ.synchronize()
            fragment_rows = [{'dim': int(dim), 'tag': int(tag)} for dim, tag in list(out or [])]
            fragment_ok = True
        except Exception as exc:  # pragma: no cover - depends on host OCC robustness
            fragment_rows = [{'error': str(exc), 'stage': 'occ.fragment'}]
    return {
        'contract': 'stratigraphy_occ_boolean_fragment_result_v2',
        'created_layer_volumes': created,
        'fragmented_dimtags': fragment_rows,
        'summary': {
            'created_layer_volume_count': len(created),
            'fragment_output_count': len(fragment_rows),
            'fragment_ok': bool(fragment_ok),
            'edit_policy': 'edit_boreholes_or_surfaces_then_remesh',
        },
    }

# Extend explicit exports for v0.8.16 while keeping older imports working.
try:
    __all__ = list(__all__) + ['build_stratigraphy_occ_boolean_plan', 'apply_stratigraphy_occ_boolean_fragment']
except NameError:  # pragma: no cover
    __all__ = ['add_stratigraphy_layer_volumes', 'build_stratigraphy_occ_boolean_plan', 'apply_stratigraphy_occ_boolean_fragment']


def build_stratigraphy_realization_audit(stratigraphy_plan: dict[str, Any] | None) -> dict[str, Any]:
    """Audit whether interpolated layer surfaces are ready for OCC volume realization."""
    plan = dict(stratigraphy_plan or {})
    surfaces = _surface_lookup(plan)
    issues: list[dict[str, Any]] = []
    layer_rows: list[dict[str, Any]] = []
    for idx, layer in enumerate([dict(row) for row in list(plan.get('layer_solids', []) or []) if isinstance(row, dict)], start=1):
        name = str(layer.get('name') or f'layer_{idx:02d}')
        top_name = str(layer.get('top_surface') or '')
        bottom_name = str(layer.get('bottom_surface') or '')
        top = surfaces.get(top_name, {})
        bottom = surfaces.get(bottom_name, {}) if bottom_name else {}
        top_n = len(list(top.get('interpolated_grid', []) or []))
        bottom_n = len(list(bottom.get('interpolated_grid', []) or [])) if bottom else top_n
        tri_n = len(list(top.get('triangles', []) or []))
        ready = bool(top_name in surfaces and tri_n > 0 and top_n > 0 and (not bottom_name or bottom_name in surfaces) and (not bottom or bottom_n == top_n))
        if not ready:
            issues.append({'layer': name, 'severity': 'warning', 'message': 'Layer surface pair is not ready for OCC loft/fragment.', 'top_surface': top_name, 'bottom_surface': bottom_name})
        layer_rows.append({'name': name, 'top_surface': top_name, 'bottom_surface': bottom_name, 'top_point_count': top_n, 'bottom_point_count': bottom_n, 'triangle_count': tri_n, 'ready_for_occ_volume': ready})
    return {'contract': 'stratigraphy_occ_realization_audit_v1', 'layers': layer_rows, 'issues': issues, 'summary': {'layer_count': len(layer_rows), 'ready_layer_count': sum(1 for row in layer_rows if row.get('ready_for_occ_volume')), 'issue_count': len(issues), 'edit_policy': 'edit_boreholes_or_surfaces_then_remesh'}}


def build_stratigraphy_fallback_layer_blocks(stratigraphy_plan: dict[str, Any] | None) -> dict[str, Any]:
    """Build deterministic fallback source-entity blocks for layers when OCC loft fails."""
    plan = dict(stratigraphy_plan or {})
    rows: list[dict[str, Any]] = []
    for idx, layer in enumerate([dict(row) for row in list(plan.get('layer_solids', []) or []) if isinstance(row, dict)], start=1):
        bounds = list(layer.get('bounds') or [])
        if len(bounds) < 6:
            continue
        name = str(layer.get('name') or f'stratigraphy_layer_{idx:02d}')
        rows.append({'name': name, 'region_name': name, 'bounds': [float(v) for v in bounds[:6]], 'role': 'soil_layer', 'material_name': str(layer.get('material_name') or name), 'mesh_size': layer.get('mesh_size', None), 'metadata': {'source': 'stratigraphy_fallback_layer_block', 'top_surface': layer.get('top_surface', ''), 'bottom_surface': layer.get('bottom_surface', ''), 'edit_policy': 'edit_boreholes_or_surfaces_then_remesh'}})
    return {'contract': 'stratigraphy_fallback_layer_blocks_v1', 'blocks': rows, 'summary': {'block_count': len(rows), 'used_when_occ_unavailable_or_unstable': True}}


try:
    __all__ = list(dict.fromkeys(list(__all__) + ['build_stratigraphy_realization_audit', 'build_stratigraphy_fallback_layer_blocks']))
except NameError:  # pragma: no cover
    __all__ = ['add_stratigraphy_layer_volumes', 'build_stratigraphy_occ_boolean_plan', 'apply_stratigraphy_occ_boolean_fragment', 'build_stratigraphy_realization_audit', 'build_stratigraphy_fallback_layer_blocks']
