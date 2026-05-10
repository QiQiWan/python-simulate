from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
@dataclass(slots=True)
class InterfaceReadyReport: applied: bool=False; duplicated_region_point_count: int=0; metadata: dict[str, Any]=field(default_factory=dict)
def apply_interface_node_split(model, duplicate_side='slave'):
    report=InterfaceReadyReport(False,0,{'duplicate_side':duplicate_side}); model.metadata['pipeline.interface_ready']={'applied':False,'duplicated_point_count':0,'updated_interface_count':0}; return report
