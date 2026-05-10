from __future__ import annotations

"""Adapters between GeoProjectDocument and stable project contracts."""

from typing import Any

from geoai_simkit.contracts import (
    ProjectContext,
    ProjectMutation,
    ProjectReadPort,
    ProjectSnapshot,
    ProjectTransaction,
    ProjectWritePort,
    is_project_port,
    project_document_from,
    project_port_capabilities,
)


GeoProjectDocumentPort = ProjectContext


def make_project_context(project: Any, **metadata: Any) -> ProjectReadPort:
    """Return a Project Port without forcing custom ports back to legacy docs.

    Legacy code can still unwrap a port at adapter boundaries with
    :func:`project_document_from`, but service/module facades should keep the
    port object intact for as long as possible.
    """

    if isinstance(project, ProjectContext):
        if metadata:
            project.metadata.update(metadata)
        return project
    if is_project_port(project):
        # Preserve caller-provided custom ports; dropping them would defeat the
        # Project Port migration because custom read/write boundaries could be
        # silently replaced by raw GeoProjectDocument access.
        return project
    return ProjectContext(project=project, metadata=dict(metadata))


def make_project_port(project: Any, **metadata: Any) -> ProjectReadPort:
    return make_project_context(project, **metadata)


def as_project_context(project_or_port: Any, **metadata: Any) -> ProjectReadPort:
    return make_project_context(project_or_port, **metadata)


def project_from_port(project_or_port: Any) -> Any:
    return project_document_from(project_or_port)


def snapshot_project(project: Any, **metadata: Any) -> ProjectSnapshot:
    context = make_project_context(project, **metadata)
    return context.snapshot()


def mark_project_changed(
    project: Any,
    *,
    action: str,
    channels: tuple[str, ...] | list[str] = (),
    affected_entities: tuple[str, ...] | list[str] = (),
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProjectSnapshot:
    context = make_project_context(project)
    mutation = ProjectMutation(
        action=action,
        channels=tuple(str(item) for item in channels),
        affected_entities=tuple(str(item) for item in affected_entities),
        payload=dict(payload or {}),
        metadata=dict(metadata or {}),
    )
    apply = getattr(context, "apply_mutation", None)
    if callable(apply):
        return apply(mutation)
    # Read-only ports still produce a fresh snapshot; callers can inspect
    # capabilities to know that mutation was not applied.
    return context.snapshot()


def apply_project_transaction(project: Any, transaction: ProjectTransaction) -> ProjectSnapshot:
    context = make_project_context(project)
    apply = getattr(context, "apply_transaction", None)
    if callable(apply):
        return apply(transaction)
    return context.snapshot()


__all__ = [
    "GeoProjectDocumentPort",
    "ProjectReadPort",
    "ProjectWritePort",
    "apply_project_transaction",
    "as_project_context",
    "make_project_context",
    "make_project_port",
    "mark_project_changed",
    "project_from_port",
    "project_port_capabilities",
    "snapshot_project",
]
