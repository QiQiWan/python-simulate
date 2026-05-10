from __future__ import annotations

"""Stable facade for GUI modeling and headless modeling workflows."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.app.modeling_architecture import build_visual_modeling_architecture_payload
from geoai_simkit.app.viewport import HeadlessViewport
from geoai_simkit.commands import CommandStack
from geoai_simkit.document import EngineeringDocument
from geoai_simkit.modules.contracts import smoke_from_spec
from geoai_simkit.modules.registry import get_project_module

MODULE_KEY = "gui_modeling"


@dataclass(slots=True)
class HeadlessModelingSession:
    document: EngineeringDocument
    viewport: HeadlessViewport
    command_stack: CommandStack

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_name": self.document.name,
            "viewport": self.viewport.render_payload(),
            "command_count": len(self.command_stack.history),
        }


def describe_module() -> dict[str, Any]:
    return get_project_module(MODULE_KEY).to_dict()


def create_headless_modeling_session(
    parameters: dict[str, Any] | None = None,
    *,
    name: str = "foundation-pit",
) -> HeadlessModelingSession:
    document = EngineeringDocument.create_foundation_pit(parameters or {"dimension": "3d"}, name=name)
    if document.mesh is None:
        document.generate_preview_mesh()
    viewport = HeadlessViewport()
    viewport.load_document(document)
    return HeadlessModelingSession(document=document, viewport=viewport, command_stack=CommandStack())


def build_modeling_architecture_payload(document: EngineeringDocument) -> dict[str, Any]:
    return build_visual_modeling_architecture_payload(document)


def smoke_check() -> dict[str, Any]:
    session = create_headless_modeling_session({"dimension": "3d"}, name="gui-module-smoke")
    payload = session.to_dict()
    return smoke_from_spec(
        get_project_module(MODULE_KEY),
        checks={
            "document_created": payload["document_name"] == "gui-module-smoke",
            "viewport_has_primitives": len(payload["viewport"].get("primitives", [])) > 0,
        },
    )


__all__ = [
    "HeadlessModelingSession",
    "build_modeling_architecture_payload",
    "create_headless_modeling_session",
    "describe_module",
    "smoke_check",
]
