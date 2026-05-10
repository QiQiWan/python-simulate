from __future__ import annotations

"""Stable selection references used by viewport, tools and property panels."""

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

SelectionEntityType = Literal[
    "point",
    "edge",
    "surface",
    "face",
    "solid",
    "block",
    "cell",
    "node",
    "support",
    "interface",
    "stage",
    "result",
]
SelectionSource = Literal["geometry", "mesh", "stage", "result", "viewport"]


@dataclass(frozen=True, slots=True)
class SelectionRef:
    entity_id: str
    entity_type: SelectionEntityType
    sub_id: str | None = None
    source: SelectionSource = "geometry"
    display_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        suffix = f":{self.sub_id}" if self.sub_id else ""
        return f"{self.source}:{self.entity_type}:{self.entity_id}{suffix}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "sub_id": self.sub_id,
            "source": self.source,
            "display_name": self.display_name or self.entity_id,
            "metadata": dict(self.metadata),
            "key": self.key,
        }


@dataclass(slots=True)
class SelectionSet:
    items: list[SelectionRef] = field(default_factory=list)
    active: SelectionRef | None = None

    def set_single(self, ref: SelectionRef | None) -> None:
        self.items = [] if ref is None else [ref]
        self.active = ref

    def add(self, ref: SelectionRef, *, make_active: bool = True) -> None:
        self.items = [item for item in self.items if item.key != ref.key]
        self.items.append(ref)
        if make_active:
            self.active = ref

    def remove(self, ref_or_key: SelectionRef | str) -> None:
        key = ref_or_key.key if isinstance(ref_or_key, SelectionRef) else str(ref_or_key)
        self.items = [item for item in self.items if item.key != key]
        if self.active is not None and self.active.key == key:
            self.active = self.items[-1] if self.items else None

    def clear(self) -> None:
        self.items.clear()
        self.active = None

    def extend(self, refs: Iterable[SelectionRef]) -> None:
        for ref in refs:
            self.add(ref, make_active=False)
        self.active = self.items[-1] if self.items else None

    def by_type(self, entity_type: SelectionEntityType) -> list[SelectionRef]:
        return [item for item in self.items if item.entity_type == entity_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active.to_dict() if self.active is not None else None,
            "items": [item.to_dict() for item in self.items],
            "count": len(self.items),
        }
