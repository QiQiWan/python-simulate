from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
@dataclass(slots=True)
class InterfaceFaceElementGroup: name: str=''; metadata: dict[str, Any]=field(default_factory=dict)
@dataclass(slots=True)
class InterfaceFaceElementPreview: elements: tuple=(); groups: tuple=(); metadata: dict[str, Any]=field(default_factory=dict)
@dataclass(slots=True)
class InterfaceFaceElementSnapshot: elements: tuple=(); groups: tuple=(); metadata: dict[str, Any]=field(default_factory=dict)
def compute_interface_face_elements(model): return InterfaceFaceElementPreview((), (), {'total_area':0.0})
def materialize_interface_face_definitions(model, interface_names=()): return ()
def interface_element_definition_summary_rows(items): return []
def interface_face_element_summary_rows(items): return []
def interface_face_group_summary_rows(items): return []
