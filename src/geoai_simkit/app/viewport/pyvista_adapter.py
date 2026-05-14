from __future__ import annotations

"""PyVista/Qt adapter for phase-aware interactive viewport tools.

The adapter is import-safe in headless tests.  A real ``pyvistaqt.QtInteractor``
can bind it to VTK mouse/keyboard observers at runtime.  Picking is actor-aware
and, when VTK cell metadata is available, cell-aware so CAD face/edge topology
records can be selected directly from the viewport.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from geoai_simkit.app.tools.base import ToolEvent
from geoai_simkit.app.viewport.viewport_state import ScenePrimitive, ViewportState
from geoai_simkit.app.viewport.workplane import WorkPlaneController
from geoai_simkit.app.viewport.snap_controller import SnapController
from geoai_simkit.app.viewport.opengl_context_guard import OpenGLContextGuardState, widget_exposure_state
from geoai_simkit.contracts.viewport import ViewportPickResult, ViewportPreviewGeometry, ViewportToolOutput, ViewportSelectionItem, ViewportSelectionSet


def _bounds_center(bounds: tuple[float, float, float, float, float, float]) -> tuple[float, float, float]:
    return ((bounds[0] + bounds[1]) * 0.5, (bounds[2] + bounds[3]) * 0.5, (bounds[4] + bounds[5]) * 0.5)


def _face_points_from_bounds(bounds: tuple[float, float, float, float, float, float]) -> list[tuple[float, float, float]]:
    x0, x1, y0, y1, z0, z1 = [float(v) for v in bounds]
    spans = [abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)]
    axis = min(range(3), key=lambda i: spans[i])
    if axis == 0:
        x = (x0 + x1) * 0.5
        return [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]
    if axis == 1:
        y = (y0 + y1) * 0.5
        return [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]
    z = (z0 + z1) * 0.5
    return [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]


def _edge_points_from_bounds(bounds: tuple[float, float, float, float, float, float]) -> list[tuple[float, float, float]]:
    x0, x1, y0, y1, z0, z1 = [float(v) for v in bounds]
    spans = [abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)]
    axis = max(range(3), key=lambda i: spans[i])
    c = _bounds_center(bounds)
    if axis == 0:
        return [(x0, c[1], c[2]), (x1, c[1], c[2])]
    if axis == 1:
        return [(c[0], y0, c[2]), (c[0], y1, c[2])]
    return [(c[0], c[1], z0), (c[0], c[1], z1)]


@dataclass(slots=True)
class PyVistaViewportAdapter:
    plotter: Any
    runtime: Any | None = None
    workplane: WorkPlaneController = field(default_factory=WorkPlaneController)
    refresh_callback: Callable[[], None] | None = None
    status_callback: Callable[[str], None] | None = None
    selection_callback: Callable[[Any | None], None] | None = None
    context_menu_callback: Callable[[ViewportPickResult], bool | None] | None = None
    actor_entity_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    preview_names: list[str] = field(default_factory=list)
    hover_names: list[str] = field(default_factory=list)
    cursor_names: list[str] = field(default_factory=list)
    constraint_names: list[str] = field(default_factory=list)
    selection_names: list[str] = field(default_factory=list)
    handle_names: list[str] = field(default_factory=list)
    mesh_names: list[str] = field(default_factory=list)
    viewport_state: ViewportState | None = None
    snap: SnapController = field(default_factory=SnapController)
    event_bound: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    rendering_suspended: bool = False
    opengl_guard: OpenGLContextGuardState = field(default_factory=OpenGLContextGuardState)

    def bind_context_menu_callback(self, callback: Callable[[ViewportPickResult], bool | None] | None) -> None:
        self.context_menu_callback = callback

    def bind_runtime(self, runtime: Any) -> None:
        self.runtime = runtime

    def bind_viewport_state(self, state: ViewportState | None) -> None:
        self.viewport_state = state

    def _actor_keys(self, actor: Any) -> list[str]:
        keys: list[str] = []
        if actor is None:
            return keys
        keys.append(str(id(actor)))
        try:
            keys.append(str(actor))
        except Exception:
            pass
        for attr in ("memory_address", "address"):
            try:
                value = getattr(actor, attr, None)
                if callable(value):
                    value = value()
                if value:
                    keys.append(str(value))
            except Exception:
                pass
        try:
            fn = getattr(actor, "GetAddressAsString", None)
            if fn is not None:
                keys.append(str(fn("")))
        except Exception:
            pass
        for attr in ("actor", "prop", "_actor"):
            try:
                child = getattr(actor, attr, None)
                if child is not None and child is not actor:
                    keys.extend(self._actor_keys(child))
            except Exception:
                pass
        return list(dict.fromkeys(keys))

    def _register_actor(self, actor: Any, info: dict[str, Any]) -> None:
        for key in self._actor_keys(actor):
            self.actor_entity_map[key] = dict(info)
        try:
            setattr(actor, "_geoai_entity_info", dict(info))
        except Exception:
            pass

    def _actor_info(self, actor: Any) -> dict[str, Any]:
        if actor is None:
            return {}
        info = getattr(actor, "_geoai_entity_info", None) or {}
        for key in self._actor_keys(actor):
            info = info or self.actor_entity_map.get(key) or {}
            if info:
                break
        return dict(info or {})

    def bind_events(self) -> None:
        if self.event_bound:
            return
        interactor = getattr(self.plotter, "iren", None) or getattr(self.plotter, "interactor", None)
        add_observer = getattr(interactor, "add_observer", None) or getattr(interactor, "AddObserver", None)
        if add_observer is None:
            self._status("Viewport interactor does not expose observer binding; toolbar tools still work through programmatic events.")
            return
        try:
            add_observer("LeftButtonPressEvent", lambda *_: self.handle_mouse_press("left"))
            add_observer("RightButtonPressEvent", lambda *_: self.handle_mouse_press("right"))
            add_observer("MouseMoveEvent", lambda *_: self.handle_mouse_move())
            add_observer("LeftButtonReleaseEvent", lambda *_: self.handle_mouse_release("left"))
            add_observer("RightButtonReleaseEvent", lambda *_: self.handle_mouse_release("right"))
            add_observer("KeyPressEvent", lambda *_: self.handle_key_press())
            self.event_bound = True
        except Exception as exc:  # pragma: no cover
            self._status(f"Viewport event binding skipped: {exc}")

    def _status(self, message: str) -> None:
        if self.status_callback is not None:
            self.status_callback(message)

    def _qt_widget_is_renderable(self) -> bool:
        exposure = widget_exposure_state(self.plotter)
        self.metadata["opengl_exposure_state"] = exposure
        return bool(exposure.get("renderable", True))

    def suspend_rendering(self, reason: str = "") -> None:
        self.rendering_suspended = True
        self.opengl_guard.suspended = True
        self.opengl_guard.last_reason = reason or "rendering_suspended"
        self.metadata["opengl_guard"] = self.opengl_guard.to_dict()

    def resume_rendering(self) -> None:
        self.rendering_suspended = False
        self.opengl_guard.suspended = False
        self.opengl_guard.last_reason = "rendering_resumed"
        self.metadata["opengl_guard"] = self.opengl_guard.to_dict()

    def safe_render(self, *, reason: str = "") -> bool:
        self.opengl_guard.render_attempts += 1
        if self.rendering_suspended or self.opengl_guard.suspended:
            self.opengl_guard.skipped_renders += 1
            self.opengl_guard.last_reason = reason or "rendering_suspended"
            self.metadata["opengl_guard"] = self.opengl_guard.to_dict()
            return False
        if not self._qt_widget_is_renderable():
            self.opengl_guard.skipped_renders += 1
            exposure = dict(self.metadata.get("opengl_exposure_state", {}) or {})
            skip_reason = str(exposure.get("reason") or reason or "context_not_renderable")
            self.opengl_guard.last_reason = skip_reason
            self.metadata["opengl_guard"] = self.opengl_guard.to_dict()
            self._status(f"Render skipped because the Qt/VTK context is not renderable; reason={skip_reason}")
            return False
        try:
            self.plotter.render()
            self.opengl_guard.last_reason = reason or "rendered"
            self.metadata["opengl_guard"] = self.opengl_guard.to_dict()
            return True
        except Exception as exc:
            message = f"Render skipped after VTK/OpenGL context error; reason={reason}; {type(exc).__name__}: {exc}"
            lower = message.lower()
            if "wglmakecurrent" in lower or "makecurrent" in lower or "opengl" in lower or "renderwindow" in lower:
                self.opengl_guard.suspended = True
                self.rendering_suspended = True
                self.opengl_guard.hints = [
                    "关闭并重新打开 3D 视口或重启 GUI。",
                    "在 RDP/显卡驱动不稳定时设置 GEOAI_SIMKIT_QT_OPENGL=software。",
                    "如需继续配置模型，设置 GEOAI_SIMKIT_DISABLE_PYVISTA=1 启动 Qt-only 工作台。",
                ]
            self.opengl_guard.failed_renders += 1
            self.opengl_guard.last_error = message
            self.opengl_guard.last_reason = reason or "render_failed"
            self.metadata["last_render_error"] = message
            self.metadata["opengl_guard"] = self.opengl_guard.to_dict()
            self._status(message)
            return False

    def event_position(self) -> tuple[float, float]:
        interactor = getattr(self.plotter, "iren", None) or getattr(self.plotter, "interactor", None)
        for obj in (interactor, getattr(interactor, "interactor", None)):
            if obj is None:
                continue
            getter = getattr(obj, "get_event_position", None) or getattr(obj, "GetEventPosition", None)
            if getter is not None:
                try:
                    x, y = getter()
                    return (float(x), float(y))
                except Exception:
                    pass
        return (0.0, 0.0)

    def current_modifiers(self) -> tuple[str, ...]:
        mods: list[str] = []
        try:
            from PySide6 import QtCore, QtWidgets  # type: ignore
            value = QtWidgets.QApplication.keyboardModifiers()
            if value & QtCore.Qt.KeyboardModifier.ShiftModifier:
                mods.append("shift")
            if value & QtCore.Qt.KeyboardModifier.ControlModifier:
                mods.append("ctrl")
            if value & QtCore.Qt.KeyboardModifier.AltModifier:
                mods.append("alt")
            if value & QtCore.Qt.KeyboardModifier.MetaModifier:
                mods.append("meta")
        except Exception:
            pass
        return tuple(mods)

    def _renderer(self) -> Any | None:
        for attr in ("renderer", "ren"):
            value = getattr(self.plotter, attr, None)
            if value is not None:
                return value
        try:
            renderers = getattr(self.plotter, "renderers", None)
            if renderers is not None and len(renderers) > 0:
                return renderers[0]
        except Exception:
            pass
        return None

    def _picked_world_from_plotter(self, sx: float | None = None, sy: float | None = None) -> tuple[tuple[float, float, float] | None, Any | None, int | None, tuple[float, float, float] | None]:
        if sx is not None and sy is not None:
            try:
                import vtk  # type: ignore
                renderer = self._renderer()
                if renderer is not None:
                    picker = vtk.vtkCellPicker()
                    picker.SetTolerance(0.0008)
                    if picker.Pick(float(sx), float(sy), 0.0, renderer):
                        pos = picker.GetPickPosition()
                        actor = picker.GetActor()
                        cell_id = int(picker.GetCellId()) if picker.GetCellId() is not None else None
                        normal = None
                        try:
                            n = picker.GetPickNormal()
                            if n is not None and len(n) >= 3:
                                normal = (float(n[0]), float(n[1]), float(n[2]))
                        except Exception:
                            normal = None
                        if pos is not None and len(pos) >= 3:
                            return (float(pos[0]), float(pos[1]), float(pos[2])), actor, cell_id, normal
                    prop = vtk.vtkPropPicker()
                    if prop.Pick(float(sx), float(sy), 0.0, renderer):
                        pos = prop.GetPickPosition()
                        actor = prop.GetActor()
                        if pos is not None and len(pos) >= 3:
                            return (float(pos[0]), float(pos[1]), float(pos[2])), actor, None, None
            except Exception:
                pass
        for name in ("pick_mouse_position", "get_pick_position"):
            fn = getattr(self.plotter, name, None)
            if fn is None:
                continue
            try:
                value = fn()
                if value is not None and len(value) >= 3:
                    picker = getattr(self.plotter, "picker", None)
                    actor = getattr(picker, "GetActor", lambda: None)()
                    cell_id = getattr(picker, "GetCellId", lambda: None)()
                    return tuple(float(v) for v in value[:3]), actor, None if cell_id in {None, -1} else int(cell_id), None  # type: ignore[index, return-value]
            except Exception:
                continue
        picker = getattr(self.plotter, "picker", None)
        getter = getattr(picker, "GetPickPosition", None)
        if getter is not None:
            try:
                value = getter()
                if value is not None and len(value) >= 3:
                    actor = getattr(picker, "GetActor", lambda: None)()
                    cell_id = getattr(picker, "GetCellId", lambda: None)()
                    return tuple(float(v) for v in value[:3]), actor, None if cell_id in {None, -1} else int(cell_id), None  # type: ignore[index, return-value]
            except Exception:
                pass
        return None, None, None, None

    def _cell_array_value(self, actor: Any, cell_id: int | None, name: str) -> str:
        if actor is None or cell_id is None or cell_id < 0:
            return ""
        try:
            mapper = actor.GetMapper()
            data = mapper.GetInput()
            arr = data.GetCellData().GetAbstractArray(name)
            if arr is None:
                arr = data.GetCellData().GetArray(name)
            if arr is None or cell_id >= arr.GetNumberOfTuples():
                return ""
            getter = getattr(arr, "GetValue", None) or getattr(arr, "GetVariantValue", None)
            if getter is None:
                return ""
            return str(getter(int(cell_id)))
        except Exception:
            return ""

    def _cell_info(self, actor: Any, cell_id: int | None) -> dict[str, Any]:
        entity_id = self._cell_array_value(actor, cell_id, "geoai_entity_id")
        kind = self._cell_array_value(actor, cell_id, "geoai_kind")
        topology_id = self._cell_array_value(actor, cell_id, "geoai_topology_id")
        primitive_id = self._cell_array_value(actor, cell_id, "geoai_primitive_id")
        source_entity_id = self._cell_array_value(actor, cell_id, "geoai_source_entity_id")
        layer_value = self._cell_array_value(actor, cell_id, "geoai_layer_value")
        if not any((entity_id, kind, topology_id, primitive_id, source_entity_id, layer_value)):
            return {}
        return {
            "entity_id": topology_id or entity_id,
            "kind": kind or "empty",
            "topology_id": topology_id,
            "primitive_id": primitive_id,
            "source_entity_id": source_entity_id,
            "layer_value": layer_value,
            "cell_id": cell_id,
        }

    def pick(self, x: float | None = None, y: float | None = None, modifiers: tuple[str, ...] = ()) -> ViewportPickResult:
        sx, sy = self.event_position() if x is None or y is None else (float(x), float(y))
        picked_world, actor, cell_id, normal = self._picked_world_from_plotter(sx, sy)
        if picked_world is None:
            world = self.workplane.project((float(sx), 0.0, float(sy)))
            pick_mode = "workplane_fallback"
        else:
            world = tuple(float(v) for v in picked_world)
            pick_mode = "vtk_cell" if cell_id is not None and cell_id >= 0 else "vtk_actor"
        snap_result = self.snap.snap(world, self.viewport_state, modifiers=modifiers)
        world = snap_result.point

        if actor is None:
            try:
                actor = getattr(getattr(self.plotter, "picker", None), "GetActor", lambda: None)()
            except Exception:
                actor = None
        actor_info = self._actor_info(actor)
        cell_info = self._cell_info(actor, cell_id)
        info = {**actor_info, **cell_info} if cell_info else actor_info
        entity_id = str(info.get("entity_id") or "")
        entity_kind = str(info.get("kind") or "empty")
        primitive_id = str(info.get("primitive_id") or actor_info.get("primitive_id") or "")
        if entity_id and entity_kind == "empty":
            entity_kind = "block"
        metadata = {
            "screen": [sx, sy],
            "workplane": self.workplane.mode,
            "snap": snap_result.to_dict(),
            "pick_mode": pick_mode,
            "cell_id": -1 if cell_id is None else int(cell_id),
            **dict(actor_info),
            **dict(cell_info),
        }
        if normal is not None:
            metadata["normal"] = list(normal)
        return ViewportPickResult(kind=entity_kind, entity_id=entity_id, primitive_id=primitive_id, world=world, normal=normal, metadata=metadata)  # type: ignore[arg-type]

    def build_tool_event(self, *, button: str = "none", x: float | None = None, y: float | None = None, modifiers: tuple[str, ...] = ()) -> ToolEvent:
        if not modifiers:
            modifiers = self.current_modifiers()
        sx, sy = self.event_position() if x is None or y is None else (float(x), float(y))
        pick = self.pick(sx, sy, modifiers=modifiers)
        return ToolEvent(x=float(sx), y=float(sy), world=pick.world, button=button, modifiers=modifiers, picked_entity_id=pick.entity_id or None, metadata={"picked_kind": pick.kind, "primitive_id": pick.primitive_id, **dict(pick.metadata)})  # type: ignore[arg-type]

    def handle_mouse_press(self, button: str = "left") -> ViewportToolOutput | None:
        if self.runtime is None:
            return None
        if button == "right" and self.context_menu_callback is not None:
            sx, sy = self.event_position()
            pick = self.pick(sx, sy, modifiers=self.current_modifiers())
            active = str(getattr(self.runtime, "active_tool_key", "") or "")
            if active == "surface":
                try:
                    meta = dict(pick.metadata or {})
                    meta.update({"context_menu_kind": "surface_tool_completion", "active_tool": active})
                    pick = ViewportPickResult(kind=pick.kind, entity_id=pick.entity_id, primitive_id=pick.primitive_id, world=pick.world, normal=pick.normal, distance=pick.distance, metadata=meta)
                    handled = bool(self.context_menu_callback(pick))
                except Exception as exc:  # pragma: no cover
                    self._status(f"Surface completion menu failed: {type(exc).__name__}: {exc}")
                    handled = False
                if handled:
                    return ViewportToolOutput(kind="message", tool=active, message="Surface completion menu opened")
            if active in {"point", "line", "block_box"}:
                try:
                    meta = dict(pick.metadata or {})
                    meta.update({"context_menu_kind": "creation_constraint_menu", "active_tool": active})
                    pick = ViewportPickResult(kind=pick.kind, entity_id=pick.entity_id, primitive_id=pick.primitive_id, world=pick.world, normal=pick.normal, distance=pick.distance, metadata=meta)
                    handled = bool(self.context_menu_callback(pick))
                except Exception as exc:  # pragma: no cover
                    self._status(f"Creation constraint menu failed: {type(exc).__name__}: {exc}")
                    handled = False
                if handled:
                    return ViewportToolOutput(kind="message", tool=active, message="Creation constraint menu opened")
            # Selection and transform modes reserve right click for engineering actions.
            if active in {"select", "drag_move", "move", "copy", "rotate", "scale"}:
                try:
                    handled = bool(self.context_menu_callback(pick))
                except Exception as exc:  # pragma: no cover
                    self._status(f"Context menu failed: {type(exc).__name__}: {exc}")
                    handled = False
                if handled:
                    return ViewportToolOutput(kind="message", tool=active or "select", message="Context menu opened")
        output = self.runtime.mouse_press(self.build_tool_event(button=button))
        self.apply_tool_output(output)
        return output

    def handle_mouse_move(self) -> ViewportToolOutput | None:
        if self.runtime is None:
            return None
        active = str(getattr(self.runtime, "active_tool_key", "") or "")
        if active in {"select", "drag_move", "move", "copy", "rotate", "scale"}:
            sx, sy = self.event_position()
            self.render_hover_pick(self.pick(sx, sy, modifiers=self.current_modifiers()))
        output = self.runtime.mouse_move(self.build_tool_event(button="none"))
        self.apply_tool_output(output)
        return output

    def clear_hover_overlay(self) -> None:
        for name in list(self.hover_names):
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass
        self.hover_names.clear()

    def render_hover_pick(self, pick: ViewportPickResult | None) -> None:
        self.clear_hover_overlay()
        if pick is None or not pick.hit or self.viewport_state is None:
            return
        primitive = next((p for p in self.viewport_state.primitives.values() if p.entity_id == pick.entity_id or p.id == pick.primitive_id), None)
        if primitive is None:
            source = str(dict(pick.metadata or {}).get("source_entity_id") or "")
            if source:
                primitive = next((p for p in self.viewport_state.primitives.values() if p.entity_id == source), None)
        if primitive is None or primitive.bounds is None:
            return
        try:
            import numpy as np
            import pyvista as pv
        except Exception:
            return
        name = f"hover-{primitive.id}"
        try:
            if primitive.kind in {"surface", "face"}:
                pts = _face_points_from_bounds(tuple(float(v) for v in primitive.bounds))
                poly = pv.PolyData(np.asarray(pts, dtype=float))
                poly.faces = np.asarray([len(pts), *range(len(pts))], dtype=np.int64)
                self.plotter.add_mesh(poly, style="wireframe", line_width=3, name=name)
            elif primitive.kind in {"edge", "curve", "line"}:
                pts = _edge_points_from_bounds(tuple(float(v) for v in primitive.bounds))
                poly = pv.PolyData(np.asarray(pts, dtype=float))
                poly.lines = np.asarray([2, 0, 1], dtype=np.int64)
                self.plotter.add_mesh(poly, line_width=5, name=name)
            elif primitive.kind in {"point"}:
                x0, _x1, y0, _y1, z0, _z1 = primitive.bounds
                poly = pv.PolyData(np.asarray([[x0, y0, z0]], dtype=float))
                self.plotter.add_mesh(poly, render_points_as_spheres=True, point_size=16, name=name)
            else:
                box = pv.Box(bounds=tuple(float(v) for v in primitive.bounds))
                self.plotter.add_mesh(box, style="wireframe", line_width=3, name=name)
            self.hover_names.append(name)
            self._status(f"Hover: {pick.kind} · {pick.entity_id}")
            self.safe_render(reason="hover_overlay")
        except Exception:
            pass

    def handle_mouse_release(self, button: str = "left") -> ViewportToolOutput | None:
        if self.runtime is None:
            return None
        output = self.runtime.mouse_release(self.build_tool_event(button=button))
        self.apply_tool_output(output)
        return output

    def handle_key_press(self, key: str | None = None) -> ViewportToolOutput | None:
        if self.runtime is None:
            return None
        key_text = key
        if key_text is None:
            interactor = getattr(self.plotter, "iren", None) or getattr(self.plotter, "interactor", None)
            getter = getattr(interactor, "get_key_sym", None) or getattr(interactor, "GetKeySym", None)
            try:
                key_text = str(getter()) if getter is not None else ""
            except Exception:
                key_text = ""
        output = self.runtime.key_press(str(key_text or ""))
        self.apply_tool_output(output)
        return output

    def clear_preview(self) -> None:
        for name in list(self.preview_names):
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass
        self.preview_names.clear()
        self.clear_cursor_overlay()

    def clear_constraint_overlay(self) -> None:
        for name in list(self.constraint_names):
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass
        self.constraint_names.clear()

    def _as_point3(self, value: Any) -> tuple[float, float, float] | None:
        try:
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                return (float(value[0]), float(value[1]), float(value[2]))
        except Exception:
            return None
        return None

    def render_constraint_lock_state(self, lock: dict[str, Any] | None = None) -> None:
        self.clear_constraint_overlay()
        lock_data = dict(lock or {})
        if not lock_data.get("enabled"):
            return
        try:
            import numpy as np
            import pyvista as pv
        except Exception:
            return
        spacing = max(float(getattr(self.snap, "spacing", 1.0) or 1.0), 0.01)
        names: list[str] = []
        try:
            start = self._as_point3(lock_data.get("start"))
            end = self._as_point3(lock_data.get("end"))
            anchor = self._as_point3(lock_data.get("anchor"))
            normal = self._as_point3(lock_data.get("normal"))
            mode = str(lock_data.get("mode") or "")
            label = str(lock_data.get("label") or mode or "约束")
            if start is not None and end is not None:
                edge_name = "constraint-locked-edge-highlight"
                poly = pv.PolyData(np.asarray([start, end], dtype=float))
                poly.lines = np.asarray([2, 0, 1], dtype=np.int64)
                self.plotter.add_mesh(poly, line_width=8, name=edge_name)
                names.append(edge_name)
                mid = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5, (start[2] + end[2]) * 0.5)
                try:
                    lbl = "constraint-locked-edge-label"
                    self.plotter.add_point_labels([mid], [f"锁定：{label}"], point_size=0, font_size=11, name=lbl)
                    names.append(lbl)
                except Exception:
                    pass
            if anchor is not None and normal is not None:
                direction = np.asarray(normal, dtype=float)
                norm = float(np.linalg.norm(direction))
                if norm <= 1.0e-12:
                    direction = np.asarray([0.0, 0.0, 1.0], dtype=float)
                    norm = 1.0
                direction = direction / norm
                arrow_name = "constraint-locked-normal-arrow"
                try:
                    arrow = pv.Arrow(start=anchor, direction=tuple(direction), scale=max(spacing * 1.5, 0.5))
                    self.plotter.add_mesh(arrow, name=arrow_name)
                    names.append(arrow_name)
                except Exception:
                    line_end = tuple(float(anchor[i] + direction[i] * max(spacing * 1.5, 0.5)) for i in range(3))
                    poly = pv.PolyData(np.asarray([anchor, line_end], dtype=float))
                    poly.lines = np.asarray([2, 0, 1], dtype=np.int64)
                    self.plotter.add_mesh(poly, line_width=6, name=arrow_name)
                    names.append(arrow_name)
                try:
                    lbl = "constraint-locked-normal-label"
                    self.plotter.add_point_labels([anchor], [f"锁定：{label}"], point_size=0, font_size=11, name=lbl)
                    names.append(lbl)
                except Exception:
                    pass
            trail_raw = lock_data.get("trail") or []
            trail = [self._as_point3(row) for row in trail_raw if self._as_point3(row) is not None]
            trail = [row for row in trail if row is not None]
            if trail:
                cloud_name = "constraint-placement-trail-points"
                cloud = pv.PolyData(np.asarray(trail, dtype=float))
                self.plotter.add_mesh(cloud, render_points_as_spheres=True, point_size=14, name=cloud_name)
                names.append(cloud_name)
                if len(trail) >= 2:
                    line_name = "constraint-placement-trail-line"
                    poly = pv.PolyData(np.asarray(trail, dtype=float))
                    lines: list[int] = []
                    for idx in range(len(trail) - 1):
                        lines.extend([2, idx, idx + 1])
                    poly.lines = np.asarray(lines, dtype=np.int64)
                    self.plotter.add_mesh(poly, line_width=4, name=line_name)
                    names.append(line_name)
                try:
                    lbl = "constraint-placement-trail-label"
                    self.plotter.add_point_labels([trail[-1]], [f"连续布置：{len(trail)} 点"], point_size=0, font_size=10, name=lbl)
                    names.append(lbl)
                except Exception:
                    pass
        except Exception:
            return
        self.constraint_names.extend(names)
        self.safe_render(reason="constraint_lock_overlay")

    def render_constraint_unlock_feedback(self, feedback: dict[str, Any] | None = None) -> None:
        self.clear_constraint_overlay()
        data = dict(feedback or {})
        if not data.get("unlocked"):
            return
        try:
            import pyvista as pv
        except Exception:
            return
        old = dict(data.get("previous_lock") or {})
        anchor = self._as_point3(old.get("anchor"))
        if anchor is None:
            start = self._as_point3(old.get("start")); end = self._as_point3(old.get("end"))
            if start is not None and end is not None:
                anchor = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5, (start[2] + end[2]) * 0.5)
        if anchor is None:
            return
        try:
            name = "constraint-unlock-feedback-label"
            self.plotter.add_point_labels([anchor], [str(data.get("message") or "约束锁定已解除")], point_size=0, font_size=12, name=name)
            self.constraint_names.append(name)
            marker = "constraint-unlock-feedback-marker"
            self.plotter.add_mesh(pv.Sphere(radius=max(float(getattr(self.snap, "spacing", 1.0) or 1.0) * 0.18, 0.06), center=anchor), name=marker)
            self.constraint_names.append(marker)
            self.safe_render(reason="constraint_unlock_feedback")
        except Exception:
            return

    def clear_cursor_overlay(self) -> None:
        for name in list(self.cursor_names):
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass
        self.cursor_names.clear()

    def _render_cursor_affordances(self, preview: ViewportPreviewGeometry, points: list[tuple[float, float, float]]) -> None:
        metadata = dict(getattr(preview, "metadata", {}) or {})
        if not metadata:
            return
        try:
            import numpy as np
            import pyvista as pv
        except Exception:
            return
        point_raw = metadata.get("snap_point") or metadata.get("crosshair_world") or (list(points[-1]) if points else None)
        if not isinstance(point_raw, (list, tuple)) or len(point_raw) < 3:
            return
        p = tuple(float(v) for v in point_raw[:3])
        spacing = max(float(getattr(self.snap, "spacing", 1.0) or 1.0), 0.01)
        size = max(spacing * 0.25, 0.08)
        names: list[str] = []
        try:
            if bool(metadata.get("screen_space_crosshair", False)):
                axes = [((p[0] - size, p[1], p[2]), (p[0] + size, p[1], p[2])), ((p[0], p[1] - size, p[2]), (p[0], p[1] + size, p[2])), ((p[0], p[1], p[2] - size), (p[0], p[1], p[2] + size))]
                for idx, (a, b) in enumerate(axes):
                    name = f"cursor-crosshair-{idx}"
                    poly = pv.PolyData(np.asarray([a, b], dtype=float))
                    poly.lines = np.asarray([2, 0, 1], dtype=np.int64)
                    self.plotter.add_mesh(poly, line_width=2, name=name)
                    names.append(name)
            snap_mode = str(metadata.get("snap_mode") or "none")
            if bool(metadata.get("snapped")) or snap_mode not in {"", "none", "disabled"}:
                name = f"snap-point-{snap_mode}"
                radius = max(size * (0.32 if snap_mode == "grid" else 0.45), 0.04)
                self.plotter.add_mesh(pv.Sphere(radius=radius, center=p), name=name)
                names.append(name)
                label = str(metadata.get("snap_label") or snap_mode)
                if label:
                    label_name = f"snap-label-{snap_mode}"
                    try:
                        self.plotter.add_point_labels([p], [label], point_size=0, font_size=10, name=label_name)
                        names.append(label_name)
                    except Exception:
                        pass
            constraint_mode = str(metadata.get("constraint_mode") or "none")
            if bool(metadata.get("constraint_locked")) and constraint_mode not in {"", "none", "disabled"}:
                lock_raw = metadata.get("constraint_lock") or {}
                lock_label = "锁定约束"
                if isinstance(lock_raw, dict):
                    lock_label = str(lock_raw.get("label") or lock_label)
                try:
                    label_name = f"constraint-lock-label-{constraint_mode}"
                    self.plotter.add_point_labels([p], [f"锁定：{lock_label}"], point_size=0, font_size=10, name=label_name)
                    names.append(label_name)
                except Exception:
                    pass
                if isinstance(lock_raw, dict):
                    self.render_constraint_lock_state(lock_raw)
            if bool(metadata.get("constraint_active")) and constraint_mode not in {"", "none", "disabled"}:
                cp_raw = metadata.get("constraint_point") or point_raw
                if isinstance(cp_raw, (list, tuple)) and len(cp_raw) >= 3:
                    cp = tuple(float(v) for v in cp_raw[:3])
                    cname = f"constraint-point-{constraint_mode}"
                    self.plotter.add_mesh(pv.Sphere(radius=max(size * 0.52, 0.055), center=cp), name=cname)
                    names.append(cname)
                    clabel = str(metadata.get("constraint_label") or constraint_mode)
                    if clabel:
                        label_name = f"constraint-label-{constraint_mode}"
                        try:
                            self.plotter.add_point_labels([cp], [clabel], point_size=0, font_size=10, name=label_name)
                            names.append(label_name)
                        except Exception:
                            pass
        except Exception:
            return
        self.cursor_names.extend(names)

    def render_preview(self, preview: ViewportPreviewGeometry | None) -> None:
        self.clear_preview()
        if preview is None:
            return
        points = [tuple(float(v) for v in point) for point in preview.points]
        if not points:
            return
        try:
            import numpy as np
            import pyvista as pv
        except Exception as exc:  # pragma: no cover
            self._status(f"Preview unavailable: {exc}")
            return
        base = f"preview-{preview.kind}"
        try:
            if preview.kind == "point" or len(points) == 1:
                cloud = pv.PolyData(np.asarray(points, dtype=float))
                self.plotter.add_mesh(cloud, render_points_as_spheres=True, point_size=12, name=base)
                self.preview_names.append(base)
            elif preview.kind in {"line", "surface", "cut_plane"}:
                poly = pv.PolyData(np.asarray(points, dtype=float))
                if preview.kind in {"surface", "cut_plane"} and len(points) >= 3:
                    poly.faces = np.asarray([len(points), *range(len(points))], dtype=np.int64)
                    self.plotter.add_mesh(poly, show_edges=True, opacity=0.35, name=base)
                else:
                    lines: list[int] = []
                    for idx in range(len(points) - 1):
                        lines.extend([2, idx, idx + 1])
                    if preview.closed and len(points) > 2:
                        lines.extend([2, len(points) - 1, 0])
                    if lines:
                        poly.lines = np.asarray(lines, dtype=np.int64)
                    self.plotter.add_mesh(poly, line_width=3, point_size=10, render_points_as_spheres=True, name=base)
                self.preview_names.append(base)
            elif preview.kind == "box" and len(points) >= 2:
                p0, p1 = points[0], points[-1]
                bounds = (min(p0[0], p1[0]), max(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[1], p1[1]), min(p0[2], p1[2]), max(p0[2], p1[2]))
                cube = pv.Box(bounds=bounds)
                self.plotter.add_mesh(cube, show_edges=True, opacity=0.35, name=base)
                self.preview_names.append(base)
            self._render_cursor_affordances(preview, points)
            self.safe_render(reason="preview")
        except Exception as exc:  # pragma: no cover
            self._status(f"Preview render failed: {exc}")

    def apply_tool_output(self, output: ViewportToolOutput | None) -> None:
        if output is None:
            return
        if output.kind == "preview":
            self.render_preview(output.preview)
        elif output.kind == "command":
            self.clear_preview()
            self.clear_hover_overlay()
            self.clear_cursor_overlay()
            lock = dict((output.metadata or {}).get("constraint_lock") or {}) if isinstance(output.metadata, dict) else {}
            if lock.get("enabled"):
                self.render_constraint_lock_state(lock)
            if self.refresh_callback is not None:
                self.refresh_callback()
            self._auto_select_command_entity(output)
        elif output.kind == "selection":
            self.render_selection(output.selection)
            if self.selection_callback is not None:
                self.selection_callback(output.selection)
            self._status(output.message)
        elif output.kind in {"message", "error"}:
            self._status(output.message)

    def _auto_select_command_entity(self, output: ViewportToolOutput) -> None:
        metadata = dict(output.metadata or {})
        if not metadata.get("auto_select_created"):
            return
        entity_id = str(metadata.get("select_entity_id") or metadata.get("created_entity_id") or "")
        kind = str(metadata.get("select_kind") or metadata.get("created_kind") or "entity")
        if not entity_id:
            try:
                affected = list(dict(output.command_result).get("affected_entities", []) or [])
                entity_id = str(affected[0]) if affected else ""
            except Exception:
                entity_id = ""
        if not entity_id:
            return
        selection_metadata = {"selection_source": "created_by_viewport_tool", "auto_selected": True, **metadata}
        controller = None
        try:
            context = getattr(self.runtime, "context", None)
            controller = dict(getattr(context, "metadata", {}) or {}).get("selection_controller")
        except Exception:
            controller = None
        if controller is not None and hasattr(controller, "select"):
            try:
                selection = controller.select(entity_id, kind, mode="replace", metadata=selection_metadata)
            except Exception:
                selection = ViewportSelectionSet((ViewportSelectionItem(kind, entity_id, entity_id, selection_metadata),), mode="replace")  # type: ignore[arg-type]
        else:
            selection = ViewportSelectionSet((ViewportSelectionItem(kind, entity_id, entity_id, selection_metadata),), mode="replace")  # type: ignore[arg-type]
        self.render_selection(selection)
        if self.selection_callback is not None:
            self.selection_callback(selection)
        self._status(f"Created and selected {kind} · {entity_id}")

    def clear_selection_overlay(self) -> None:
        for name in list(self.selection_names):
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass
        self.selection_names.clear()
        for name in list(self.handle_names):
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass
        self.handle_names.clear()

    def _mesh_selection_bounds(self, entity_id: str, metadata: dict[str, Any]) -> tuple[float, float, float, float, float, float] | None:
        if entity_id == "imported_geology_model":
            bounds = self.metadata.get("imported_geology_bounds")
            if isinstance(bounds, (list, tuple)) and len(bounds) == 6:
                return tuple(float(v) for v in bounds)  # type: ignore[return-value]
        layer_value = str(metadata.get("layer_value") or "")
        layer_bounds = dict(self.metadata.get("imported_geology_layer_bounds", {}) or {})
        bounds = layer_bounds.get(layer_value) or layer_bounds.get(entity_id.replace("geology_layer:", ""))
        if isinstance(bounds, (list, tuple)) and len(bounds) == 6:
            return tuple(float(v) for v in bounds)  # type: ignore[return-value]
        return None

    def render_selection(self, selection: Any | None) -> None:
        self.clear_selection_overlay()
        if selection is None:
            return
        try:
            import numpy as np
            import pyvista as pv
        except Exception:
            return
        items = list(getattr(selection, "items", ()) or [])
        for idx, item in enumerate(items):
            entity_id = getattr(item, "entity_id", "")
            item_meta = dict(getattr(item, "metadata", {}) or {})
            primitive = None
            if self.viewport_state is not None:
                primitive = next((p for p in self.viewport_state.primitives.values() if p.entity_id == entity_id), None)
            if primitive is None and self.viewport_state is not None:
                source = str(item_meta.get("source_entity_id") or "")
                if source:
                    primitive = next((p for p in self.viewport_state.primitives.values() if p.entity_id == source), None)
            mesh_bounds = self._mesh_selection_bounds(str(entity_id), item_meta) if primitive is None else None
            if primitive is None and mesh_bounds is None:
                continue
            name = f"selection-{idx}-{entity_id}"
            try:
                if primitive is None:
                    box = pv.Box(bounds=mesh_bounds)
                    self.plotter.add_mesh(box, style="wireframe", line_width=6, name=name, lighting=False)
                    self.selection_names.append(name)
                    b = tuple(float(v) for v in mesh_bounds)
                    cx, cy, cz = _bounds_center(b)
                    extent = max(max(b[1] - b[0], b[3] - b[2], b[5] - b[4]), 1.0)
                    center_name = f"edit-handle-{idx}-center-{entity_id}"
                    actor = self.plotter.add_mesh(pv.Sphere(radius=max(extent * 0.025, 0.08), center=(cx, cy, cz)), name=center_name, lighting=False)
                    self.handle_names.append(center_name)
                    self._register_actor(actor, {"entity_id": entity_id, "kind": str(getattr(item, "kind", "geology_model")), "handle": "center", **item_meta})
                    continue
                if primitive.bounds is None:
                    continue
                if primitive.kind in {"face", "surface"}:
                    pts = _face_points_from_bounds(tuple(float(v) for v in primitive.bounds))
                    poly = pv.PolyData(np.asarray(pts, dtype=float))
                    poly.faces = np.asarray([len(pts), *range(len(pts))], dtype=np.int64)
                    self.plotter.add_mesh(poly, style="wireframe", line_width=5, name=name)
                elif primitive.kind == "edge":
                    pts = _edge_points_from_bounds(tuple(float(v) for v in primitive.bounds))
                    poly = pv.PolyData(np.asarray(pts, dtype=float))
                    poly.lines = np.asarray([2, 0, 1], dtype=np.int64)
                    self.plotter.add_mesh(poly, line_width=7, name=name)
                else:
                    box = pv.Box(bounds=tuple(float(v) for v in primitive.bounds))
                    self.plotter.add_mesh(box, style="wireframe", line_width=5, name=name)
                self.selection_names.append(name)
                b = tuple(float(v) for v in primitive.bounds)
                cx, cy, cz = _bounds_center(b)
                extent = max(max(b[1] - b[0], b[3] - b[2], b[5] - b[4]), 1.0)
                radius = max(extent * 0.025, 0.08)
                center_name = f"edit-handle-{idx}-center-{entity_id}"
                actor = self.plotter.add_mesh(pv.Sphere(radius=radius, center=(cx, cy, cz)), name=center_name)
                self.handle_names.append(center_name)
                self._register_actor(actor, {"entity_id": entity_id, "kind": primitive.kind, "primitive_id": primitive.id, "handle": "center", **dict(primitive.metadata)})
                for axis, end in {
                    "x": (cx + extent * 0.45, cy, cz),
                    "y": (cx, cy + extent * 0.45, cz),
                    "z": (cx, cy, cz + extent * 0.45),
                }.items():
                    hname = f"gizmo-axis-{axis}-{idx}-{entity_id}"
                    pts = np.asarray([(cx, cy, cz), end], dtype=float)
                    poly = pv.PolyData(pts)
                    poly.lines = np.asarray([2, 0, 1], dtype=np.int64)
                    hactor = self.plotter.add_mesh(poly, line_width=6, render_points_as_spheres=True, point_size=10, name=hname)
                    self.handle_names.append(hname)
                    self._register_actor(hactor, {"entity_id": entity_id, "kind": primitive.kind, "primitive_id": primitive.id, "handle": "axis", "handle_axis": axis, **dict(primitive.metadata)})
            except Exception:
                pass
        self.safe_render(reason="selection_overlay")

    def _set_cell_data(self, dataset: Any, name: str, values: list[str]) -> None:
        try:
            import numpy as np
            dataset.cell_data[name] = np.asarray([str(v) for v in values], dtype=str)
        except Exception:
            pass

    def _attach_cell_metadata(self, dataset: Any, primitive: ScenePrimitive) -> None:
        try:
            count = int(getattr(dataset, "n_cells", 0) or 0)
        except Exception:
            count = 0
        if count <= 0:
            return
        metadata = dict(primitive.metadata or {})
        primitive_ids = [primitive.id] * count
        source_ids = [str(metadata.get("source_entity_id") or primitive.entity_id)] * count
        if primitive.kind == "block" and metadata.get("topology_face_ids"):
            face_ids = [str(v) for v in list(metadata.get("topology_face_ids") or []) if str(v)]
            entities = [(face_ids[i] if i < len(face_ids) else face_ids[-1]) for i in range(count)]
            kinds = ["face"] * count
            topology_ids = list(entities)
        elif primitive.kind in {"face", "edge"}:
            topo = str(metadata.get("topology_id") or primitive.entity_id)
            entities = [topo] * count
            kinds = [primitive.kind] * count
            topology_ids = [topo] * count
        else:
            entities = [primitive.entity_id] * count
            kinds = [primitive.kind] * count
            topology_ids = [str(metadata.get("topology_id") or "")] * count
        self._set_cell_data(dataset, "geoai_entity_id", entities)
        self._set_cell_data(dataset, "geoai_kind", kinds)
        self._set_cell_data(dataset, "geoai_primitive_id", primitive_ids)
        self._set_cell_data(dataset, "geoai_topology_id", topology_ids)
        self._set_cell_data(dataset, "geoai_source_entity_id", source_ids)


    def clear_mesh_overlay(self) -> None:
        for name in list(self.mesh_names):
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass
        self.mesh_names.clear()

    def _vtk_cell_type(self, cell_type: str, node_count: int) -> int:
        key = str(cell_type or "").lower().replace("-", "_").replace(" ", "_")
        mapped = {
            "line": 3, "line2": 3, "edge": 3,
            "tri": 5, "tri3": 5, "triangle": 5,
            "quad": 9, "quad4": 9, "quadrilateral": 9,
            "tet4": 10, "tetra": 10, "tetra4": 10, "tetrahedron": 10,
            "hex8": 12, "hexa": 12, "hexahedron": 12, "brick": 12,
            "wedge": 13, "wedge6": 13, "prism": 13,
            "pyramid": 14, "pyramid5": 14,
            "quadratic_edge": 21, "line3": 21,
            "triangle6": 22, "tri6": 22,
            "quad8": 23,
            "tetra10": 24, "tet10": 24,
            "hexahedron20": 25, "hex20": 25,
            "wedge15": 26,
            "pyramid13": 27,
            "quad9": 28,
        }
        if key in mapped:
            return mapped[key]
        if node_count == 2:
            return 3
        if node_count == 3:
            return 5
        if node_count == 4:
            return 10
        if node_count == 5:
            return 14
        if node_count == 6:
            return 13
        if node_count == 8:
            return 12
        if node_count == 10:
            return 24
        return 7  # VTK_POLYGON fallback

    def _scalar_unique_count(self, values: list[Any]) -> int:
        return len({str(v) for v in values})

    def _looks_like_geology_scalar(self, name: str) -> bool:
        lower = str(name or "").lower().replace("-", "_").replace(":", "_").replace(" ", "_")
        if lower.startswith("vtk") or lower in {"geoai_entity_id", "geoai_kind", "geoai_primitive_id", "geoai_topology_id", "geoai_source_entity_id"}:
            return False
        tokens = ("soil", "stratum", "strata", "layer", "geology", "geo", "lithology", "formation", "material", "mat", "rock", "phase", "physical", "gmsh", "region", "domain", "zone", "group", "unit", "facies")
        return any(token in lower for token in tokens)

    def _preferred_mesh_scalar(self, mesh: Any) -> str | None:
        tags = getattr(mesh, "cell_tags", {}) or {}
        meta = dict(getattr(mesh, "metadata", {}) or {})
        cell_count = int(getattr(mesh, "cell_count", 0) or 0)
        candidates = (
            str(meta.get("active_cell_scalar") or ""),
            str(meta.get("preferred_geology_scalar") or ""),
            "soil_id", "soilid", "soil", "soil_layer", "soil_layer_id",
            "stratum_id", "stratum", "strata", "strata_id",
            "layer_id", "layer", "geology_layer", "geology_layer_id",
            "lithology", "formation", "formation_id", "facies",
            "material_index", "material_id", "materialid", "material", "mat_id", "mat",
            "gmsh_physical", "gmsh:physical", "physical", "physical_group", "physical_id",
            "domain", "domain_id", "region", "region_id", "zone", "zone_id",
            "display_group",
        )
        lower_to_key = {str(k).lower().replace("-", "_").replace(":", "_").replace(" ", "_"): k for k in tags}
        ordered: list[str] = []
        for name in candidates:
            if not name:
                continue
            key = lower_to_key.get(str(name).lower().replace("-", "_").replace(":", "_").replace(" ", "_"))
            if key is not None and len(list(tags.get(key, []))) == cell_count:
                ordered.append(str(key))
        for key, values in tags.items():
            if len(list(values)) == cell_count and self._looks_like_geology_scalar(str(key)):
                ordered.append(str(key))
        ordered = list(dict.fromkeys(ordered))
        if not ordered:
            return None
        multi = [key for key in ordered if self._scalar_unique_count(list(tags.get(key, []))) > 1]
        return multi[0] if multi else ordered[0]

    def _add_mesh_line_actor(self, dataset: Any, *, name: str, line_width: int = 1, info: dict[str, Any] | None = None) -> bool:
        try:
            if dataset is None or int(getattr(dataset, "n_cells", 0) or 0) <= 0:
                return False
        except Exception:
            pass
        actor = None
        try:
            actor = self.plotter.add_mesh(dataset, line_width=line_width, name=name, lighting=False, render_lines_as_tubes=False)
        except TypeError:
            try:
                actor = self.plotter.add_mesh(dataset, line_width=line_width, name=name, lighting=False)
            except TypeError:
                actor = self.plotter.add_mesh(dataset, line_width=line_width, name=name)
        if info:
            self._register_actor(actor, info)
        self.mesh_names.append(name)
        return True

    def _surface_cell_centers_array(self, surface: Any) -> Any | None:
        try:
            centers = surface.cell_centers()
            return getattr(centers, "points", None)
        except Exception:
            return None

    def _extract_all_edges(self, dataset: Any) -> Any | None:
        try:
            fn = getattr(dataset, "extract_all_edges", None)
            if fn is not None:
                return fn()
        except Exception:
            pass
        try:
            return dataset.extract_feature_edges(boundary_edges=True, feature_edges=True, manifold_edges=True, non_manifold_edges=True)
        except Exception:
            return None

    def _add_paraview_mesh_contours(self, surface: Any, grid: Any) -> dict[str, Any]:
        """Draw ParaView-like external grid lines and four lateral side contours.

        ``show_edges=True`` on the same surface actor can cause z-fighting and
        moire artifacts.  This draws line actors separately: all external surface
        edges for the real mesh texture, plus x/y side bands so front/back/left/
        right outlines remain legible even on dense VTU geology meshes.
        """
        import numpy as np

        added: list[str] = []
        pick_info = {"entity_id": "imported_geology_model", "kind": "geology_model", "primitive_id": "imported_geology_model", "source_entity_id": "imported_geology_model"}
        all_edges = self._extract_all_edges(surface)
        if all_edges is not None and self._add_mesh_line_actor(all_edges, name="geoai-imported-surface-grid-lines", line_width=1, info=pick_info):
            added.append("geoai-imported-surface-grid-lines")
        try:
            outline = grid.outline()
            if self._add_mesh_line_actor(outline, name="geoai-imported-mesh-outline", line_width=4, info=pick_info):
                added.append("geoai-imported-mesh-outline")
        except Exception:
            pass
        centers = self._surface_cell_centers_array(surface)
        if centers is None:
            return {"edge_actors": added, "side_actors": []}
        try:
            centers = np.asarray(centers, dtype=float)
            bounds = [float(v) for v in surface.bounds]
        except Exception:
            return {"edge_actors": added, "side_actors": []}
        if centers.size == 0 or len(bounds) != 6:
            return {"edge_actors": added, "side_actors": []}
        x0, x1, y0, y1, z0, z1 = bounds
        span = max(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), 1.0)
        tol = max(span * 1.0e-5, 1.0e-9)
        sides = {
            "xmin": (0, x0),
            "xmax": (0, x1),
            "ymin": (1, y0),
            "ymax": (1, y1),
        }
        side_actors: list[str] = []
        for side_name, (axis, value) in sides.items():
            local = np.where(np.abs(centers[:, axis] - value) <= tol)[0]
            if len(local) == 0:
                local = np.where(np.abs(centers[:, axis] - value) <= max(span * 1.0e-3, tol))[0]
            if len(local) == 0:
                continue
            try:
                side = surface.extract_cells(local.tolist())
                side_edges = self._extract_all_edges(side)
                actor_name = f"geoai-imported-side-grid-{side_name}"
                if side_edges is not None and self._add_mesh_line_actor(side_edges, name=actor_name, line_width=2, info={**pick_info, "side": side_name}):
                    side_actors.append(actor_name)
                    added.append(actor_name)
            except Exception:
                continue
        return {"edge_actors": added, "side_actors": side_actors}

    def render_project_mesh_overlay(self, project: Any, *, clear: bool = True) -> dict[str, Any]:
        """Render imported/generated MeshDocument in a ParaView-like geology style.

        The main actor is the extracted external surface colored by categorical
        geology cell scalars (preferably ``soil_id`` for VTU or
        ``gmsh_physical`` for MSH).  Surface wireframe, feature edges and outline
        are drawn separately so users see four-side boundary mesh contours
        without the visual noise of every internal volume edge.
        """
        if clear:
            self.clear_mesh_overlay()
        mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
        if mesh is None or not getattr(mesh, "nodes", None) or not getattr(mesh, "cells", None):
            self.metadata["mesh_overlay"] = {"ok": False, "reason": "no_mesh_document"}
            return dict(self.metadata["mesh_overlay"])
        try:
            import numpy as np
            import pyvista as pv
        except Exception as exc:  # pragma: no cover
            self.metadata["mesh_overlay"] = {"ok": False, "reason": f"pyvista_unavailable: {exc}"}
            return dict(self.metadata["mesh_overlay"])
        try:
            points = np.asarray(mesh.nodes, dtype=float)
            cells_flat: list[int] = []
            cell_types: list[int] = []
            kept_indices: list[int] = []
            for i, cell in enumerate(mesh.cells):
                ids = [int(v) for v in cell]
                if not ids:
                    continue
                if min(ids) < 0 or max(ids) >= len(points):
                    continue
                cells_flat.extend([len(ids), *ids])
                ctype = str(mesh.cell_types[i] if i < len(mesh.cell_types) else "")
                cell_types.append(self._vtk_cell_type(ctype, len(ids)))
                kept_indices.append(i)
            if not kept_indices:
                self.metadata["mesh_overlay"] = {"ok": False, "reason": "no_supported_cells"}
                return dict(self.metadata["mesh_overlay"])
            grid = pv.UnstructuredGrid(np.asarray(cells_flat, dtype=np.int64), np.asarray(cell_types, dtype=np.uint8), points)
            scalar_name = self._preferred_mesh_scalar(mesh)
            raw_values = list(getattr(mesh, "cell_tags", {}).get(scalar_name, []) or []) if scalar_name else []
            scalar_lookup: dict[str, int] = {}
            scalar_labels: list[str] = []
            scalar_indices: list[int] = []
            scalar_numeric: list[float] = []
            numeric_ok = True
            for old_i in kept_indices:
                value = raw_values[old_i] if old_i < len(raw_values) else old_i
                label = str(value)
                if label not in scalar_lookup:
                    scalar_lookup[label] = len(scalar_lookup)
                    scalar_labels.append(label)
                scalar_indices.append(scalar_lookup[label])
                try:
                    scalar_numeric.append(float(value))
                except Exception:
                    numeric_ok = False
                    scalar_numeric.append(float(scalar_lookup[label]))
            # ParaView-style categorical rendering: always render geology/material
            # labels through a compact category index so numeric layer IDs get
            # distinct colors instead of a continuous heat-map gradient.
            display_scalar = scalar_name or "geology_layer"
            active_values = np.asarray(scalar_indices, dtype=float)
            grid.cell_data[display_scalar] = active_values
            layer_values_by_cell = [scalar_labels[i] if i < len(scalar_labels) else str(scalar_indices[pos]) for pos, i in enumerate(scalar_indices)]
            grid.cell_data["geoai_source_cell_id"] = np.asarray(kept_indices, dtype=np.int64)
            grid.cell_data["geoai_entity_id"] = np.asarray([f"geology_layer:{label}" for label in layer_values_by_cell], dtype=str)
            grid.cell_data["geoai_kind"] = np.asarray(["geology_layer" for _ in kept_indices], dtype=str)
            grid.cell_data["geoai_primitive_id"] = np.asarray(["imported_geology_model" for _ in kept_indices], dtype=str)
            grid.cell_data["geoai_topology_id"] = np.asarray([f"geology_layer:{label}" for label in layer_values_by_cell], dtype=str)
            grid.cell_data["geoai_source_entity_id"] = np.asarray(["imported_geology_model" for _ in kept_indices], dtype=str)
            grid.cell_data["geoai_layer_value"] = np.asarray(layer_values_by_cell, dtype=str)
            grid.cell_data[f"{display_scalar}_raw_label"] = np.asarray(layer_values_by_cell, dtype=str)
            bad_ids = set(int(v) for v in list(getattr(mesh.quality, "bad_cell_ids", []) or []))
            grid.cell_data["geoai_bad_cell"] = np.asarray([1.0 if old_i in bad_ids else 0.0 for old_i in kept_indices], dtype=float)

            try:
                surface = grid.extract_surface(pass_pointid=True, pass_cellid=True, algorithm="dataset_surface")
            except TypeError:
                surface = grid.extract_surface()
            original = surface.cell_data.get("vtkOriginalCellIds")
            if original is None:
                original = surface.cell_data.get("vtkoriginalcellids")
            if original is not None:
                oi = np.asarray(original, dtype=int)
                valid = oi[(oi >= 0) & (oi < len(active_values))]
                if len(valid) == len(oi) and display_scalar not in surface.cell_data:
                    surface.cell_data[display_scalar] = active_values[oi]
                for key in ("geoai_entity_id", "geoai_kind", "geoai_primitive_id", "geoai_topology_id", "geoai_source_entity_id", "geoai_layer_value", f"{display_scalar}_raw_label"):
                    if key not in surface.cell_data and key in grid.cell_data and len(valid) == len(oi):
                        surface.cell_data[key] = np.asarray(grid.cell_data[key])[oi]
            # Main ParaView-like solid surface: categorical geology colors, no
            # coincident wireframe on the surface actor.  Mesh lines are rendered
            # as independent line actors below to avoid flower shadow artifacts.
            clim = None
            if len(active_values):
                clim = [float(np.nanmin(active_values)), float(np.nanmax(active_values))]
            annotations = {float(idx): label for label, idx in scalar_lookup.items()}
            mesh_kwargs = {
                "scalars": display_scalar if display_scalar in surface.cell_data else None,
                "cmap": "tab20",
                "n_colors": max(int(len(scalar_lookup)), 2),
                "categories": True,
                "show_edges": False,
                "opacity": 1.0,
                "name": "geoai-imported-geology-surface",
                "scalar_bar_args": {"title": display_scalar, "n_labels": min(max(int(len(scalar_lookup)), 2), 12)},
                "clim": clim,
                "lighting": False,
                "smooth_shading": False,
                "annotations": annotations,
            }
            try:
                actor = self.plotter.add_mesh(surface, **mesh_kwargs)
            except TypeError:
                mesh_kwargs.pop("annotations", None)
                try:
                    actor = self.plotter.add_mesh(surface, **mesh_kwargs)
                except TypeError:
                    mesh_kwargs.pop("n_colors", None)
                    actor = self.plotter.add_mesh(surface, **mesh_kwargs)
            self.mesh_names.append("geoai-imported-geology-surface")
            self._register_actor(actor, {"entity_id": "imported_geology_model", "kind": "geology_model", "primitive_id": "imported_geology_model", "display_scalar": display_scalar, "layer_labels": list(scalar_labels)})
            contour_info = self._add_paraview_mesh_contours(surface, grid)
            if bad_ids:
                local_bad = [idx for idx, old_i in enumerate(kept_indices) if old_i in bad_ids]
                if local_bad:
                    try:
                        bad = grid.extract_cells(local_bad).extract_surface(algorithm="dataset_surface")
                        self.plotter.add_mesh(bad, style="wireframe", line_width=4, name="geoai-bad-fem-cells")
                        self.mesh_names.append("geoai-bad-fem-cells")
                    except Exception:
                        pass
            try:
                quality = getattr(mesh, "quality", None)
                nonmanifold = dict(getattr(mesh, "metadata", {}) or {}).get("nonmanifold_report", {})
                text = (
                    f"Mesh: nodes={mesh.node_count} cells={mesh.cell_count} layers={len(scalar_lookup)} scalar={display_scalar}\n"
                    f"minQ={getattr(quality, 'min_quality', None)} aspect={getattr(quality, 'max_aspect_ratio', None)} bad={len(bad_ids)} "
                    f"nonmanifold={nonmanifold.get('nonmanifold_face_count', 0)}"
                )
                self.plotter.add_text(text, position="upper_left", name="geoai-mesh-summary")
                self.mesh_names.append("geoai-mesh-summary")
            except Exception:
                pass
            try:
                self.metadata["imported_geology_bounds"] = [float(v) for v in grid.bounds]
                layer_bounds: dict[str, list[float]] = {}
                for layer_label, layer_index in scalar_lookup.items():
                    local = [idx for idx, value in enumerate(scalar_indices) if value == layer_index]
                    if local:
                        layer_grid = grid.extract_cells(local)
                        layer_bounds[layer_label] = [float(v) for v in layer_grid.bounds]
                self.metadata["imported_geology_layer_bounds"] = layer_bounds
            except Exception:
                pass
            info = {
                "ok": True,
                "node_count": int(mesh.node_count),
                "cell_count": int(mesh.cell_count),
                "displayed_cell_count": int(len(kept_indices)),
                "layer_count": int(len(scalar_lookup)),
                "display_scalar": display_scalar,
                "bad_cell_count": int(len(bad_ids)),
                "actor": str(actor),
                "contour_actors": list(contour_info.get("edge_actors", []) or []),
                "side_contour_actors": list(contour_info.get("side_actors", []) or []),
                "style": "paraview_categorical_surface_plus_external_grid_contours",
            }
            self.metadata["mesh_overlay"] = info
            return info
        except Exception as exc:  # pragma: no cover
            msg = f"Mesh overlay render failed: {type(exc).__name__}: {exc}"
            self._status(msg)
            self.metadata["mesh_overlay"] = {"ok": False, "reason": msg}
            return dict(self.metadata["mesh_overlay"])

    def render_result_overlay(self, project: Any, *, field_name: str = "cell_von_mises", phase_id: str | None = None, clear: bool = True) -> dict[str, Any]:
        """Render the latest FEM result field on the imported/geology mesh.

        Cell fields are mapped by ResultFieldRecord.entity_ids, which store the
        original mesh cell ids from the compiler.  Nodal fields are mapped by the
        compact phase node order; this is sufficient for the current imported
        geology workflow where all cells are active in the automatic-stress run.
        """
        if clear:
            self.clear_mesh_overlay()
        mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
        if mesh is None or not getattr(mesh, "nodes", None) or not getattr(mesh, "cells", None):
            return {"ok": False, "reason": "no_mesh_document"}
        results = dict(getattr(getattr(project, "result_store", None), "phase_results", {}) or {})
        if not results:
            return {"ok": False, "reason": "no_phase_results"}
        phase_ids: list[str] = []
        try:
            phase_ids = list(project.phase_ids())
        except Exception:
            phase_ids = list(results.keys())
        ordered = [pid for pid in phase_ids if pid in results] or list(results.keys())
        if phase_id is None:
            phase_id = ordered[-1]
        stage = results.get(str(phase_id))
        if stage is None:
            return {"ok": False, "reason": f"phase_result_not_found:{phase_id}"}
        fields = dict(getattr(stage, "fields", {}) or {})
        field = fields.get(str(field_name))
        if field is None and str(field_name) == "displacement":
            field = fields.get("displacement")
        if field is None:
            return {"ok": False, "reason": f"field_not_found:{field_name}", "available_fields": sorted(fields)}
        try:
            import numpy as np
            import pyvista as pv
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "reason": f"pyvista_unavailable: {exc}"}
        try:
            points = np.asarray(mesh.nodes, dtype=float)
            cells_flat: list[int] = []
            cell_types: list[int] = []
            kept_indices: list[int] = []
            for i, cell in enumerate(mesh.cells):
                ids = [int(v) for v in cell]
                if not ids or min(ids) < 0 or max(ids) >= len(points):
                    continue
                cells_flat.extend([len(ids), *ids])
                ctype = str(mesh.cell_types[i] if i < len(mesh.cell_types) else "")
                cell_types.append(self._vtk_cell_type(ctype, len(ids)))
                kept_indices.append(i)
            if not kept_indices:
                return {"ok": False, "reason": "no_supported_cells"}
            grid = pv.UnstructuredGrid(np.asarray(cells_flat, dtype=np.int64), np.asarray(cell_types, dtype=np.uint8), points)
            values = [float(v) for v in list(getattr(field, "values", []) or [])]
            association = str(getattr(field, "association", ""))
            components = int(getattr(field, "components", 1) or 1)
            scalar_name = f"result_{field_name}"
            if association == "cell":
                out = np.full(len(kept_indices), np.nan, dtype=float)
                entity_ids = [str(v) for v in list(getattr(field, "entity_ids", []) or [])]
                id_to_value: dict[int, float] = {}
                if components <= 1:
                    for eid, value in zip(entity_ids, values):
                        try:
                            id_to_value[int(eid)] = float(value)
                        except Exception:
                            continue
                else:
                    for idx, eid in enumerate(entity_ids):
                        start = idx * components
                        vec = values[start:start + components]
                        if len(vec) == components:
                            try:
                                id_to_value[int(eid)] = float(np.linalg.norm(np.asarray(vec, dtype=float)))
                            except Exception:
                                pass
                for local_i, old_i in enumerate(kept_indices):
                    if old_i in id_to_value:
                        out[local_i] = id_to_value[old_i]
                if np.all(np.isnan(out)):
                    return {"ok": False, "reason": "cell_field_has_no_matching_entity_ids"}
                fill = float(np.nanmin(out)) if np.any(~np.isnan(out)) else 0.0
                out = np.where(np.isnan(out), fill, out)
                grid.cell_data[scalar_name] = out
            else:
                if components == 3 and len(values) >= points.shape[0] * 3:
                    vec = np.asarray(values[:points.shape[0] * 3], dtype=float).reshape((-1, 3))
                    if str(field_name) == "uz":
                        point_values = vec[:, 2]
                    else:
                        point_values = np.linalg.norm(vec, axis=1)
                else:
                    point_values = np.asarray(values[:points.shape[0]], dtype=float)
                    if len(point_values) < points.shape[0]:
                        point_values = np.pad(point_values, (0, points.shape[0] - len(point_values)), constant_values=0.0)
                grid.point_data[scalar_name] = point_values
            try:
                surface = grid.extract_surface(pass_pointid=True, pass_cellid=True, algorithm="dataset_surface")
            except TypeError:
                surface = grid.extract_surface()
            try:
                actor = self.plotter.add_mesh(
                    surface,
                    scalars=scalar_name,
                    cmap="viridis",
                    show_edges=False,
                    lighting=False,
                    smooth_shading=False,
                    name="geoai-fem-result-surface",
                    scalar_bar_args={"title": f"{phase_id}:{field_name}"},
                )
            except TypeError:
                actor = self.plotter.add_mesh(surface, scalars=scalar_name, show_edges=False, name="geoai-fem-result-surface")
            self.mesh_names.append("geoai-fem-result-surface")
            self._register_actor(actor, {"entity_id": "imported_geology_model", "kind": "fem_result", "primitive_id": "imported_geology_model", "result_field": str(field_name), "phase_id": str(phase_id)})
            contour_info = self._add_paraview_mesh_contours(surface, grid)
            try:
                metrics = dict(getattr(stage, "metrics", {}) or {})
                text = (
                    f"FEM result: phase={phase_id} field={field_name}\n"
                    f"max|u|={metrics.get('max_displacement', 0.0)} settlement={metrics.get('max_settlement', 0.0)} "
                    f"vm={metrics.get('max_von_mises_stress', 0.0)}"
                )
                self.plotter.add_text(text, position="upper_left", name="geoai-fem-result-summary")
                self.mesh_names.append("geoai-fem-result-summary")
            except Exception:
                pass
            info = {"ok": True, "phase_id": str(phase_id), "field_name": str(field_name), "association": association, "components": components, "contour_actors": list(contour_info.get("edge_actors", []) or []), "style": "fem_result_scalar_surface_plus_external_grid_contours"}
            self.metadata["fem_result_overlay"] = info
            return info
        except Exception as exc:  # pragma: no cover
            msg = f"FEM result overlay failed: {type(exc).__name__}: {exc}"
            self._status(msg)
            self.metadata["fem_result_overlay"] = {"ok": False, "reason": msg}
            return dict(self.metadata["fem_result_overlay"])

    def render_viewport_state(self, state: ViewportState, *, clear: bool = True) -> dict[str, dict[str, str]]:
        if clear:
            try:
                self.plotter.clear()
            except Exception:
                pass
        actor_map: dict[str, dict[str, str]] = {}
        if clear:
            self.actor_entity_map.clear()
        self.bind_viewport_state(state)
        for primitive in state.primitives.values():
            actor = self._add_primitive(primitive)
            if actor is None:
                continue
            info = {"entity_id": primitive.entity_id, "kind": primitive.kind, "primitive_id": primitive.id, **dict(primitive.metadata)}
            self._register_actor(actor, info)
            actor_map[primitive.entity_id] = {"entity_id": primitive.entity_id, "kind": primitive.kind, "primitive_id": primitive.id}
        return actor_map

    def _add_primitive(self, primitive: ScenePrimitive) -> Any | None:
        if not primitive.visible:
            return None
        try:
            import numpy as np
            import pyvista as pv
        except Exception:  # pragma: no cover
            return None
        try:
            meta_points = list(primitive.metadata.get("points", []) or [])
            points = np.asarray(meta_points, dtype=float).reshape((-1, 3)) if meta_points else np.empty((0, 3), dtype=float)
            name = primitive.id
            opacity = float(primitive.style.get("opacity", 0.8))
            if primitive.kind == "point" and primitive.bounds is not None:
                x0, _, y0, _, z0, _ = primitive.bounds
                dataset = pv.PolyData(np.asarray([[x0, y0, z0]], dtype=float))
                return self.plotter.add_mesh(dataset, render_points_as_spheres=True, point_size=11, name=name)
            if primitive.kind in {"edge", "support", "partition_feature", "contact_pair"}:
                if len(points) < 2 and primitive.bounds is not None:
                    points = np.asarray(_edge_points_from_bounds(tuple(float(v) for v in primitive.bounds)), dtype=float)
                if len(points) >= 2:
                    dataset = pv.PolyData(points)
                    lines: list[int] = []
                    for idx in range(len(points) - 1):
                        lines.extend([2, idx, idx + 1])
                    dataset.lines = np.asarray(lines, dtype=np.int64)
                    self._attach_cell_metadata(dataset, primitive)
                    return self.plotter.add_mesh(dataset, line_width=4, render_points_as_spheres=True, point_size=8, name=name)
            if primitive.kind in {"surface", "face"}:
                if len(points) < 3 and primitive.bounds is not None:
                    points = np.asarray(_face_points_from_bounds(tuple(float(v) for v in primitive.bounds)), dtype=float)
                if len(points) >= 3:
                    dataset = pv.PolyData(points)
                    dataset.faces = np.asarray([len(points), *range(len(points))], dtype=np.int64)
                    self._attach_cell_metadata(dataset, primitive)
                    actor = self.plotter.add_mesh(dataset, show_edges=False, opacity=max(min(opacity, 0.8), 0.2), name=name, lighting=False, smooth_shading=False)
                    try:
                        edge_name = f"{name}:edges"
                        edges = self._extract_all_edges(dataset)
                        if edges is not None:
                            edge_actor = self.plotter.add_mesh(edges, line_width=2, name=edge_name, lighting=False, render_lines_as_tubes=False)
                            self._register_actor(edge_actor, {"entity_id": primitive.entity_id, "kind": primitive.kind, "primitive_id": primitive.id, **dict(primitive.metadata)})
                    except Exception:
                        pass
                    return actor
            if primitive.kind == "block" and primitive.bounds is not None:
                dataset = pv.Box(bounds=tuple(float(v) for v in primitive.bounds))
                self._attach_cell_metadata(dataset, primitive)
                render_mode = str(primitive.metadata.get("render_mode") or "solid")
                if render_mode == "outline_only":
                    outline = dataset.outline()
                    return self.plotter.add_mesh(outline, line_width=3, name=name, lighting=False, render_lines_as_tubes=False)
                actor = self.plotter.add_mesh(dataset, show_edges=False, opacity=max(min(opacity, 1.0), 0.08), name=name, lighting=False, smooth_shading=False)
                try:
                    edge_name = f"{name}:edges"
                    edges = self._extract_all_edges(dataset)
                    if edges is not None:
                        edge_actor = self.plotter.add_mesh(edges, line_width=1, name=edge_name, lighting=False, render_lines_as_tubes=False)
                        self._register_actor(edge_actor, {"entity_id": primitive.entity_id, "kind": primitive.kind, "primitive_id": primitive.id, **dict(primitive.metadata)})
                except Exception:
                    pass
                return actor
        except Exception as exc:  # pragma: no cover
            self._status(f"Primitive render failed for {primitive.entity_id}: {exc}")
        return None


__all__ = ["PyVistaViewportAdapter"]
