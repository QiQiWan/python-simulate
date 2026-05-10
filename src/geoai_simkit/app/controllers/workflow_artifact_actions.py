from __future__ import annotations

"""Qt-free controller for typed workflow artifacts.

GUI panels can use this controller to render workflow outputs through stable
``WorkflowArtifactRef`` DTOs instead of inspecting mesh/solver/result payload
objects directly.
"""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.contracts import ProjectWorkflowReport, WorkflowArtifactRef, workflow_artifact_ref_from_payload


@dataclass(slots=True)
class WorkflowArtifactActionController:
    """Expose typed workflow artifact summaries for GUI/status panels."""

    report: ProjectWorkflowReport | None = None

    def artifact_refs(self, report: ProjectWorkflowReport | None = None) -> list[dict[str, Any]]:
        active = report or self.report
        if active is None:
            return []
        return [item.to_dict() for item in active.artifact_refs]

    def artifact_manifest(self, report: ProjectWorkflowReport | None = None) -> dict[str, Any]:
        active = report or self.report
        if active is None:
            return {"manifest_id": "empty", "artifacts": [], "lineage": []}
        return active.artifact_manifest().to_dict()

    def artifact_table_rows(self, report: ProjectWorkflowReport | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for ref in self.artifact_refs(report):
            summary = dict(ref.get("summary", {}))
            rows.append(
                {
                    "key": ref.get("key", ""),
                    "kind": ref.get("kind", "unknown"),
                    "producer": ref.get("producer", ""),
                    "accepted": bool(ref.get("accepted", False)),
                    "status": ref.get("status", "unknown"),
                    "payload_type": ref.get("payload_type", "unknown"),
                    "headline": _headline(summary),
                }
            )
        return rows

    def ref_from_payload(self, key: str, payload: Any, *, producer: str | None = None, kind: str | None = None) -> WorkflowArtifactRef:
        return workflow_artifact_ref_from_payload(key, payload, producer=producer, kind=kind)


def _headline(summary: dict[str, Any]) -> str:
    for candidate in ("status", "mesh_kind", "backend_key", "stage_count", "field_count"):
        if candidate in summary:
            return f"{candidate}={summary[candidate]}"
    if "metadata" in summary and isinstance(summary["metadata"], dict):
        metadata = summary["metadata"]
        for candidate in ("plugin", "backend", "contract"):
            if candidate in metadata:
                return f"{candidate}={metadata[candidate]}"
    return ""


__all__ = ["WorkflowArtifactActionController"]
