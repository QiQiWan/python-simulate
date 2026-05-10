from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import math
from typing import Any, Iterable, Sequence

from geoai_simkit.geometry.editable_blocks import EditableBlock, normalize_editable_blocks
from geoai_simkit.geometry.partition_engine import plane_aabb_intersection_polygon
from geoai_simkit.geometry.topology_kernel import Point3, polygon_area_3d


def _as_point3(value: Sequence[Any] | None, default: Point3 = (0.0, 0.0, 0.0)) -> Point3:
    if value is None:
        return default
    vals = list(value)[:3]
    if len(vals) != 3:
        raise ValueError('A 3D point/normal must contain exactly three values.')
    return (float(vals[0]), float(vals[1]), float(vals[2]))


def _norm(v: Point3) -> float:
    return float((v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5)


def _normalize(v: Point3) -> Point3:
    n = _norm(v)
    if n <= 1.0e-14:
        raise ValueError('normal cannot be zero.')
    return (v[0] / n, v[1] / n, v[2] / n)


def _dot(a: Point3, b: Point3) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def _sub(a: Point3, b: Point3) -> Point3:
    return (float(a[0] - b[0]), float(a[1] - b[1]), float(a[2] - b[2]))


def _bbox_center(bounds: Sequence[float]) -> Point3:
    vals = [float(v) for v in list(bounds)[:6]]
    return (0.5 * (vals[0] + vals[1]), 0.5 * (vals[2] + vals[3]), 0.5 * (vals[4] + vals[5]))


def _bbox_volume(bounds: Sequence[float]) -> float:
    vals = [float(v) for v in list(bounds)[:6]]
    return max(0.0, vals[1] - vals[0]) * max(0.0, vals[3] - vals[2]) * max(0.0, vals[5] - vals[4])


def _point_in_bbox(point: Sequence[float], bounds: Sequence[float], *, tol: float = 1.0e-7) -> bool:
    x, y, z = [float(v) for v in list(point)[:3]]
    xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in list(bounds)[:6]]
    return (xmin - tol <= x <= xmax + tol) and (ymin - tol <= y <= ymax + tol) and (zmin - tol <= z <= zmax + tol)


def _distance(a: Point3, b: Point3) -> float:
    return _norm(_sub(a, b))


def _safe_slug(value: str, *, fallback: str = 'occ') -> str:
    text = ''.join(ch if ch.isalnum() or ch in {'_', '-', ':', '.'} else '_' for ch in str(value or '').strip())
    text = '_'.join(part for part in text.split('_') if part)
    return text or fallback


def gmsh_occ_available() -> bool:
    """Return True when the gmsh Python module is discoverable.

    This intentionally uses importlib metadata instead of importing gmsh, because
    importing the wheel can block or fail on machines missing OpenGL/OCC runtime
    libraries. Actual execution still imports gmsh inside require_backend().
    """
    try:
        import importlib.util
        return importlib.util.find_spec('gmsh') is not None
    except Exception:
        return False


