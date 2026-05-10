from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
@dataclass(slots=True)
class InterfaceNodeSplitPlan: name: str=''; metadata: dict[str, Any]=field(default_factory=dict)
@dataclass(slots=True)
class InterfaceTopologyInfo: split_plans: tuple=(); metadata: dict[str, Any]=field(default_factory=dict)
@dataclass(slots=True)
class InterfaceTopologySnapshot: rows: tuple=(); metadata: dict[str, Any]=field(default_factory=dict)
def analyze_interface_topology(model): return InterfaceTopologyInfo((), {'n_suggested_duplicate_points': 0})
def interface_topology_snapshot(model): return InterfaceTopologySnapshot((), {})
