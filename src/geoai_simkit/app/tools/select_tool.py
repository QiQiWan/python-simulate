from __future__ import annotations

"""Selection tool that updates document, viewport and multi-selection state."""

from geoai_simkit.app.tools.base import ModelingTool, ToolContext, ToolEvent
from geoai_simkit.app.viewport.pick_adapter import pick_from_tool_event
from geoai_simkit.app.viewport.selection_controller import SelectionController
from geoai_simkit.contracts.viewport import ViewportSelectionItem, ViewportSelectionSet, ViewportToolOutput


class SelectTool(ModelingTool):
    name = "select"

    def _controller(self, context: ToolContext) -> SelectionController:
        controller = None
        if isinstance(context.metadata, dict):
            controller = context.metadata.get("selection_controller")
        if controller is None:
            controller = SelectionController()
            if isinstance(context.metadata, dict):
                context.metadata["selection_controller"] = controller
        return controller

    def on_mouse_press(self, event: ToolEvent, context: ToolContext):
        pick = pick_from_tool_event(event)
        controller = self._controller(context)
        modifiers = {str(item).lower() for item in event.modifiers}
        if not pick.entity_id:
            selection = getattr(context.document, "selection", None)
            if selection is not None and hasattr(selection, "clear"):
                selection.clear()
            controller.clear()
            return ViewportToolOutput(kind="selection", tool=self.name, message="Cleared selection", selection=ViewportSelectionSet(()))
        entity_type = str(event.metadata.get("entity_type") or event.metadata.get("picked_kind") or "block")
        mode = "replace"
        if "shift" in modifiers:
            mode = "add"
        elif "ctrl" in modifiers or "control" in modifiers or "cmd" in modifiers or "meta" in modifiers:
            mode = "toggle"
        ref = None
        if hasattr(context.viewport, "select_entity"):
            ref = context.viewport.select_entity(pick.entity_id, entity_type=entity_type)
        if ref is not None and hasattr(context.document, "select"):
            document_selection = getattr(context.document, "selection", None)
            if mode == "replace" and document_selection is not None and hasattr(document_selection, "clear"):
                document_selection.clear()
            try:
                context.document.select(ref)
            except Exception:
                pass
        selection = controller.select(pick.entity_id, entity_type, mode=mode, metadata=pick.metadata)
        item_count = len(selection.items)
        return ViewportToolOutput(kind="selection", tool=self.name, message=f"Selected {item_count} item(s)", selection=selection)

    def on_key_press(self, key: str, context: ToolContext):
        if str(key).lower() in {"i", "invert"}:
            controller = self._controller(context)
            state = context.viewport
            if hasattr(state, "primitives"):
                selection = controller.invert(state)
                return ViewportToolOutput(kind="selection", tool=self.name, message=f"Inverted selection: {len(selection.items)} item(s)", selection=selection)
        return None


__all__ = ["SelectTool"]