@dataclass(frozen=True, slots=True)
class OCCSplitTool:
    name: str
    target_block: str
    kind: str
    point: Point3 = (0.0, 0.0, 0.0)
    normal: Point3 = (0.0, 0.0, 1.0)
    polygon: tuple[Point3, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'target_block': self.target_block,
            'kind': self.kind,
            'point': [float(v) for v in self.point],
            'normal': [float(v) for v in self.normal],
            'polygon': [[float(v) for v in p] for p in self.polygon],
            'area': float(polygon_area_3d(self.polygon)),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class OCCPartitionPlan:
    backend_available: bool
    requested_tool_count: int
    executable_tool_count: int
    tools: tuple[OCCSplitTool, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'contract': 'gmsh_occ_partition_plan_v2',
            'backend': 'gmsh.model.occ',
            'backend_available': bool(self.backend_available),
            'requested_tool_count': int(self.requested_tool_count),
            'executable_tool_count': int(self.executable_tool_count),
            'tools': [tool.to_dict() for tool in self.tools],
            'issues': [dict(issue) for issue in self.issues],
            'summary': {
                'backend_available': bool(self.backend_available),
                'requested_tool_count': int(self.requested_tool_count),
                'executable_tool_count': int(self.executable_tool_count),
                'issue_count': len(self.issues),
            },
            'metadata': dict(self.metadata),
        }


def _issue(issue_id: str, severity: str, message: str, *, target: str = 'occ_partition', action: str = '', details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {'id': issue_id, 'severity': severity, 'message': message, 'target': target, 'action': action, 'details': dict(details or {})}


def build_gmsh_occ_partition_plan(blocks: Iterable[dict[str, Any]], split_definitions: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a Gmsh-OCC handoff plan for exact solid fragmentation.

    The plan is deterministic even when the optional gmsh runtime is missing.
    Deployments with gmsh can execute the same tool list to create fragmented
    volumes, physical volumes, physical surfaces, cell sets and face sets.
    """
    block_rows = normalize_editable_blocks(blocks)
    block_by_name = {block.name: block for block in block_rows}
    split_rows = [dict(row) for row in list(split_definitions or []) if isinstance(row, dict)]
    tools: list[OCCSplitTool] = []
    issues: list[dict[str, Any]] = []
    requested = 0
    for index, row in enumerate(split_rows, start=1):
        kind = str(row.get('kind') or '').strip().lower()
        if kind not in {'plane', 'oblique_plane', 'polyline', 'polyline_extrusion', 'surface', 'axis', 'axis_plane'} and row.get('normal') is None and row.get('polyline') is None and row.get('axis') is None:
            continue
        requested += 1
        target = str(row.get('target_block') or row.get('region_name') or row.get('target') or '').strip()
        name = str(row.get('name') or f'{target}__occ_split_{index:02d}')
        block = block_by_name.get(target)
        if block is None:
            issues.append(_issue(f'occ.{name}.target_missing', 'warning', f'OCC split target {target!r} is not present in editable blocks.', target=target, action='Refresh split definitions or execute the split before meshing.'))
            continue
        if row.get('polyline') is not None or kind in {'polyline', 'polyline_extrusion'}:
            raw_points = list(row.get('polyline') or [])
            pts: list[Point3] = []
            for raw in raw_points:
                vals = list(raw)
                if len(vals) < 2:
                    continue
                z = float(vals[2]) if len(vals) >= 3 else float(block.bounds[4])
                pts.append((float(vals[0]), float(vals[1]), z))
            if len(pts) < 2:
                issues.append(_issue(f'occ.{name}.polyline_too_short', 'warning', 'Polyline extrusion split requires at least two points.', target=target, action='Draw at least two polyline points.'))
                continue
            z0 = float(row.get('z_min', block.bounds[4]) if row.get('z_min') not in {None, ''} else block.bounds[4])
            z1 = float(row.get('z_max', block.bounds[5]) if row.get('z_max') not in {None, ''} else block.bounds[5])
            tools.append(OCCSplitTool(name=name, target_block=target, kind='polyline_extrusion', point=(pts[0][0], pts[0][1], z0), normal=(0.0, 0.0, 1.0), metadata={'polyline': [list(p) for p in pts], 'z_min': z0, 'z_max': z1, 'occ_operation': 'fragment_volume_by_extruded_segment_faces'}))
        else:
            if row.get('axis') is not None and row.get('normal') is None:
                axis = str(row.get('axis') or 'z').strip().lower()
                coord = float(row.get('coordinate') if row.get('coordinate') not in {None, ''} else {'x': block.center[0], 'y': block.center[1], 'z': block.center[2]}.get(axis, block.center[2]))
                point = {'x': (coord, 0.0, 0.0), 'y': (0.0, coord, 0.0), 'z': (0.0, 0.0, coord)}.get(axis, (0.0, 0.0, coord))
                normal = {'x': (1.0, 0.0, 0.0), 'y': (0.0, 1.0, 0.0), 'z': (0.0, 0.0, 1.0)}.get(axis, (0.0, 0.0, 1.0))
            else:
                point = _as_point3(row.get('point') or row.get('origin') or block.center)
                normal = _normalize(_as_point3(row.get('normal'), (0.0, 0.0, 1.0)))
            polygon = plane_aabb_intersection_polygon(block.bounds, point, normal)
            if len(polygon) < 3:
                issues.append(_issue(f'occ.{name}.plane_no_intersection', 'warning', 'Plane split does not intersect the target block.', target=target, action='Move the plane into the target block.'))
                continue
            tools.append(OCCSplitTool(name=name, target_block=target, kind='oblique_plane', point=point, normal=normal, polygon=polygon, metadata={'occ_operation': 'fragment_volume_by_plane_surface'}))
    if not gmsh_occ_available():
        issues.append(_issue('occ.backend.unavailable', 'info', 'gmsh Python OCC backend is not available in this environment; partition plan remains executable on machines with gmsh/libGLU installed.', action='Install gmsh Python package and system OpenGL/OCC runtime to enable exact solid partition.'))
    return OCCPartitionPlan(
        backend_available=gmsh_occ_available(),
        requested_tool_count=requested,
        executable_tool_count=len(tools),
        tools=tuple(tools),
        issues=tuple(issues),
        metadata={
            'exact_solid_partition': True,
            'fallback_contract': 'protected_surface_rows',
            'mesh_handoff_contract': 'occ_fragmented_volume_mesh_v1',
            'exports': ['physical_volumes', 'physical_surfaces', 'region_cell_sets', 'topology_face_sets'],
        },
    ).to_dict()


class GmshOCCPartitioner:
    """Executor for OCC fragmentation and Gmsh volume meshing.

    It creates OCC volumes from editable blocks, fragments them by plane or
    polyline-extruded faces, assigns physical volumes/surfaces, generates a 3D
    mesh, and returns metadata needed to reconstruct FE region/cell/face sets.
    """

    def __init__(self, *, characteristic_length: float = 1.0, algorithm3d: int = 1, optimize: bool = True) -> None:
        self.characteristic_length = float(characteristic_length)
        self.algorithm3d = int(algorithm3d)
        self.optimize = bool(optimize)

    def require_backend(self):
        try:
            import gmsh
            return gmsh
        except Exception as exc:  # pragma: no cover - depends on optional host deps
            raise RuntimeError('Gmsh OCC backend is unavailable. Install gmsh and required OpenGL/OCC runtime libraries.') from exc

    def build_occ_model(self, blocks: Iterable[dict[str, Any]], split_definitions: Iterable[dict[str, Any]] | None = None, *, model_name: str = 'geoai_occ_partition') -> dict[str, Any]:
        """Build and fragment the OCC model without generating a mesh."""
        gmsh = self.require_backend()
        block_rows = normalize_editable_blocks(blocks)
        plan = build_gmsh_occ_partition_plan([b.to_dict() for b in block_rows], split_definitions)
        gmsh.initialize()
        try:  # pragma: no cover - optional gmsh path
            gmsh.model.add(model_name)
            self._configure_gmsh(gmsh)
            volume_tags = self._add_block_volumes(gmsh, block_rows)
            tool_dimtags = self._add_split_tools(gmsh, plan)
            if tool_dimtags:
                gmsh.model.occ.fragment([(3, tag) for tag in volume_tags.values()], tool_dimtags, removeObject=True, removeTool=False)
            gmsh.model.occ.synchronize()
            return {'model_name': model_name, 'volume_count': len(gmsh.model.getEntities(3)), 'surface_count': len(gmsh.model.getEntities(2)), 'tool_count': len(tool_dimtags), 'plan': plan}
        finally:
            try:
                gmsh.finalize()
            except Exception:
                pass

    def mesh_fragmented_model(
        self,
        blocks: Iterable[dict[str, Any]],
        split_definitions: Iterable[dict[str, Any]] | None,
        msh_path: str | Path,
        *,
        protected_surfaces: Iterable[dict[str, Any]] | None = None,
        mesh_size_controls: Iterable[dict[str, Any]] | None = None,
        stratigraphy_plan: dict[str, Any] | None = None,
        model_name: str = 'geoai_occ_fragmented_mesh',
    ) -> dict[str, Any]:
        """Execute OCC fragmentation, physical tagging and volume mesh export."""
        gmsh = self.require_backend()
        block_rows = normalize_editable_blocks(blocks)
        if not block_rows:
            raise RuntimeError('OCC fragmented meshing requires at least one editable block.')
        plan = build_gmsh_occ_partition_plan([b.to_dict() for b in block_rows], split_definitions)
        strat_plan = dict(stratigraphy_plan or {})
        has_stratigraphy_layers = bool(strat_plan.get('occ_layer_volume_enabled') and list(strat_plan.get('layer_solids', []) or []))
        if int(plan.get('executable_tool_count', 0) or 0) <= 0 and not has_stratigraphy_layers:
            raise RuntimeError('OCC fragmented meshing requires at least one executable split tool or stratigraphy OCC layer volume contract.')
        protected_rows = [dict(row) for row in list(protected_surfaces or []) if isinstance(row, dict)]
        out_path = Path(msh_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        gmsh.initialize()
        try:  # pragma: no cover - depends on gmsh runtime
            gmsh.model.add(model_name)
            self._configure_gmsh(gmsh)
            layer_names = {str(row.get('name') or '') for row in list(strat_plan.get('layer_solids', []) or []) if isinstance(row, dict)}
            non_layer_blocks = [block for block in block_rows if block.name not in layer_names]
            source_volume_tags = self._add_block_volumes(gmsh, non_layer_blocks or block_rows)
            stratigraphy_volume_rows: list[dict[str, Any]] = []
            if has_stratigraphy_layers:
                try:
                    from geoai_simkit.geometry.stratigraphy_occ import add_stratigraphy_layer_volumes
                    stratigraphy_volume_rows = add_stratigraphy_layer_volumes(gmsh, strat_plan, characteristic_length=float(self.characteristic_length))
                    for row in stratigraphy_volume_rows:
                        name = str(row.get('name') or f'stratigraphy_layer_{len(source_volume_tags) + 1:02d}')
                        tag = int(row.get('occ_volume_tag'))
                        source_volume_tags[name] = tag
                except Exception as exc:
                    stratigraphy_volume_rows = [{'error': str(exc), 'contract': 'occ_lofted_stratigraphy_layer_volume_v1'}]
            object_dimtags = [(3, tag) for tag in source_volume_tags.values()]
            tool_dimtags = self._add_split_tools(gmsh, plan)
            if tool_dimtags:
                gmsh.model.occ.fragment(object_dimtags, tool_dimtags, removeObject=True, removeTool=False)
            gmsh.model.occ.synchronize()
            volume_rows = self._tag_physical_volumes(gmsh, block_rows)
            face_rows = self._tag_physical_surfaces(gmsh, block_rows, protected_rows, plan)
            mesh_size_field_plan: dict[str, Any] = {}
            mesh_size_field_application: dict[str, Any] = {}
            try:
                from geoai_simkit.geometry.mesh_size_field import MeshSizeFieldBuilder, apply_gmsh_mesh_size_field_plan

                mesh_size_field_plan = MeshSizeFieldBuilder().build_from_physical_surfaces(
                    face_rows,
                    global_size=float(self.characteristic_length),
                    user_controls=mesh_size_controls,
                )
                mesh_size_field_application = apply_gmsh_mesh_size_field_plan(gmsh, mesh_size_field_plan)
            except Exception as exc:  # pragma: no cover - host/gmsh-version dependent
                mesh_size_field_plan = {
                    'contract': 'mesh_size_field_plan_v1',
                    'fields': [],
                    'issues': [{'id': 'mesh_size_field.failed', 'severity': 'warning', 'message': str(exc)}],
                    'summary': {'field_count': 0, 'issue_count': 1},
                }
                mesh_size_field_application = {'applied': False, 'field_count': 0, 'issues': list(mesh_size_field_plan.get('issues', []))}
            gmsh.model.mesh.generate(3)
            if self.optimize:
                try:
                    gmsh.model.mesh.optimize('Netgen')
                except Exception:
                    pass
            gmsh.write(str(out_path))
            logs = []
            try:
                logs = list(gmsh.logger.get()[-12:])
            except Exception:
                logs = []
            return {
                'contract': 'occ_fragmented_volume_mesh_v1',
                'backend': 'gmsh.model.occ',
                'model_name': model_name,
                'msh_path': str(out_path),
                'plan': plan,
                'physical_volume_rows': volume_rows,
                'physical_surface_rows': face_rows,
                'stratigraphy_occ_layer_volumes': stratigraphy_volume_rows,
                'stratigraphy_occ_contract': 'occ_lofted_stratigraphy_layer_volume_v1',
                'mesh_size_field_plan': mesh_size_field_plan,
                'mesh_size_field_application': mesh_size_field_application,
                'region_cell_set_contract': 'region_name_from_gmsh_physical_volume',
                'face_set_contract': 'protected_or_boundary_surface_from_gmsh_physical_surface',
                'summary': {
                    'source_block_count': len(block_rows),
                    'split_tool_count': len(tool_dimtags),
                    'stratigraphy_layer_volume_count': len([row for row in stratigraphy_volume_rows if isinstance(row, dict) and row.get('occ_volume_tag') is not None]),
                    'fragmented_volume_count': len(volume_rows),
                    'physical_surface_count': len(face_rows),
                    'protected_surface_count': sum(1 for row in face_rows if row.get('surface_role') == 'protected_split_face'),
                    'mesh_size_field_count': int(dict(mesh_size_field_plan.get('summary', {}) or {}).get('field_count', 0)),
                    'mesh_size_field_applied': bool(mesh_size_field_application.get('applied', False)),
                },
                'logger_tail': logs,
            }
        finally:
            try:
                gmsh.finalize()
            except Exception:
                pass

    def _configure_gmsh(self, gmsh: Any) -> None:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.option.setNumber('Mesh.CharacteristicLengthMin', float(self.characteristic_length))
        gmsh.option.setNumber('Mesh.CharacteristicLengthMax', float(self.characteristic_length))
        gmsh.option.setNumber('Mesh.Algorithm3D', int(self.algorithm3d))
        # Keep lower-dimensional entities in the .msh file so physical surface
        # groups are recoverable as face sets through meshio field_data.
        gmsh.option.setNumber('Mesh.SaveAll', 0)

    def _add_block_volumes(self, gmsh: Any, blocks: Sequence[EditableBlock]) -> dict[str, int]:
        tags: dict[str, int] = {}
        for block in blocks:
            xmin, xmax, ymin, ymax, zmin, zmax = block.bounds
            tag = gmsh.model.occ.addBox(xmin, ymin, zmin, xmax - xmin, ymax - ymin, zmax - zmin)
            tags[block.name] = int(tag)
        gmsh.model.occ.synchronize()
        return tags

    def _add_split_tools(self, gmsh: Any, plan: dict[str, Any]) -> list[tuple[int, int]]:
        tool_dimtags: list[tuple[int, int]] = []
        for tool in list(plan.get('tools', []) or []):
            kind = str(tool.get('kind') or '')
            if kind == 'oblique_plane':
                polygon = [tuple(float(v) for v in list(p)[:3]) for p in list(tool.get('polygon', []) or [])]
                if len(polygon) < 3:
                    continue
                pts = [gmsh.model.occ.addPoint(*p, self.characteristic_length) for p in polygon]
                lines = [gmsh.model.occ.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
                loop = gmsh.model.occ.addCurveLoop(lines)
                surf = gmsh.model.occ.addPlaneSurface([loop])
                tool_dimtags.append((2, int(surf)))
            elif kind == 'polyline_extrusion':
                meta = dict(tool.get('metadata', {}) or {})
                polyline = [tuple(float(v) for v in list(p)[:3]) for p in list(meta.get('polyline', []) or [])]
                z0 = float(meta.get('z_min', 0.0))
                z1 = float(meta.get('z_max', 0.0))
                for a, b in zip(polyline[:-1], polyline[1:]):
                    p0 = gmsh.model.occ.addPoint(a[0], a[1], z0, self.characteristic_length)
                    p1 = gmsh.model.occ.addPoint(b[0], b[1], z0, self.characteristic_length)
                    p2 = gmsh.model.occ.addPoint(b[0], b[1], z1, self.characteristic_length)
                    p3 = gmsh.model.occ.addPoint(a[0], a[1], z1, self.characteristic_length)
                    lines = [gmsh.model.occ.addLine(p0, p1), gmsh.model.occ.addLine(p1, p2), gmsh.model.occ.addLine(p2, p3), gmsh.model.occ.addLine(p3, p0)]
                    loop = gmsh.model.occ.addCurveLoop(lines)
                    surf = gmsh.model.occ.addPlaneSurface([loop])
                    tool_dimtags.append((2, int(surf)))
        return tool_dimtags

    def _classify_block_for_entity(self, gmsh: Any, dim: int, tag: int, blocks: Sequence[EditableBlock]) -> EditableBlock:
        try:
            center = gmsh.model.occ.getCenterOfMass(dim, tag)
            point = (float(center[0]), float(center[1]), float(center[2]))
        except Exception:
            point = _bbox_center(gmsh.model.getBoundingBox(dim, tag))
        inside = [block for block in blocks if _point_in_bbox(point, block.bounds)]
        if inside:
            return min(inside, key=lambda b: _bbox_volume(b.bounds))
        return min(blocks, key=lambda b: _distance(point, b.center))

    def _tag_physical_volumes(self, gmsh: Any, blocks: Sequence[EditableBlock]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for dim, tag in gmsh.model.getEntities(3):
            if int(dim) != 3:
                continue
            block = self._classify_block_for_entity(gmsh, 3, int(tag), blocks)
            region_name = block.name
            physical = gmsh.model.addPhysicalGroup(3, [int(tag)])
            physical_name = f'region::{_safe_slug(region_name)}::occ_volume::{int(tag)}'
            gmsh.model.setPhysicalName(3, physical, physical_name)
            bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(3, int(tag)))
            rows.append({
                'physical_id': int(physical),
                'physical_name': physical_name,
                'dim': 3,
                'occ_volume_tag': int(tag),
                'region_name': region_name,
                'source_block': block.name,
                'role': block.role,
                'material_name': block.material_name,
                'bounds': [float(v) for v in bbox],
                'center': [float(v) for v in _bbox_center(bbox)],
                'volume_bbox': float(_bbox_volume(bbox)),
            })
        return rows

    def _protected_match(self, gmsh: Any, surface_tag: int, protected_rows: Sequence[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any] | None:
        try:
            center = tuple(float(v) for v in gmsh.model.occ.getCenterOfMass(2, int(surface_tag)))
        except Exception:
            center = _bbox_center(gmsh.model.getBoundingBox(2, int(surface_tag)))
        candidates = list(protected_rows)
        # Also include OCC tools because virtual plane/polyline splits may not
        # appear in protected_surface_rows on older saved cases.
        for tool in list(plan.get('tools', []) or []):
            candidates.append({
                'name': tool.get('name'),
                'target_block': tool.get('target_block'),
                'kind': tool.get('kind'),
                'point': tool.get('point'),
                'normal': tool.get('normal'),
                'polygon': tool.get('polygon'),
                'metadata': dict(tool.get('metadata', {}) or {}),
            })
        best: tuple[float, dict[str, Any]] | None = None
        for row in candidates:
            name = str(row.get('name') or '').strip()
            if not name:
                continue
            kind = str(row.get('kind') or '').strip().lower()
            meta = dict(row.get('metadata', {}) or {})
            if kind == 'polyline_extrusion' or meta.get('panel_polygons') or meta.get('polyline'):
                panels = list(meta.get('panel_polygons', []) or [])
                if not panels and meta.get('polyline'):
                    polyline = [tuple(float(v) for v in list(p)[:3]) for p in list(meta.get('polyline', []) or [])]
                    z0 = float(meta.get('z_min', center[2]))
                    z1 = float(meta.get('z_max', center[2]))
                    panels = [[(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)] for a, b in zip(polyline[:-1], polyline[1:])]
                for panel in panels:
                    pts = [tuple(float(v) for v in list(p)[:3]) for p in list(panel)]
                    if len(pts) < 3:
                        continue
                    # Plane distance plus loose bounding-box check is robust
                    # enough for tagging generated fragment surfaces.
                    p0 = pts[0]
                    v1 = _sub(pts[1], pts[0])
                    v2 = _sub(pts[2], pts[1])
                    normal = _normalize((v1[1] * v2[2] - v1[2] * v2[1], v1[2] * v2[0] - v1[0] * v2[2], v1[0] * v2[1] - v1[1] * v2[0]))
                    dist = abs(_dot(_sub(center, p0), normal))
                    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
                    in_box = min(xs) - 1e-5 <= center[0] <= max(xs) + 1e-5 and min(ys) - 1e-5 <= center[1] <= max(ys) + 1e-5 and min(zs) - 1e-5 <= center[2] <= max(zs) + 1e-5
                    if in_box and (best is None or dist < best[0]):
                        best = (dist, row)
            else:
                point = row.get('point') or row.get('origin')
                normal = row.get('normal')
                if point is None or normal is None:
                    continue
                p0 = _as_point3(point)
                n = _normalize(_as_point3(normal, (0.0, 0.0, 1.0)))
                dist = abs(_dot(_sub(center, p0), n))
                if dist > max(1.0e-5, self.characteristic_length * 1.0e-3):
                    continue
                polygon = [tuple(float(v) for v in list(p)[:3]) for p in list(row.get('polygon', []) or [])]
                if polygon:
                    xs, ys, zs = [p[0] for p in polygon], [p[1] for p in polygon], [p[2] for p in polygon]
                    if not (min(xs) - 1e-5 <= center[0] <= max(xs) + 1e-5 and min(ys) - 1e-5 <= center[1] <= max(ys) + 1e-5 and min(zs) - 1e-5 <= center[2] <= max(zs) + 1e-5):
                        continue
                if best is None or dist < best[0]:
                    best = (dist, row)
        if best is None:
            return None
        return dict(best[1])

    def _tag_physical_surfaces(self, gmsh: Any, blocks: Sequence[EditableBlock], protected_rows: Sequence[dict[str, Any]], plan: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for dim, tag in gmsh.model.getEntities(2):
            if int(dim) != 2:
                continue
            block = self._classify_block_for_entity(gmsh, 2, int(tag), blocks)
            protected = self._protected_match(gmsh, int(tag), protected_rows, plan)
            if protected is not None:
                face_set_name = str(protected.get('name') or f'protected_surface_{tag}')
                role = 'protected_split_face'
                topology_entity_id = f'protected_surface:{face_set_name}'
            else:
                face_set_name = f'{block.name}:boundary:{int(tag)}'
                role = 'boundary_surface'
                topology_entity_id = f'face_set:{face_set_name}'
            physical = gmsh.model.addPhysicalGroup(2, [int(tag)])
            physical_name = f'face_set::{_safe_slug(face_set_name)}::surface::{int(tag)}'
            gmsh.model.setPhysicalName(2, physical, physical_name)
            bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(2, int(tag)))
            rows.append({
                'physical_id': int(physical),
                'physical_name': physical_name,
                'dim': 2,
                'occ_surface_tag': int(tag),
                'face_set_name': face_set_name,
                'surface_role': role,
                'source_block': block.name,
                'region_name': block.name,
                'topology_entity_id': topology_entity_id,
                'protected_surface': None if protected is None else str(protected.get('name') or ''),
                'bounds': [float(v) for v in bbox],
                'center': [float(v) for v in _bbox_center(bbox)],
            })
        return rows


__all__ = [
    'GmshOCCPartitioner',
    'OCCPartitionPlan',
    'OCCSplitTool',
    'build_gmsh_occ_partition_plan',
    'gmsh_occ_available',
]
