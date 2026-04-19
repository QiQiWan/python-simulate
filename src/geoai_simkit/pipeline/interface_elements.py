from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from geoai_simkit.core.model import InterfaceDefinition, InterfaceElementDefinition, SimulationModel
from geoai_simkit.pipeline.surfaces import _region_face_records
from geoai_simkit.pipeline.topology import _point_region_owners


@dataclass(slots=True)
class InterfaceFaceElementPreview:
    interface_name: str
    interface_kind: str
    slave_region: str
    master_region: str
    element_kind: str
    slave_point_ids: tuple[int, ...]
    master_point_ids: tuple[int, ...]
    area: float
    centroid: tuple[float, float, float]
    duplicate_side: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceFaceElementGroup:
    interface_name: str
    interface_kind: str
    slave_region: str
    master_region: str
    duplicate_side: str
    element_count: int
    total_area: float
    element_kinds: dict[str, int]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceFaceElementSnapshot:
    groups: tuple[InterfaceFaceElementGroup, ...]
    elements: tuple[InterfaceFaceElementPreview, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'groups': interface_face_group_summary_rows(self.groups),
            'elements': interface_face_element_summary_rows(self.elements),
            'metadata': dict(self.metadata),
        }


def _infer_single_region(point_ids: tuple[int, ...], owners: dict[int, set[str]]) -> str:
    regions = sorted({name for pid in point_ids for name in owners.get(int(pid), set())})
    if len(regions) == 1:
        return str(regions[0])
    return ''


def _element_kind_from_count(point_count: int) -> str:
    if int(point_count) == 2:
        return 'line2'
    if int(point_count) == 3:
        return 'tria3'
    if int(point_count) == 4:
        return 'quad4'
    return f'polygon{int(point_count)}'


def _candidate_face_records_for_interface(
    interface: InterfaceDefinition,
    *,
    by_region: dict[str, list[Any]],
    owners: dict[int, set[str]],
) -> tuple[list[Any], dict[int, int], str, str, str]:
    slave_ids = tuple(int(v) for v in getattr(interface, 'slave_point_ids', ()) or ())
    master_ids = tuple(int(v) for v in getattr(interface, 'master_point_ids', ()) or ())
    pair_count = min(len(slave_ids), len(master_ids))
    slave_ids = slave_ids[:pair_count]
    master_ids = master_ids[:pair_count]
    if not slave_ids or not master_ids:
        return [], {}, '', '', 'slave'
    meta = dict(getattr(interface, 'metadata', {}) or {})
    slave_region = str(meta.get('slave_region') or '').strip()
    master_region = str(meta.get('master_region') or '').strip()
    inferred_slave_region = _infer_single_region(slave_ids, owners)
    inferred_master_region = _infer_single_region(master_ids, owners)
    if inferred_slave_region and slave_region not in owners.get(int(slave_ids[0]), set()):
        slave_region = inferred_slave_region
    elif not slave_region:
        slave_region = inferred_slave_region
    if inferred_master_region and master_region not in owners.get(int(master_ids[0]), set()):
        master_region = inferred_master_region
    elif not master_region:
        master_region = inferred_master_region
    duplicate_side = str(meta.get('interface_ready_duplicate_side') or 'slave').strip().lower()
    if duplicate_side not in {'slave', 'master'}:
        duplicate_side = 'slave'
    if duplicate_side == 'slave':
        driving_region = slave_region
        driving_ids = slave_ids
        mapping = {int(s): int(m) for s, m in zip(slave_ids, master_ids, strict=False)}
    else:
        driving_region = master_region
        driving_ids = master_ids
        mapping = {int(m): int(s) for s, m in zip(slave_ids, master_ids, strict=False)}
    if not driving_region:
        return [], {}, slave_region, master_region, duplicate_side
    driving_set = set(int(v) for v in driving_ids)
    records: list[Any] = []
    for record in by_region.get(driving_region, []):
        point_ids = tuple(int(v) for v in getattr(record, 'point_ids', ()) or ())
        if len(point_ids) < 2:
            continue
        if not all(int(pid) in driving_set for pid in point_ids):
            continue
        if not all(int(pid) in mapping for pid in point_ids):
            continue
        mapped = tuple(int(mapping[int(pid)]) for pid in point_ids)
        if duplicate_side == 'slave':
            opposite_region = master_region
        else:
            opposite_region = slave_region
        if opposite_region and not all(opposite_region in owners.get(int(pid), set()) for pid in mapped):
            continue
        records.append(record)
    return records, mapping, slave_region, master_region, duplicate_side


