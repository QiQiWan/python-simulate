from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(slots=True)
class BindingReviewQueue:
    contract: str = "binding_transfer_gui_review_queue_v1"
    review_items: list[dict[str, Any]] = field(default_factory=list)
    auto_items: list[dict[str, Any]] = field(default_factory=list)
    invalid_items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "review_items": list(self.review_items),
            "auto_items": list(self.auto_items),
            "invalid_items": list(self.invalid_items),
            "summary": {
                "review_count": len(self.review_items),
                "auto_count": len(self.auto_items),
                "invalid_count": len(self.invalid_items),
                "requires_user_confirmation": bool(self.review_items or self.invalid_items),
            },
            "available_actions": ["accept", "reject", "map_to_entity", "keep_unassigned"],
        }


class BindingTransferReviewManager:
    """Build and apply GUI review decisions for binding transfer after remesh."""

    def build_queue(self, transfer_report: dict[str, Any] | None, *, candidates: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        report = dict(transfer_report or {})
        review_items: list[dict[str, Any]] = []
        auto_items: list[dict[str, Any]] = []
        invalid_items: list[dict[str, Any]] = [dict(r) for r in list(report.get("invalid_bindings", []) or []) if isinstance(r, dict)]
        transferred = [dict(r) for r in list(report.get("transferred_bindings", []) or report.get("transfers", []) or []) if isinstance(r, dict)]
        for row in transferred:
            if bool(row.get("review_required", False)) or float(row.get("score", 10.0) or 0.0) < 6.0:
                review_items.append({**row, "decision": "pending", "reason": row.get("reason") or "low confidence transfer"})
            else:
                auto_items.append({**row, "decision": "auto_accept"})
        for cand in [dict(r) for r in list(candidates or []) if isinstance(r, dict)]:
            if bool(cand.get("review_required", False)):
                review_items.append({**cand, "decision": "pending", "reason": cand.get("reason") or cand.get("reasons", [])})
            elif bool(cand.get("auto_transfer_recommended", False)):
                auto_items.append({**cand, "decision": "auto_accept"})
        return BindingReviewQueue(review_items=review_items, auto_items=auto_items, invalid_items=invalid_items).to_dict()

    def apply_decisions(self, parameters: dict[str, Any], decisions: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
        params = dict(parameters or {})
        history = list(params.get("binding_transfer_review_history", []) or [])
        applied: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        manual_maps: list[dict[str, Any]] = []
        bindings = dict(params.get("topology_entity_bindings", {}) or {})
        for decision in [dict(r) for r in list(decisions or []) if isinstance(r, dict)]:
            action = str(decision.get("action") or decision.get("decision") or "").lower()
            source = str(decision.get("source_entity") or decision.get("old_entity_id") or decision.get("entity_id") or "")
            target = str(decision.get("target_entity") or decision.get("new_entity_id") or decision.get("mapped_entity_id") or "")
            if action in {"accept", "auto_accept"} and source and target:
                if source in bindings:
                    bindings[target] = dict(bindings.get(source, {}) or {})
                applied.append({"source_entity": source, "target_entity": target, "action": "accept"})
            elif action == "map_to_entity" and source and target:
                if source in bindings:
                    bindings[target] = dict(bindings.get(source, {}) or {})
                manual_maps.append({"source_entity": source, "target_entity": target, "action": "map_to_entity"})
            else:
                rejected.append({"source_entity": source, "target_entity": target, "action": action or "reject"})
        params["topology_entity_bindings"] = bindings
        record = {"contract": "binding_transfer_review_decision_result_v1", "applied": applied, "manual_maps": manual_maps, "rejected": rejected}
        history.append(record)
        params["binding_transfer_review_history"] = history[-25:]
        return params, {**record, "summary": {"applied_count": len(applied), "manual_map_count": len(manual_maps), "rejected_count": len(rejected)}}


__all__ = ["BindingTransferReviewManager", "BindingReviewQueue"]
