from __future__ import annotations

"""Preview overlay helpers for interactive viewport tools."""

from geoai_simkit.contracts.viewport import ViewportPreviewGeometry, ViewportToolOutput


def preview_output(
    tool: str,
    kind: str,
    points: list[tuple[float, float, float]] | tuple[tuple[float, float, float], ...],
    *,
    closed: bool = False,
    message: str = "",
    style: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
) -> ViewportToolOutput:
    """Return a preview output with optional interaction affordance metadata.

    ``metadata`` is consumed by GUI adapters to render cursor crosshairs, snap
    glyphs and snap labels without coupling modeling tools to PyVista/Qt.
    """

    preview = ViewportPreviewGeometry(kind=kind, points=tuple(points), closed=closed, style={"mode": "preview", **dict(style or {})}, metadata=dict(metadata or {}))
    return ViewportToolOutput(kind="preview", tool=tool, message=message, preview=preview, metadata={"preview_metadata": dict(metadata or {})})


def message_output(tool: str, message: str, *, error: bool = False) -> ViewportToolOutput:
    return ViewportToolOutput(kind="error" if error else "message", tool=tool, message=message)


__all__ = ["message_output", "preview_output"]
