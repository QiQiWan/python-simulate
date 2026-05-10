from __future__ import annotations

"""Contracts for cross-module project workflow orchestration.

The 0.8.63 workflow contract keeps legacy payload access through
``ProjectWorkflowReport.artifacts`` for compatibility, but adds typed,
serializable ``WorkflowArtifactRef`` rows as the stable cross-module artifact
index.  GUI, CLI and service callers should prefer these references when they
only need to render status, route to detail panels, export provenance or audit a
workflow without holding implementation objects from mesh/solver/result layers.
"""

from dataclasses import dataclass, field
from typing import Mapping

from .payloads import WorkflowArtifactPayload
from .project import ProjectReadPort, ProjectSnapshot


_WORKFLOW_ARTIFACT_KINDS = ("mesh", "stages", "solve", "summary", "readiness", "quality", "governance", "unknown")


@dataclass(frozen=True, slots=True)
class WorkflowArtifactRef:
    """Typed, dependency-light index row for one workflow artifact.

    ``payload_key`` points at ``ProjectWorkflowReport.artifacts`` when callers
    need the original object.  ``summary`` and ``metadata`` are plain mappings so
    this row can be serialized without importing meshing, solver or result
    implementation classes.
    """

    key: str
    kind: str
    producer: str
    status: str = "ok"
    accepted: bool = True
    payload_type: str = "unknown"
    payload_key: str = ""
    summary: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_payload(self, *, workflow_id: str = "workflow") -> WorkflowArtifactPayload:
        return WorkflowArtifactPayload(
            artifact_id=f"{workflow_id}:{self.kind}:{self.key}",
            key=self.key,
            kind=self.kind,
            producer=self.producer,
            payload_type=self.payload_type,
            status=self.status,
            accepted=bool(self.accepted),
            summary=dict(self.summary),
            diagnostics=tuple(str(item) for item in self.metadata.get("diagnostics", ()) or ()),
            metadata={"payload_key": self.payload_key or self.key, **dict(self.metadata)},
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "kind": self.kind,
            "producer": self.producer,
            "status": self.status,
            "accepted": bool(self.accepted),
            "payload_type": self.payload_type,
            "payload_key": self.payload_key or self.key,
            "summary": dict(self.summary),
            "metadata": dict(self.metadata),
            "typed_payload": self.to_payload().to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MeshWorkflowArtifact(WorkflowArtifactRef):
    """Typed artifact reference for generated/attached meshes."""


@dataclass(frozen=True, slots=True)
class StageWorkflowArtifact(WorkflowArtifactRef):
    """Typed artifact reference for compiled stage models."""


@dataclass(frozen=True, slots=True)
class SolveWorkflowArtifact(WorkflowArtifactRef):
    """Typed artifact reference for solver execution output."""


@dataclass(frozen=True, slots=True)
class ResultWorkflowArtifact(WorkflowArtifactRef):
    """Typed artifact reference for result/postprocessing output."""


def _safe_payload_dict(payload: object) -> dict[str, object]:
    if hasattr(payload, "to_dict"):
        try:
            data = payload.to_dict()
            return dict(data) if isinstance(data, Mapping) else {"value": str(data)}
        except Exception:  # pragma: no cover - defensive only
            return {"value": str(payload)}
    if isinstance(payload, Mapping):
        return dict(payload)
    return {"value": str(payload)}


def _artifact_status(kind: str, payload: object, summary: Mapping[str, object]) -> tuple[bool, str]:
    if kind == "solve":
        accepted = bool(summary.get("accepted", summary.get("ok", getattr(payload, "ok", True))))
        return accepted, str(summary.get("status", "ok" if accepted else "rejected"))
    if kind == "summary":
        accepted = bool(summary.get("accepted", getattr(payload, "accepted", True)))
        return accepted, "ok" if accepted else "rejected"
    accepted = bool(summary.get("ok", getattr(payload, "ok", True)))
    return accepted, str(summary.get("status", "ok" if accepted else "rejected"))


def workflow_artifact_ref_from_payload(key: str, payload: object, *, producer: str | None = None, kind: str | None = None) -> WorkflowArtifactRef:
    """Create a typed artifact reference from a legacy payload object."""

    artifact_kind = str(kind or key or "unknown")
    if artifact_kind not in _WORKFLOW_ARTIFACT_KINDS:
        artifact_kind = "unknown"
    payload_type = f"{type(payload).__module__}.{type(payload).__qualname__}"
    summary = _safe_payload_dict(payload)
    accepted, status = _artifact_status(artifact_kind, payload, summary)
    base = {
        "key": str(key),
        "kind": artifact_kind,
        "producer": str(producer or key),
        "status": status,
        "accepted": accepted,
        "payload_type": payload_type,
        "payload_key": str(key),
        "summary": summary,
        "metadata": {
            "contract": "workflow_artifact_ref_v1",
            "legacy_payload_available": True,
        },
    }
    if artifact_kind == "mesh":
        return MeshWorkflowArtifact(**base)
    if artifact_kind == "stages":
        return StageWorkflowArtifact(**base)
    if artifact_kind == "solve":
        return SolveWorkflowArtifact(**base)
    if artifact_kind == "summary":
        return ResultWorkflowArtifact(**base)
    return WorkflowArtifactRef(**base)


@dataclass(frozen=True, slots=True)
class WorkflowArtifactLineage:
    """Serializable lineage row connecting one artifact to upstream artifacts."""

    artifact_id: str
    key: str
    kind: str
    producer: str
    depends_on: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "key": self.key,
            "kind": self.kind,
            "producer": self.producer,
            "depends_on": list(self.depends_on),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class WorkflowArtifactManifest:
    """Stable manifest for workflow artifacts and provenance."""

    manifest_id: str
    artifacts: tuple[WorkflowArtifactRef, ...] = ()
    lineage: tuple[WorkflowArtifactLineage, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def artifact(self, key: str) -> WorkflowArtifactRef | None:
        for item in self.artifacts:
            if item.key == key:
                return item
        return None

    def typed_payloads(self) -> tuple[WorkflowArtifactPayload, ...]:
        workflow_id = str(self.metadata.get("workflow_id", self.manifest_id.replace(":manifest", "")))
        return tuple(item.to_payload(workflow_id=workflow_id) for item in self.artifacts)

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_id": self.manifest_id,
            "artifact_count": len(self.artifacts),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "typed_payloads": [item.to_dict() for item in self.typed_payloads()],
            "lineage": [item.to_dict() for item in self.lineage],
            "metadata": {"contract": "workflow_artifact_manifest_v2", "contract_version": "workflow_artifact_manifest_v3", **dict(self.metadata)},
        }


def workflow_artifact_manifest_from_refs(refs: tuple[WorkflowArtifactRef, ...] | list[WorkflowArtifactRef], *, workflow_id: str = "workflow") -> WorkflowArtifactManifest:
    ordered = tuple(refs)
    lineage: list[WorkflowArtifactLineage] = []
    previous: list[str] = []
    for item in ordered:
        artifact_id = f"{workflow_id}:{item.kind}:{item.key}"
        dependencies = tuple(previous) if item.key != "mesh" else ()
        lineage.append(
            WorkflowArtifactLineage(
                artifact_id=artifact_id,
                key=item.key,
                kind=item.kind,
                producer=item.producer,
                depends_on=dependencies,
                metadata={"payload_key": item.payload_key or item.key, "payload_type": item.payload_type},
            )
        )
        previous.append(artifact_id)
    return WorkflowArtifactManifest(
        manifest_id=f"{workflow_id}:manifest",
        artifacts=ordered,
        lineage=tuple(lineage),
        metadata={"workflow_id": workflow_id},
    )


@dataclass(frozen=True, slots=True)
class ProjectWorkflowRequest:
    """Dependency-light request for the canonical module interoperability chain."""

    project: ProjectReadPort | object
    mesh_kind: str = "auto"
    solver_backend: str = "reference_cpu"
    postprocessor: str = "auto"
    compile_stages: bool = True
    solve: bool = True
    summarize: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowStepReport:
    """Status emitted by one module facade/service step."""

    key: str
    ok: bool
    status: str = "ok"
    diagnostics: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "ok": bool(self.ok),
            "status": self.status,
            "diagnostics": list(self.diagnostics),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ProjectWorkflowReport:
    """Result of a canonical headless module-interoperability workflow."""

    ok: bool
    snapshot_before: ProjectSnapshot | None = None
    snapshot_after: ProjectSnapshot | None = None
    steps: tuple[WorkflowStepReport, ...] = ()
    artifacts: dict[str, object] = field(default_factory=dict)
    artifact_refs: tuple[WorkflowArtifactRef, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def artifact_ref(self, key: str) -> WorkflowArtifactRef | None:
        for item in self.artifact_refs:
            if item.key == key:
                return item
        return None

    @property
    def typed_artifacts(self) -> tuple[WorkflowArtifactRef, ...]:
        """Alias for callers that want the stable typed artifact index."""

        return self.artifact_refs

    def artifact_manifest(self) -> WorkflowArtifactManifest:
        workflow_id = str(self.metadata.get("workflow_id") or self.metadata.get("case") or "workflow")
        return workflow_artifact_manifest_from_refs(self.artifact_refs, workflow_id=workflow_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "snapshot_before": self.snapshot_before.to_dict() if self.snapshot_before else None,
            "snapshot_after": self.snapshot_after.to_dict() if self.snapshot_after else None,
            "steps": [step.to_dict() for step in self.steps],
            "artifact_keys": sorted(self.artifacts),
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "artifact_manifest": self.artifact_manifest().to_dict(),
            "metadata": dict(self.metadata),
        }


__all__ = [
    "MeshWorkflowArtifact",
    "ProjectWorkflowRequest",
    "ProjectWorkflowReport",
    "ResultWorkflowArtifact",
    "SolveWorkflowArtifact",
    "StageWorkflowArtifact",
    "WorkflowArtifactLineage",
    "WorkflowArtifactManifest",
    "workflow_artifact_manifest_from_refs",
    "WorkflowArtifactRef",
    "WorkflowArtifactPayload",
    "WorkflowStepReport",
    "workflow_artifact_ref_from_payload",
]
