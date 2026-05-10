from __future__ import annotations

"""Selection tool that updates document and viewport selection consistently."""

from geoai_simkit.app.tools.base import ModelingTool, ToolContext, ToolEvent


class SelectTool(ModelingTool):
    name = "select"

    def on_mouse_press(self, event: ToolEvent, context: ToolContext):
        if not event.picked_entity_id:
            context.document.selection.clear()
            return None
        ref = context.viewport.select_entity(event.picked_entity_id, entity_type="block")
        if ref is not None:
            context.document.select(ref)
        return ref