def compute_interface_face_elements(
    model: SimulationModel,
    *,
    interface_names: tuple[str, ...] = (),
) -> InterfaceFaceElementSnapshot:
    selected = {str(v) for v in interface_names if str(v)}
    by_region, _, _ = _region_face_records(model)
    owners = _point_region_owners(model)
    groups: list[InterfaceFaceElementGroup] = []
    elements: list[InterfaceFaceElementPreview] = []
    total_area = 0.0
    for interface in model.interfaces:
        if selected and str(interface.name) not in selected:
            continue
        records, mapping, slave_region, master_region, duplicate_side = _candidate_face_records_for_interface(interface, by_region=by_region, owners=owners)
        if not records:
            continue
        kind_counts: dict[str, int] = {}
        group_area = 0.0
        for record in records:
            driving_face = tuple(int(v) for v in getattr(record, 'point_ids', ()) or ())
            mapped_face = tuple(int(mapping[int(pid)]) for pid in driving_face)
            if duplicate_side == 'slave':
                slave_face = driving_face
                master_face = mapped_face
            else:
                slave_face = mapped_face
                master_face = driving_face
            kind = _element_kind_from_count(len(slave_face))
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            area = float(getattr(record, 'area', 0.0) or 0.0)
            group_area += area
            total_area += area
            centroid_vec = np.asarray(getattr(record, 'centroid', np.zeros(3, dtype=float)), dtype=float).reshape(-1)
            if centroid_vec.size < 3:
                centroid_vec = np.pad(centroid_vec, (0, max(0, 3 - centroid_vec.size)), constant_values=0.0)
            elements.append(
                InterfaceFaceElementPreview(
                    interface_name=str(interface.name),
                    interface_kind=str(interface.kind),
                    slave_region=slave_region,
                    master_region=master_region,
                    element_kind=kind,
                    slave_point_ids=tuple(int(v) for v in slave_face),
                    master_point_ids=tuple(int(v) for v in master_face),
                    area=area,
                    centroid=(float(centroid_vec[0]), float(centroid_vec[1]), float(centroid_vec[2])),
                    duplicate_side=duplicate_side,
                    metadata={
                        'active_stages': list(getattr(interface, 'active_stages', ()) or ()),
                        'pair_count': int(min(len(interface.slave_point_ids), len(interface.master_point_ids))),
                    },
                )
            )
        groups.append(
            InterfaceFaceElementGroup(
                interface_name=str(interface.name),
                interface_kind=str(interface.kind),
                slave_region=slave_region,
                master_region=master_region,
                duplicate_side=duplicate_side,
                element_count=int(len(records)),
                total_area=float(group_area),
                element_kinds=dict(sorted(kind_counts.items())),
                metadata={
                    'has_interface_ready_metadata': bool(getattr(interface, 'metadata', {}) and 'interface_ready_duplicate_side' in getattr(interface, 'metadata', {})),
                },
            )
        )
    groups.sort(key=lambda item: (-item.element_count, -item.total_area, item.interface_name))
    elements.sort(key=lambda item: (item.interface_name, item.element_kind, -item.area))
    metadata = {
        'n_groups': int(len(groups)),
        'n_elements': int(len(elements)),
        'total_area': float(total_area),
    }
    return InterfaceFaceElementSnapshot(groups=tuple(groups), elements=tuple(elements), metadata=metadata)


def interface_face_group_summary_rows(items: tuple[InterfaceFaceElementGroup, ...] | list[InterfaceFaceElementGroup]) -> list[dict[str, Any]]:
    return [
        {
            'interface_name': item.interface_name,
            'interface_kind': item.interface_kind,
            'slave_region': item.slave_region,
            'master_region': item.master_region,
            'duplicate_side': item.duplicate_side,
            'element_count': int(item.element_count),
            'total_area': float(item.total_area),
            'element_kinds': dict(item.element_kinds),
            'metadata': dict(item.metadata),
        }
        for item in items
    ]


def interface_face_element_summary_rows(items: tuple[InterfaceFaceElementPreview, ...] | list[InterfaceFaceElementPreview]) -> list[dict[str, Any]]:
    return [
        {
            'interface_name': item.interface_name,
            'interface_kind': item.interface_kind,
            'slave_region': item.slave_region,
            'master_region': item.master_region,
            'element_kind': item.element_kind,
            'slave_point_ids': [int(v) for v in item.slave_point_ids],
            'master_point_ids': [int(v) for v in item.master_point_ids],
            'point_count': int(len(item.slave_point_ids)),
            'area': float(item.area),
            'centroid': [float(v) for v in item.centroid],
            'duplicate_side': item.duplicate_side,
            'metadata': dict(item.metadata),
        }
        for item in items
    ]


def materialize_interface_face_definitions(
    model: SimulationModel,
    *,
    interface_names: tuple[str, ...] = (),
) -> tuple[InterfaceElementDefinition, ...]:
    snapshot = compute_interface_face_elements(model, interface_names=interface_names)
    definitions: list[InterfaceElementDefinition] = []
    for idx, item in enumerate(snapshot.elements):
        parameters = {'area': float(item.area), 'duplicate_side': item.duplicate_side}
        metadata = dict(item.metadata)
        metadata.update({
            'interface_kind': item.interface_kind,
            'slave_region': item.slave_region,
            'master_region': item.master_region,
            'centroid': [float(v) for v in item.centroid],
            'source': 'pipeline.interface_face_elements',
        })
        definitions.append(
            InterfaceElementDefinition(
                name=f"{item.interface_name}::face::{idx}",
                interface_name=item.interface_name,
                element_kind=item.element_kind,
                slave_point_ids=tuple(int(v) for v in item.slave_point_ids),
                master_point_ids=tuple(int(v) for v in item.master_point_ids),
                active_stages=tuple(item.metadata.get('active_stages', ()) or ()),
                parameters=parameters,
                metadata=metadata,
            )
        )
    return tuple(definitions)


def interface_element_definition_summary_rows(
    items: tuple[InterfaceElementDefinition, ...] | list[InterfaceElementDefinition],
) -> list[dict[str, Any]]:
    return [
        {
            'name': item.name,
            'interface_name': item.interface_name,
            'element_kind': item.element_kind,
            'slave_point_ids': [int(v) for v in item.slave_point_ids],
            'master_point_ids': [int(v) for v in item.master_point_ids],
            'point_count': int(len(item.slave_point_ids)),
            'active_stages': list(item.active_stages),
            'parameters': dict(item.parameters),
            'metadata': dict(item.metadata),
        }
        for item in items
    ]
