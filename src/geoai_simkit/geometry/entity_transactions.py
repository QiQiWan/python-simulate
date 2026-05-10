from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from geoai_simkit.geometry.editable_blocks import EditableBlock, editable_blocks_to_rows, normalize_editable_blocks


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _block_name_from_entity(entity_id: str) -> str:
    text = _clean(entity_id)
    if text.startswith("solid:"):
        return text.split(":", 1)[1].split(":occ_", 1)[0].split(":", 1)[0]
    if text.startswith("face:"):
        parts = text.split(":")
        return parts[1] if len(parts) >= 2 else ""
    return text


def _as_float_triplet(values: Iterable[Any] | None, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    raw = list(values or [])
    out = [default[0], default[1], default[2]]
    for idx, value in enumerate(raw[:3]):
        try:
            out[idx] = float(value)
        except Exception:
            out[idx] = default[idx]
    return (float(out[0]), float(out[1]), float(out[2]))


@dataclass(slots=True)
class EntityTransactionResult:
    action: str
    entity_ids: tuple[str, ...]
    modified_block_names: tuple[str, ...] = ()
    created_named_selection: str = ""
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": "entity_edit_transaction_result_v1",
            "action": self.action,
            "entity_ids": list(self.entity_ids),
            "modified_block_names": list(self.modified_block_names),
            "created_named_selection": self.created_named_selection,
            "issues": [dict(row) for row in self.issues],
            "metadata": dict(self.metadata),
            "mesh_editable": False,
            "edit_policy": "edit_source_entities_then_remesh",
            "requires_remesh": bool(self.modified_block_names or self.created_named_selection),
        }


class EntityEditTransactionManager:
    """Apply GUI entity operations to source entities, never to mesh cells.

    The viewport may expose drag handles and context menus, but this manager is
    the source of truth: only source blocks/named selections/bindings are changed.
    The generated mesh and result package are invalidated by the caller.
    """

    def _match_block(self, block: EditableBlock, entity_ids: set[str]) -> bool:
        if f"solid:{block.name}" in entity_ids or block.name in entity_ids:
            return True
        for entity_id in entity_ids:
            if _block_name_from_entity(entity_id) == block.name:
                return True
        return False

    def apply_transform(
        self,
        parameters: dict[str, Any] | None,
        entity_ids: Iterable[str],
        *,
        translation: Iterable[Any] | None = None,
        scale: Iterable[Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        params = dict(parameters or {})
        ids = tuple(str(v) for v in list(entity_ids or []) if str(v))
        selected = set(ids)
        blocks = normalize_editable_blocks(params.get("editable_blocks") or params.get("blocks") or [])
        dx, dy, dz = _as_float_triplet(translation)
        sx, sy, sz = _as_float_triplet(scale, default=(1.0, 1.0, 1.0))
        modified: list[str] = []
        out: list[EditableBlock] = []
        issues: list[dict[str, Any]] = []
        for block in blocks:
            if self._match_block(block, selected):
                if block.locked:
                    issues.append({"entity_id": f"solid:{block.name}", "severity": "warning", "message": "Locked entity was not transformed."})
                    out.append(block)
                    continue
                updated = block.translated(dx, dy, dz)
                if (sx, sy, sz) != (1.0, 1.0, 1.0):
                    updated = updated.scaled_about_center(sx, sy, sz)
                meta = dict(updated.metadata)
                meta["last_entity_transform"] = {"translation": [dx, dy, dz], "scale": [sx, sy, sz], "source": "viewport_transform"}
                updated = replace(updated, metadata=meta)
                out.append(updated)
                modified.append(block.name)
            else:
                out.append(block)
        if not modified and ids:
            issues.append({"entity_ids": list(ids), "severity": "warning", "message": "No editable source block matched the selected topology entity."})
        params["editable_blocks"] = editable_blocks_to_rows(out)
        params["blocks"] = params["editable_blocks"]
        params["last_entity_edit_transaction"] = EntityTransactionResult(
            action="transform_entities",
            entity_ids=ids,
            modified_block_names=tuple(modified),
            issues=tuple(issues),
            metadata={"translation": [dx, dy, dz], "scale": [sx, sy, sz]},
        ).to_dict()
        return params, params["last_entity_edit_transaction"]

    def create_named_selection(
        self,
        parameters: dict[str, Any] | None,
        entity_ids: Iterable[str],
        *,
        name: str | None = None,
        kind: str = "mixed",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        params = dict(parameters or {})
        ids = tuple(str(v) for v in list(entity_ids or []) if str(v))
        label = _clean(name) or f"selection_{len(list(params.get('named_selections', []) or [])) + 1:02d}"
        row = {
            "name": label,
            "id": f"selection:{label}",
            "kind": kind,
            "entity_ids": list(ids),
            "source": "viewport_selection",
            "edit_policy": "edit_selection_members_or_source_entities_then_remesh",
        }
        selections = [dict(r) for r in list(params.get("named_selections", []) or []) if isinstance(r, dict) and str(r.get("name")) != label]
        selections.append(row)
        params["named_selections"] = selections
        params["last_entity_edit_transaction"] = EntityTransactionResult(
            action="create_named_selection",
            entity_ids=ids,
            created_named_selection=label,
            metadata={"kind": kind},
        ).to_dict()
        return params, params["last_entity_edit_transaction"]

    def build_property_feedback(self, parameters: dict[str, Any] | None, *, entity_id: str, action: str) -> dict[str, Any]:
        params = dict(parameters or {})
        transaction = dict(params.get("last_entity_edit_transaction", {}) or {})
        return {
            "contract": "entity_property_feedback_v2",
            "entity_id": str(entity_id or ""),
            "action": str(action or ""),
            "transaction": transaction,
            "requires_remesh": bool(transaction.get("requires_remesh", False) or params.get("geometry_dirty_state", {}).get("requires_remesh", False)),
            "view_feedback": {
                "highlight_entity_id": str(entity_id or ""),
                "refresh_scene_tree": True,
                "show_remesh_badge": True,
                "message": "Source entity changed; regenerate mesh before solving." if transaction else "No source entity change recorded.",
            },
        }


__all__ = ["EntityEditTransactionManager", "EntityTransactionResult"]
