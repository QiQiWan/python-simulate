from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from geoai_simkit.core.model import SimulationModel


@dataclass(slots=True)
class InterfaceTopologyInfo:
    interface_name: str
    interface_kind: str
    pair_count: int
    identical_pair_count: int
    overlapping_point_count: int
    duplicate_side: str
    suggested_duplicate_point_ids: tuple[int, ...]
    max_pair_gap: float
    mean_pair_gap: float
    slave_regions: tuple[str, ...] = ()
    master_regions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceNodeSplitPlan:
    interface_name: str
    duplicate_side: str
    source_region_names: tuple[str, ...]
    duplicate_point_ids: tuple[int, ...]
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceTopologySnapshot:
    interfaces: tuple[InterfaceTopologyInfo, ...]
    split_plans: tuple[InterfaceNodeSplitPlan, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'interfaces': interface_topology_summary_rows(self.interfaces),
            'split_plans': interface_node_split_summary_rows(self.split_plans),
            'metadata': dict(self.metadata),
        }


def _point_region_owners(model: SimulationModel) -> dict[int, set[str]]:
    grid = model.to_unstructured_grid()
    owners: dict[int, set[str]] = {}
    for region in model.region_tags:
        region_name = str(region.name)
        for cid in getattr(region, 'cell_ids', ()):
            try:
                cell = grid.get_cell(int(cid))
            except Exception:
                continue
            for pid in getattr(cell, 'point_ids', ()):
                owners.setdefault(int(pid), set()).add(region_name)
    return owners


def analyze_interface_topology(model: SimulationModel, *, duplicate_side: str = 'slave') -> InterfaceTopologySnapshot:
    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    owners = _point_region_owners(model)
    topology_rows: list[InterfaceTopologyInfo] = []
    split_plans: list[InterfaceNodeSplitPlan] = []
    duplicate_side_key = str(duplicate_side or 'slave').strip().lower()
    if duplicate_side_key not in {'slave', 'master'}:
        duplicate_side_key = 'slave'
    total_pairs = 0
    total_suggested = 0
    for interface in model.interfaces:
        slave_ids = [int(v) for v in getattr(interface, 'slave_point_ids', ())]
        master_ids = [int(v) for v in getattr(interface, 'master_point_ids', ())]
        pair_count = min(len(slave_ids), len(master_ids))
        total_pairs += pair_count
        pair_slave = slave_ids[:pair_count]
        pair_master = master_ids[:pair_count]
        identical_ids = [int(s) for s, m in zip(pair_slave, pair_master, strict=False) if int(s) == int(m)]
        overlap_ids = sorted(set(pair_slave).intersection(pair_master))
        gap_values: list[float] = []
        for s, m in zip(pair_slave, pair_master, strict=False):
            if 0 <= int(s) < int(points.shape[0]) and 0 <= int(m) < int(points.shape[0]):
                gap_values.append(float(np.linalg.norm(points[int(s)] - points[int(m)])))
        suggested_ids = tuple(sorted(set(identical_ids if identical_ids else overlap_ids)))
        total_suggested += len(suggested_ids)
        side_point_ids = pair_slave if duplicate_side_key == 'slave' else pair_master
        side_owners = sorted({name for pid in side_point_ids for name in owners.get(int(pid), set())})
        opposite_point_ids = pair_master if duplicate_side_key == 'slave' else pair_slave
        opposite_owners = sorted({name for pid in opposite_point_ids for name in owners.get(int(pid), set())})
        interface_meta = dict(getattr(interface, 'metadata', {}) or {})
        preferred_side_region = str(interface_meta.get('slave_region' if duplicate_side_key == 'slave' else 'master_region') or '').strip()
        preferred_opposite_region = str(interface_meta.get('master_region' if duplicate_side_key == 'slave' else 'slave_region') or '').strip()
        if preferred_side_region:
            side_owners = [preferred_side_region]
        if preferred_opposite_region:
            opposite_owners = [preferred_opposite_region]
        topology_rows.append(
            InterfaceTopologyInfo(
                interface_name=str(interface.name),
                interface_kind=str(interface.kind),
                pair_count=int(pair_count),
                identical_pair_count=int(len(identical_ids)),
                overlapping_point_count=int(len(overlap_ids)),
                duplicate_side=duplicate_side_key,
                suggested_duplicate_point_ids=suggested_ids,
                max_pair_gap=float(max(gap_values) if gap_values else 0.0),
                mean_pair_gap=float(sum(gap_values) / len(gap_values) if gap_values else 0.0),
                slave_regions=tuple(sorted({name for pid in pair_slave for name in owners.get(int(pid), set())})),
                master_regions=tuple(sorted({name for pid in pair_master for name in owners.get(int(pid), set())})),
                metadata={
                    'has_identical_pairs': bool(identical_ids),
                    'has_point_overlap': bool(overlap_ids),
                    'duplicate_side_region_names': side_owners,
                    'opposite_side_region_names': opposite_owners,
                    'active_stages': list(getattr(interface, 'active_stages', ()) or ()),
                },
            )
        )
        if suggested_ids:
            split_plans.append(
                InterfaceNodeSplitPlan(
                    interface_name=str(interface.name),
                    duplicate_side=duplicate_side_key,
                    source_region_names=tuple(side_owners),
                    duplicate_point_ids=suggested_ids,
                    reason='identical_slave_master_pairs' if identical_ids else 'shared_point_ids_across_interface',
                    metadata={
                        'pair_count': int(pair_count),
                        'identical_pair_count': int(len(identical_ids)),
                        'overlapping_point_count': int(len(overlap_ids)),
                        'opposite_region_names': opposite_owners,
                    },
                )
            )
    return InterfaceTopologySnapshot(
        interfaces=tuple(topology_rows),
        split_plans=tuple(split_plans),
        metadata={
            'n_interfaces': int(len(topology_rows)),
            'n_interface_pairs': int(total_pairs),
            'n_split_plans': int(len(split_plans)),
            'n_suggested_duplicate_points': int(total_suggested),
            'duplicate_side': duplicate_side_key,
        },
    )


def interface_topology_summary_rows(items):
    return [{
        'interface_name': item.interface_name,
        'interface_kind': item.interface_kind,
        'pair_count': int(item.pair_count),
        'identical_pair_count': int(item.identical_pair_count),
        'overlapping_point_count': int(item.overlapping_point_count),
        'duplicate_side': item.duplicate_side,
        'suggested_duplicate_point_ids': [int(v) for v in item.suggested_duplicate_point_ids],
        'suggested_duplicate_point_count': int(len(item.suggested_duplicate_point_ids)),
        'max_pair_gap': float(item.max_pair_gap),
        'mean_pair_gap': float(item.mean_pair_gap),
        'slave_regions': list(item.slave_regions),
        'master_regions': list(item.master_regions),
        'metadata': dict(item.metadata),
    } for item in items]


def interface_node_split_summary_rows(items):
    return [{
        'interface_name': item.interface_name,
        'duplicate_side': item.duplicate_side,
        'source_region_names': list(item.source_region_names),
        'duplicate_point_ids': [int(v) for v in item.duplicate_point_ids],
        'duplicate_point_count': int(len(item.duplicate_point_ids)),
        'reason': item.reason,
        'metadata': dict(item.metadata),
    } for item in items]
