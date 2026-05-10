from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


def _safe_float(value: Any, default: float) -> float:
    try:
        if value in {None, ''}:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _role_size_factor(role: str, surface_role: str = '') -> float:
    text = f'{role} {surface_role}'.lower()
    if any(k in text for k in ('wall_foot', 'wall-foot', 'toe', 'corner')):
        return 0.35
    if any(k in text for k in ('contact', 'interface', 'protected', 'split')):
        return 0.45
    if any(k in text for k in ('wall', 'retaining', 'support')):
        return 0.55
    if any(k in text for k in ('monitoring', 'borehole', 'instrument')):
        return 0.65
    if any(k in text for k in ('layer', 'stratigraphy')):
        return 0.70
    if any(k in text for k in ('excavation', 'opening', 'cut')):
        return 0.60
    if any(k in text for k in ('terrain', 'slope')):
        return 0.80
    return 1.0


@dataclass(frozen=True, slots=True)
class MeshSizeFieldSpec:
    name: str
    kind: str = 'distance_threshold'
    target_dim: int = 2
    target_tags: tuple[int, ...] = ()
    size_min: float = 1.0
    size_max: float = 2.0
    dist_min: float = 0.0
    dist_max: float = 4.0
    source: str = 'auto'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'kind': self.kind,
            'target_dim': int(self.target_dim),
            'target_tags': [int(v) for v in self.target_tags],
            'size_min': float(self.size_min),
            'size_max': float(self.size_max),
            'dist_min': float(self.dist_min),
            'dist_max': float(self.dist_max),
            'source': self.source,
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MeshSizeFieldPlan:
    fields: tuple[MeshSizeFieldSpec, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'contract': 'mesh_size_field_plan_v2',
            'fields': [field.to_dict() for field in self.fields],
            'issues': [dict(issue) for issue in self.issues],
            'summary': {
                'field_count': len(self.fields),
                'issue_count': len(self.issues),
                'applies_to': 'gmsh_background_field',
                'engineering_refinement': 'wall_excavation_interface_monitoring_layer',
            },
            'metadata': dict(self.metadata),
        }


class MeshSizeFieldBuilder:
    """Build Gmsh background mesh-size fields from editable entities.

    Users edit solids/faces. These fields are generated during remeshing and are
    not exposed as directly editable mesh primitives.
    """

    def build_from_physical_surfaces(
        self,
        surface_rows: Iterable[dict[str, Any]],
        *,
        global_size: float,
        user_controls: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        gsize = max(1.0e-9, float(global_size))
        rows = [dict(row) for row in list(surface_rows or []) if isinstance(row, dict)]
        controls = [dict(row) for row in list(user_controls or []) if isinstance(row, dict)]
        control_by_name = {str(row.get('target') or row.get('name') or ''): row for row in controls}
        fields: list[MeshSizeFieldSpec] = []
        issues: list[dict[str, Any]] = []
        for row in rows:
            try:
                tag = int(row.get('occ_surface_tag') or row.get('surface_tag') or 0)
            except Exception:
                tag = 0
            if tag <= 0:
                continue
            face_name = str(row.get('face_set_name') or row.get('name') or f'surface_{tag}')
            role = str(row.get('surface_role') or '')
            source_block = str(row.get('source_block') or row.get('region_name') or '')
            ctrl = control_by_name.get(face_name) or control_by_name.get(str(row.get('topology_entity_id') or '')) or {}
            factor = _safe_float(ctrl.get('factor'), _role_size_factor(source_block, role))
            size_min = max(1.0e-9, _safe_float(ctrl.get('size_min'), gsize * factor))
            size_max = max(size_min, _safe_float(ctrl.get('size_max'), gsize))
            dist_min = max(0.0, _safe_float(ctrl.get('dist_min'), 0.0))
            dist_max = max(dist_min + 1.0e-9, _safe_float(ctrl.get('dist_max'), max(gsize * 3.0, size_max * 2.0)))
            if factor < 0.999 or ctrl:
                fields.append(MeshSizeFieldSpec(
                    name=f'mesh_field::{face_name}',
                    target_tags=(tag,),
                    size_min=size_min,
                    size_max=size_max,
                    dist_min=dist_min,
                    dist_max=dist_max,
                    source='surface_role' if not ctrl else 'user_control',
                    metadata={'face_set_name': face_name, 'surface_role': role, 'source_block': source_block, 'topology_entity_id': row.get('topology_entity_id', '')},
                ))
        if not fields:
            issues.append({'id': 'mesh_size_field.empty', 'severity': 'info', 'message': 'No protected/wall/excavation/contact surfaces required local mesh refinement.'})
        return MeshSizeFieldPlan(tuple(fields), tuple(issues), {'global_size': gsize}).to_dict()


def apply_gmsh_mesh_size_field_plan(gmsh: Any, plan: dict[str, Any]) -> dict[str, Any]:
    fields = [dict(row) for row in list(plan.get('fields', []) or []) if isinstance(row, dict)]
    if not fields:
        return {'applied': False, 'field_count': 0, 'issues': list(plan.get('issues', []) or [])}
    ids: list[int] = []
    issues: list[dict[str, Any]] = []
    api = gmsh.model.mesh.field
    for row in fields:
        tags = [int(v) for v in list(row.get('target_tags', []) or []) if int(v) > 0]
        if not tags:
            continue
        try:
            dist = api.add('Distance')
            # Gmsh versions differ in option spelling. Try the modern surface
            # option first, then the older FacesList alias.
            try:
                api.setNumbers(dist, 'SurfacesList', tags)
            except Exception:
                api.setNumbers(dist, 'FacesList', tags)
            thr = api.add('Threshold')
            api.setNumber(thr, 'InField', dist)
            api.setNumber(thr, 'SizeMin', float(row.get('size_min') or 1.0))
            api.setNumber(thr, 'SizeMax', float(row.get('size_max') or 1.0))
            api.setNumber(thr, 'DistMin', float(row.get('dist_min') or 0.0))
            api.setNumber(thr, 'DistMax', float(row.get('dist_max') or 1.0))
            ids.append(int(thr))
        except Exception as exc:  # pragma: no cover - depends on gmsh versions
            issues.append({'id': f'mesh_size_field.apply_failed.{row.get("name", "field")}', 'severity': 'warning', 'message': str(exc), 'target_tags': tags})
    if ids:
        try:
            if len(ids) == 1:
                api.setAsBackgroundMesh(ids[0])
            else:
                min_field = api.add('Min')
                api.setNumbers(min_field, 'FieldsList', ids)
                api.setAsBackgroundMesh(min_field)
                ids.append(int(min_field))
        except Exception as exc:  # pragma: no cover
            issues.append({'id': 'mesh_size_field.background_failed', 'severity': 'warning', 'message': str(exc)})
    return {'applied': bool(ids), 'field_count': len(fields), 'gmsh_field_ids': ids, 'issues': issues}


__all__ = ['MeshSizeFieldBuilder', 'MeshSizeFieldPlan', 'MeshSizeFieldSpec', 'apply_gmsh_mesh_size_field_plan']
