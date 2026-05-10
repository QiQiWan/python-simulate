from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
@dataclass(slots=True)
class InterfaceMaterializationRequest: interface_name: str=''; request_type: str='face_interface_element'; can_materialize: bool=False; metadata: dict[str, Any]=field(default_factory=dict)
def build_interface_materialization_requests(*args, **kwargs): return ()
def build_interface_materialization_request_payload(*args, **kwargs): return {'summary': {'request_count':0,'face_interface_element_count':0,'manual_review_count':0}, 'request_rows': []}
