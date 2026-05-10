from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _entity_id(row: dict[str, Any]) -> str:
    return _clean(row.get('id') or row.get('topology_entity_id') or row.get('entity_id') or row.get('name'))


def _surface_name(row: dict[str, Any]) -> str:
    return _clean(row.get('face_set_name') or row.get('name') or row.get('protected_surface'))


def _source_region(row: dict[str, Any]) -> str:
    return _clean(row.get('region_name') or row.get('source_block') or row.get('target_block'))


def _kind_from_entity(entity: str) -> str:
    if entity.startswith(('face:', 'face_set:', 'protected_surface:')):
        return 'face'
    if entity.startswith('solid:'):
        return 'solid'
    if entity.startswith('edge:'):
        return 'edge'
    return 'entity'


def _solid_base(entity: str) -> str:
    if entity.startswith('solid:'):
        return entity.split(':', 1)[1].split(':occ_', 1)[0]
    return entity


def _face_parts(entity: str) -> tuple[str, str]:
    if entity.startswith('face:'):
        parts = entity.split(':')
        if len(parts) >= 3:
            return parts[1], parts[2]
    if entity.startswith('face_set:'):
        return '', entity.split(':', 1)[1]
    if entity.startswith('protected_surface:'):
        return '', entity.split(':', 1)[1].split(':panel_', 1)[0]
    return '', entity


def collect_current_entity_rows(
    *,
    editable_payload: dict[str, Any] | None = None,
    brep_document: dict[str, Any] | None = None,
    face_sets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    payload = dict(editable_payload or {})
    brep = dict(brep_document or payload.get('brep_document', {}) or {})
    rows: list[dict[str, Any]] = []
    for key in ('solid_rows', 'face_rows', 'named_selection_rows'):
        for row in list(payload.get(key, []) or []):
            if isinstance(row, dict):
                rows.append({**dict(row), 'source_table': key})
    for key in ('volumes', 'surfaces', 'edges'):
        for row in list(brep.get(key, []) or []):
            if isinstance(row, dict):
                rows.append({**dict(row), 'source_table': f'brep.{key}'})
    fs = dict(face_sets or {})
    for row in list(fs.get('face_sets', payload.get('solver_face_set_rows', [])) or []):
        if isinstance(row, dict):
            name = _surface_name(row)
            rows.append({**dict(row), 'id': f'face_set:{name}' if name else _entity_id(row), 'kind': 'face', 'source_table': 'solver_face_sets'})
    return [row for row in rows if _entity_id(row)]


@dataclass(slots=True)
class BindingTransferReport:
    transferred_bindings: dict[str, Any] = field(default_factory=dict)
    transfer_map: dict[str, list[str]] = field(default_factory=dict)
    invalid_bindings: tuple[dict[str, Any], ...] = ()
    unchanged_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            'contract': 'binding_transfer_report_v1',
            'transferred_bindings': dict(self.transferred_bindings),
            'transfer_map': {str(k): list(v) for k, v in self.transfer_map.items()},
            'invalid_bindings': [dict(row) for row in self.invalid_bindings],
            'summary': {
                'binding_count': len(self.transferred_bindings),
                'transferred_source_count': len(self.transfer_map),
                'invalid_binding_count': len(self.invalid_bindings),
                'unchanged_count': int(self.unchanged_count),
            },
        }


class BindingTransferManager:
    """Preserve entity bindings after entity edits and remeshing.

    The manager never edits mesh cells. It maps bindings from source topology
    entities to current BRep/face-set entities that were regenerated from the
    latest editable solids.
    """

    def _candidate_ids(self, entity: str, rows: list[dict[str, Any]]) -> list[str]:
        entity = _clean(entity)
        if not entity:
            return []
        current = {_entity_id(row) for row in rows}
        if entity in current:
            return [entity]
        kind = _kind_from_entity(entity)
        candidates: list[str] = []
        if kind == 'solid':
            base = _solid_base(entity)
            for row in rows:
                rid = _entity_id(row)
                if not rid:
                    continue
                if rid.startswith('solid:') and (_source_region(row) == base or base in rid):
                    candidates.append(rid)
        elif kind == 'face':
            region, face = _face_parts(entity)
            for row in rows:
                rid = _entity_id(row)
                if not rid or not rid.startswith(('face:', 'face_set:', 'protected_surface:')):
                    continue
                sname = _surface_name(row)
                src = _source_region(row)
                protected = _clean(row.get('protected_surface'))
                if entity.startswith('protected_surface:') and protected and protected in entity:
                    candidates.append(rid)
                elif entity.startswith('face_set:') and sname and (sname == face or face in sname):
                    candidates.append(rid)
                elif region and src == region and (not face or face in rid or face in sname):
                    candidates.append(rid)
                elif face and (face in rid or face in sname):
                    candidates.append(rid)
        return list(dict.fromkeys(candidates))

    def transfer(
        self,
        bindings: dict[str, Any] | None,
        *,
        editable_payload: dict[str, Any] | None = None,
        brep_document: dict[str, Any] | None = None,
        face_sets: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source = {str(k): v for k, v in dict(bindings or {}).items() if str(k)}
        rows = collect_current_entity_rows(editable_payload=editable_payload, brep_document=brep_document, face_sets=face_sets)
        transferred: dict[str, Any] = {}
        transfer_map: dict[str, list[str]] = {}
        invalid: list[dict[str, Any]] = []
        unchanged = 0
        for entity, payload in source.items():
            targets = self._candidate_ids(entity, rows)
            if not targets:
                invalid.append({'entity_id': entity, 'reason': 'no_current_entity_match', 'binding': payload})
                continue
            if targets == [entity]:
                unchanged += 1
            else:
                transfer_map[entity] = targets
            for target in targets:
                existing = dict(transferred.get(target, {}) or {})
                incoming = dict(payload or {}) if isinstance(payload, dict) else {'value': payload}
                merged = {**incoming, **existing}
                inherited = list(merged.get('inherited_from', []) or [])
                if target != entity:
                    inherited.append(entity)
                if inherited:
                    merged['inherited_from'] = list(dict.fromkeys(inherited))
                transferred[target] = merged
        return BindingTransferReport(transferred, transfer_map, tuple(invalid), unchanged).to_dict()


__all__ = ['BindingTransferManager', 'BindingTransferReport', 'collect_current_entity_rows']
