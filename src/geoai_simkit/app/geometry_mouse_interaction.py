from __future__ import annotations

"""Mouse-level geometry editing controller for the modern workbench.

This module is deliberately independent from Qt/PyVista.  The GUI passes model
coordinates and optional picked entity ids; tests can drive the same controller
without a display server.  It covers the first interactive editor contract:
click-to-create points, continuous line drawing, surface closure, box block
creation, point dragging, rubber-band selection, multi-selection and context
menu actions.
"""

from dataclasses import dataclass, field
from math import hypot
from typing import Any, Iterable, Literal

from geoai_simkit.document import SelectionRef

MouseToolMode = Literal["select", "point", "line", "surface", "block", "move_point", "soil_layer", "excavation", "wall", "strut", "anchor"]
MouseButton = Literal["left", "right"]
SelectionModifier = Literal["replace", "add", "toggle"]


@dataclass(slots=True)
class MouseInteractionResult:
    ok: bool = True
    action: str = ""
    message: str = ""
    entity_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "action": self.action,
            "message": self.message,
            "entity_ids": list(self.entity_ids),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class GeometryMouseController:
    """State machine for section-viewport mouse editing."""

    system: Any
    mode: MouseToolMode = "select"
    default_y: float = 0.0
    snap: bool = True
    block_half_width_y: float = 0.5
    surface_close_tolerance: float = 0.65
    line_anchor: tuple[float, float, float] | None = None
    block_anchor: tuple[float, float, float] | None = None
    surface_vertices: list[tuple[float, float, float]] = field(default_factory=list)
    excavation_vertices: list[tuple[float, float, float]] = field(default_factory=list)
    support_anchor: tuple[float, float, float] | None = None
    layer_anchor: tuple[float, float, float] | None = None
    drag_entity_id: str | None = None
    preview_point: tuple[float, float, float] | None = None
    last_context_actions: list[dict[str, Any]] = field(default_factory=list)

    def set_mode(self, mode: MouseToolMode) -> MouseInteractionResult:
        self.mode = mode
        if mode not in {"line", "surface", "block", "excavation", "wall", "strut", "anchor", "soil_layer"}:
            self.line_anchor = None
            self.block_anchor = None
            self.support_anchor = None
            self.layer_anchor = None
            self.surface_vertices.clear()
            self.excavation_vertices.clear()
        self.preview_point = None
        self.system.active_tool_name = mode
        self.system.log("mouse_tool_mode", mode=mode)
        return MouseInteractionResult(action="set_mode", message=f"Tool mode set to {mode}", metadata=self.preview_state())

    def cancel(self) -> MouseInteractionResult:
        self.line_anchor = None
        self.block_anchor = None
        self.surface_vertices.clear()
        self.excavation_vertices.clear()
        self.support_anchor = None
        self.layer_anchor = None
        self.drag_entity_id = None
        self.preview_point = None
        self.system.log("mouse_cancel")
        return MouseInteractionResult(action="cancel", message="Pending mouse operation cancelled.", metadata=self.preview_state())

    def _xyz(self, x: float, z: float) -> tuple[float, float, float]:
        return (float(x), float(self.default_y), float(z))

    def _distance_xz(self, a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return hypot(float(a[0]) - float(b[0]), float(a[2]) - float(b[2]))

    def click(
        self,
        x: float,
        z: float,
        *,
        entity_id: str | None = None,
        entity_type: str | None = None,
        button: MouseButton = "left",
        selection_modifier: SelectionModifier = "replace",
    ) -> MouseInteractionResult:
        xyz = self._xyz(x, z)
        if button == "right":
            self.last_context_actions = self.context_actions(entity_id=entity_id, entity_type=entity_type)
            return MouseInteractionResult(action="context_menu", entity_ids=[] if not entity_id else [entity_id], metadata={"actions": list(self.last_context_actions)})

        if self.mode == "select":
            if entity_id and entity_type:
                ref = self.system.make_selection_ref(entity_id, entity_type)
                if ref is None:
                    return MouseInteractionResult(ok=False, action="select", message=f"Entity not found: {entity_type}:{entity_id}")
                self.system.apply_selection(ref, modifier=selection_modifier)
                return MouseInteractionResult(action="select", entity_ids=[entity_id], metadata={"modifier": selection_modifier})
            self.system.clear_selection()
            return MouseInteractionResult(action="clear_selection", message="Selection cleared.")

        if self.mode == "move_point":
            if entity_id and entity_type == "point":
                ref = self.system.make_selection_ref(entity_id, "point")
                if ref is not None:
                    self.system.apply_selection(ref, modifier="replace")
                    self.drag_entity_id = entity_id
                    return MouseInteractionResult(action="start_point_drag", entity_ids=[entity_id])
            # No point was picked; move selected point directly to clicked location.
            result = self.system.move_selected_point(*xyz, snap=self.snap)
            return MouseInteractionResult(action="move_selected_point", metadata={"result": result or {}})

        if self.mode == "point":
            result = self.system.create_point(*xyz, snap=self.snap)
            return MouseInteractionResult(action="create_point", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result})

        if self.mode == "line":
            if self.line_anchor is None:
                self.line_anchor = xyz
                self.preview_point = xyz
                return MouseInteractionResult(action="line_anchor", message="Line start point set.", metadata=self.preview_state())
            result = self.system.create_line(self.line_anchor, xyz, snap=self.snap)
            affected = list(result.get("affected_entities", []) or [])
            # Continuous line mode: keep the second point as the next anchor.
            self.line_anchor = xyz
            self.preview_point = xyz
            return MouseInteractionResult(action="create_line_segment", entity_ids=affected, metadata={"result": result, "continuous": True, **self.preview_state()})

        if self.mode == "surface":
            if self.surface_vertices and len(self.surface_vertices) >= 3 and self._distance_xz(self.surface_vertices[0], xyz) <= self.surface_close_tolerance:
                return self.close_surface()
            self.surface_vertices.append(xyz)
            self.preview_point = xyz
            return MouseInteractionResult(action="surface_vertex", message=f"Surface vertex {len(self.surface_vertices)} added.", metadata=self.preview_state())

        if self.mode == "soil_layer":
            if self.layer_anchor is None:
                self.layer_anchor = xyz
                self.preview_point = xyz
                return MouseInteractionResult(action="soil_layer_anchor", message="Drag or click to set horizontal soil layer split.", metadata=self.preview_state())
            result = self.system.split_soil_layer_at(xyz[2])
            self.layer_anchor = None
            self.preview_point = None
            return MouseInteractionResult(action="split_soil_layer", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result})

        if self.mode in {"wall", "strut", "anchor"}:
            if self.support_anchor is None:
                self.support_anchor = xyz
                self.preview_point = xyz
                return MouseInteractionResult(action=f"{self.mode}_anchor", message=f"{self.mode} start point set.", metadata=self.preview_state())
            result = self.system.create_support(self.support_anchor, xyz, support_type=self.mode)
            self.support_anchor = None
            self.preview_point = None
            return MouseInteractionResult(action="create_support", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result, "support_type": self.mode})

        if self.mode == "excavation":
            if self.excavation_vertices and len(self.excavation_vertices) >= 3 and self._distance_xz(self.excavation_vertices[0], xyz) <= self.surface_close_tolerance:
                return self.close_excavation_polygon()
            self.excavation_vertices.append(xyz)
            self.preview_point = xyz
            return MouseInteractionResult(action="excavation_vertex", message=f"Excavation vertex {len(self.excavation_vertices)} added.", metadata=self.preview_state())

        if self.mode == "block":
            if self.block_anchor is None:
                self.block_anchor = xyz
                self.preview_point = xyz
                return MouseInteractionResult(action="block_anchor", message="Block first corner set.", metadata=self.preview_state())
            bounds = self._block_bounds(self.block_anchor, xyz)
            result = self.system.create_block(bounds, role="structure")
            self.block_anchor = None
            self.preview_point = None
            return MouseInteractionResult(action="create_block", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result, "bounds": list(bounds)})

        return MouseInteractionResult(ok=False, action="unknown", message=f"Unsupported mode: {self.mode}")

    def _block_bounds(self, a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float, float, float, float]:
        xmin, xmax = sorted((float(a[0]), float(b[0])))
        zmin, zmax = sorted((float(a[2]), float(b[2])))
        # Avoid zero-thickness blocks when the user double-clicks too close.
        if xmax - xmin < 1e-6:
            xmax = xmin + 1.0
        if zmax - zmin < 1e-6:
            zmin = zmax - 1.0
        return (xmin, xmax, -self.block_half_width_y, self.block_half_width_y, zmin, zmax)

    def finish_line(self) -> MouseInteractionResult:
        self.line_anchor = None
        self.preview_point = None
        return MouseInteractionResult(action="finish_line", message="Continuous line drawing finished.", metadata=self.preview_state())

    def close_surface(self) -> MouseInteractionResult:
        if len(self.surface_vertices) < 3:
            return MouseInteractionResult(ok=False, action="close_surface", message="At least three vertices are required.")
        coords = list(self.surface_vertices)
        result = self.system.create_surface(coords, snap=self.snap)
        self.surface_vertices.clear()
        self.preview_point = None
        return MouseInteractionResult(action="create_surface", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result})

    def close_excavation_polygon(self) -> MouseInteractionResult:
        if len(self.excavation_vertices) < 3:
            return MouseInteractionResult(ok=False, action="close_excavation", message="At least three excavation vertices are required.")
        coords = list(self.excavation_vertices)
        result = self.system.split_excavation_polygon(coords)
        self.excavation_vertices.clear()
        self.preview_point = None
        return MouseInteractionResult(action="split_excavation_polygon", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result})

    def end_soil_layer_drag(self, x: float, z: float) -> MouseInteractionResult:
        if self.layer_anchor is None:
            return MouseInteractionResult(ok=False, action="end_soil_layer_drag", message="No active soil-layer split drag.")
        xyz = self._xyz(x, z)
        result = self.system.split_soil_layer_at(xyz[2])
        self.layer_anchor = None
        self.preview_point = None
        return MouseInteractionResult(action="split_soil_layer", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result})

    def start_drag(self, entity_id: str, entity_type: str = "point") -> MouseInteractionResult:
        if entity_type != "point":
            return MouseInteractionResult(ok=False, action="start_drag", message="Only points can be dragged in this editor mode.")
        ref = self.system.make_selection_ref(entity_id, entity_type)
        if ref is None:
            return MouseInteractionResult(ok=False, action="start_drag", message=f"Point not found: {entity_id}")
        self.system.apply_selection(ref, modifier="replace")
        self.drag_entity_id = entity_id
        return MouseInteractionResult(action="start_drag", entity_ids=[entity_id])

    def drag_to(self, x: float, z: float) -> MouseInteractionResult:
        self.preview_point = self._xyz(x, z)
        return MouseInteractionResult(action="drag_preview", metadata=self.preview_state())

    def end_drag(self, x: float, z: float) -> MouseInteractionResult:
        if not self.drag_entity_id:
            return MouseInteractionResult(ok=False, action="end_drag", message="No active point drag.")
        result = self.system.move_selected_point(*self._xyz(x, z), snap=self.snap)
        entity_id = self.drag_entity_id
        self.drag_entity_id = None
        self.preview_point = None
        return MouseInteractionResult(action="end_drag", entity_ids=[entity_id], metadata={"result": result or {}})

    def box_select(
        self,
        x1: float,
        z1: float,
        x2: float,
        z2: float,
        *,
        include_types: Iterable[str] = ("point", "edge", "surface", "block", "support", "contact_pair", "partition_feature"),
        modifier: SelectionModifier = "replace",
    ) -> MouseInteractionResult:
        xmin, xmax = sorted((float(x1), float(x2)))
        zmin, zmax = sorted((float(z1), float(z2)))
        include = set(str(t) for t in include_types)
        payload = self.system.refresh_viewport()
        refs: list[SelectionRef] = []
        for primitive in payload.get("primitives", []):
            kind = str(primitive.get("kind"))
            if kind not in include or not primitive.get("pickable", True) or not primitive.get("visible", True):
                continue
            center = self._primitive_center_xz(primitive)
            if center is None:
                continue
            cx, cz = center
            if xmin <= cx <= xmax and zmin <= cz <= zmax:
                ref = self.system.make_selection_ref(str(primitive.get("entity_id")), kind)
                if ref is not None:
                    refs.append(ref)
        self.system.apply_selection_many(refs, modifier=modifier)
        return MouseInteractionResult(action="box_select", entity_ids=[ref.entity_id for ref in refs], metadata={"count": len(refs), "modifier": modifier})

    def _primitive_center_xz(self, primitive: dict[str, Any]) -> tuple[float, float] | None:
        meta = primitive.get("metadata", {}) or {}
        if primitive.get("kind") == "point":
            return (float(meta.get("x", 0.0)), float(meta.get("z", 0.0)))
        bounds = primitive.get("bounds")
        if isinstance(bounds, (list, tuple)) and len(bounds) >= 6:
            return ((float(bounds[0]) + float(bounds[1])) * 0.5, (float(bounds[4]) + float(bounds[5])) * 0.5)
        points = meta.get("points") or []
        if points:
            xs = [float(p[0]) for p in points if len(p) >= 3]
            zs = [float(p[2]) for p in points if len(p) >= 3]
            if xs and zs:
                return (sum(xs) / len(xs), sum(zs) / len(zs))
        return None

    def context_actions(self, *, entity_id: str | None = None, entity_type: str | None = None) -> list[dict[str, Any]]:
        selected = self.system.document.selection.items
        if entity_id and entity_type and not selected:
            ref = self.system.make_selection_ref(entity_id, entity_type)
            selected = [] if ref is None else [ref]
        entity_types = {ref.entity_type for ref in selected}
        actions: list[dict[str, Any]] = [
            {"id": "clear_selection", "label": "Clear selection", "enabled": True},
        ]
        if not selected:
            actions.extend([
                {"id": "tool_select", "label": "Switch to Select", "enabled": True},
                {"id": "tool_point", "label": "Create point here", "enabled": True},
                {"id": "tool_soil_layer", "label": "Drag horizontal soil layer split", "enabled": True},
                {"id": "tool_excavation", "label": "Draw excavation polygon", "enabled": True},
                {"id": "tool_wall", "label": "Draw wall axis", "enabled": True},
                {"id": "tool_strut", "label": "Draw strut axis", "enabled": True},
            ])
            return actions
        if "partition_feature" in entity_types:
            actions.extend([
                {"id": "drag_update_feature", "label": "Drag-update selected feature", "enabled": True},
                {"id": "rebuild_interfaces", "label": "Rebuild contact/interface candidates", "enabled": True},
            ])
        if "support" in entity_types:
            actions.extend([
                {"id": "edit_support_parameters", "label": "Edit support parameters", "enabled": True},
                {"id": "drag_update_support", "label": "Drag-update support endpoint", "enabled": True},
            ])
        if "block" in entity_types:
            actions.extend([
                {"id": "activate_selected", "label": "Activate selected blocks in current stage", "enabled": True},
                {"id": "deactivate_selected", "label": "Deactivate selected blocks in current stage", "enabled": True},
                {"id": "hide_selected", "label": "Hide selected blocks", "enabled": True},
                {"id": "show_selected", "label": "Show selected blocks", "enabled": True},
                {"id": "assign_manual_material", "label": "Assign material: manual_material", "enabled": True},
                {"id": "rebuild_interfaces", "label": "Rebuild contact/interface candidates", "enabled": True},
                {"id": "accept_first_interface", "label": "Accept first pending interface", "enabled": True},
            ])
        if entity_types.intersection({"point", "edge", "surface", "block"}):
            actions.append({"id": "delete_selected", "label": "Delete selected geometry", "enabled": True})
        actions.append({"id": "cancel_pending", "label": "Cancel pending draw operation", "enabled": True})
        return actions

    def invoke_context_action(self, action_id: str, *, stage_id: str | None = None) -> MouseInteractionResult:
        if action_id == "clear_selection":
            self.system.clear_selection()
            return MouseInteractionResult(action=action_id)
        if action_id == "cancel_pending":
            return self.cancel()
        if action_id.startswith("tool_"):
            return self.set_mode(action_id.replace("tool_", ""))
        if action_id in {"activate_selected", "deactivate_selected"}:
            active = action_id == "activate_selected"
            results = self.system.set_selected_blocks_activation(stage_id or self.system.document.stages.active_stage_id or "", active)
            return MouseInteractionResult(action=action_id, metadata={"results": results})
        if action_id in {"hide_selected", "show_selected"}:
            visible = action_id == "show_selected"
            results = self.system.set_selected_blocks_visibility(visible)
            return MouseInteractionResult(action=action_id, metadata={"results": results})
        if action_id == "assign_manual_material":
            results = []
            for ref in self.system.document.selection.by_type("block"):
                results.append(self.system.assign_material(ref.entity_id, "manual_material"))
            return MouseInteractionResult(action=action_id, metadata={"results": results})
        if action_id == "drag_update_feature":
            return MouseInteractionResult(action=action_id, metadata={"preview": self.preview_state(), "message": "Use end_parametric_drag(x, z) to commit the feature drag."})
        if action_id == "edit_support_parameters":
            return MouseInteractionResult(action=action_id, metadata={"message": "Use update_selected_support_parameters(...) on the system to commit parameter edits."})
        if action_id == "drag_update_support":
            return MouseInteractionResult(action=action_id, metadata={"message": "Use drag_selected_support_endpoint_to(endpoint, x, z) to commit endpoint drag."})
        if action_id == "rebuild_interfaces":
            return MouseInteractionResult(action=action_id, metadata={"result": self.system.rebuild_interface_candidates()})
        if action_id == "accept_first_interface":
            return MouseInteractionResult(action=action_id, metadata={"result": self.system.accept_first_interface_candidate() or {}})
        if action_id == "delete_selected":
            results = self.system.delete_selected_geometry_entities()
            return MouseInteractionResult(action=action_id, metadata={"results": results})
        return MouseInteractionResult(ok=False, action=action_id, message=f"Unknown context action: {action_id}")

    def end_parametric_drag(self, x: float, z: float) -> MouseInteractionResult:
        """Commit a drag update for the currently selected parametric feature."""
        ref = self.system.document.selection.active
        if ref is None:
            return MouseInteractionResult(ok=False, action="parametric_drag", message="No selected feature or generated block.")
        if ref.entity_type == "partition_feature":
            feature = self.system.document.geometry.partition_features.get(ref.entity_id)
            if feature is None:
                return MouseInteractionResult(ok=False, action="parametric_drag", message="Selected feature no longer exists.")
            if feature.type == "horizontal_layer":
                result = self.system.update_soil_layer_feature(ref.entity_id, self._xyz(x, z)[2])
                return MouseInteractionResult(action="update_soil_layer_feature", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result})
            if feature.type == "excavation_surface":
                vertices = feature.parameters.get("polygon_vertices") or []
                if not vertices:
                    return MouseInteractionResult(ok=False, action="parametric_drag", message="Excavation feature has no polygon vertices to translate.")
                old_center_x = sum(float(v[0]) for v in vertices) / len(vertices)
                old_center_z = sum(float(v[2]) for v in vertices) / len(vertices)
                dx = float(x) - old_center_x
                dz = float(z) - old_center_z
                moved = [(float(v[0]) + dx, float(v[1]) if len(v) > 1 else self.default_y, float(v[2]) + dz) for v in vertices]
                result = self.system.update_excavation_feature(ref.entity_id, moved)
                return MouseInteractionResult(action="update_excavation_feature", entity_ids=list(result.get("affected_entities", []) or []), metadata={"result": result})
        if ref.entity_type == "block":
            fid = self.system.feature_id_for_selection()
            if fid:
                self.system.select_entity(fid, "partition_feature")
                return self.end_parametric_drag(x, z)
        return MouseInteractionResult(ok=False, action="parametric_drag", message=f"Selection is not an editable parametric feature: {ref.entity_type}")

    def drag_selected_support_endpoint_to(self, endpoint: str, x: float, z: float) -> MouseInteractionResult:
        ref = self.system.document.selection.active
        if ref is None or ref.entity_type != "support":
            return MouseInteractionResult(ok=False, action="drag_support_endpoint", message="No support selected.")
        support = self.system.document.supports.get(ref.entity_id, {})
        start = tuple(float(v) for v in support.get("start", (0.0, self.default_y, 0.0)))
        end = tuple(float(v) for v in support.get("end", (0.0, self.default_y, 0.0)))
        xyz = self._xyz(x, z)
        if endpoint.lower().startswith("start"):
            start = xyz
        else:
            end = xyz
        result = self.system.update_support_parameters(ref.entity_id, start=start, end=end)
        return MouseInteractionResult(action="drag_support_endpoint", entity_ids=[ref.entity_id], metadata={"result": result, "endpoint": endpoint})

    def preview_state(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "line_anchor": list(self.line_anchor) if self.line_anchor else None,
            "block_anchor": list(self.block_anchor) if self.block_anchor else None,
            "surface_vertices": [list(p) for p in self.surface_vertices],
            "excavation_vertices": [list(p) for p in self.excavation_vertices],
            "support_anchor": list(self.support_anchor) if self.support_anchor else None,
            "layer_anchor": list(self.layer_anchor) if self.layer_anchor else None,
            "drag_entity_id": self.drag_entity_id,
            "preview_point": list(self.preview_point) if self.preview_point else None,
            "snap": bool(self.snap),
        }


__all__ = ["GeometryMouseController", "MouseInteractionResult", "MouseToolMode", "SelectionModifier"]
