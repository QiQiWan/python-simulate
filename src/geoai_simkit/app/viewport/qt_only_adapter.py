from __future__ import annotations

"""Qt-only viewport adapter used when PyVista/VTK cannot create a render window.

The adapter preserves the GUI workflow, project editing, import assembly and
readiness panels even on Windows/RDP/OpenGL setups where ``QtInteractor`` fails.
It deliberately implements the small method surface consumed by
``phase_workbench_qt`` while making no 3D-rendering claims.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from geoai_simkit.app.viewport.snap_controller import SnapController
from geoai_simkit.app.viewport.workplane import WorkPlaneController

QT_ONLY_VIEWPORT_ADAPTER_CONTRACT = "geoai_simkit_qt_only_viewport_adapter_v1"


@dataclass(slots=True)
class QtOnlyViewportAdapter:
    widget: Any | None = None
    refresh_callback: Callable[[], None] | None = None
    status_callback: Callable[[str], None] | None = None
    selection_callback: Callable[[Any | None], None] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    snap: SnapController = field(default_factory=SnapController)
    workplane: WorkPlaneController = field(default_factory=WorkPlaneController)
    runtime: Any | None = None
    viewport_state: Any | None = None
    context_menu_callback: Callable[[Any], bool] | None = None

    def __post_init__(self) -> None:
        self.metadata.update(
            {
                "contract": QT_ONLY_VIEWPORT_ADAPTER_CONTRACT,
                "backend": "qt_only",
                "pyvista_enabled": False,
                "opengl_guard": {"enabled": False, "reason": "qt_only_workbench"},
                "opengl_exposure_state": {"exposed": False, "reason": "qt_only_workbench"},
                "message": "PyVista/VTK rendering is disabled; import/assembly/mesh/readiness panels remain available.",
            }
        )

    def _emit_status(self, message: str) -> None:
        if self.status_callback is not None:
            try:
                self.status_callback(message)
            except Exception:
                pass
        if self.widget is not None and hasattr(self.widget, "setPlainText"):
            try:
                self.widget.setPlainText(message)
            except Exception:
                pass

    def bind_context_menu_callback(self, callback: Callable[[Any], bool]) -> None:
        self.context_menu_callback = callback

    def bind_runtime(self, runtime: Any) -> None:
        self.runtime = runtime

    def bind_viewport_state(self, state: Any) -> None:
        self.viewport_state = state
        count = len(getattr(state, "primitives", {}) or {})
        self.metadata["primitive_count"] = count

    def bind_events(self) -> None:
        self.metadata["events_bound"] = False
        self.metadata["event_note"] = "Qt-only adapter has no 3D mouse picking; use import-driven assembly controls."

    def render_viewport_state(self, state: Any, *, clear: bool = True) -> dict[str, Any]:
        self.bind_viewport_state(state)
        count = len(getattr(state, "primitives", {}) or {})
        self._emit_status(f"Qt-only 工作台：已加载 {count} 个视图对象；3D OpenGL 视口已禁用，导入拼接/网格/Readiness 可继续使用。")
        return {"ok": True, "backend": "qt_only", "primitive_count": count, "clear": bool(clear)}


    def render_project_mesh_overlay(self, project: Any, *, clear: bool = True) -> dict[str, Any]:
        mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
        if mesh is None:
            msg = "Qt-only 工作台：当前没有导入网格；请先导入 MSH/VTU/STL/IFC/STEP。"
            self.metadata["mesh_overlay"] = {"ok": False, "backend": "qt_only", "reason": "no_mesh_document"}
        else:
            quality = getattr(mesh, "quality", None)
            layers = getattr(mesh, "cell_tags", {}).get("geology_layer_id", []) or []
            msg = (
                f"Qt-only 工作台：已加载网格 nodes={getattr(mesh, 'node_count', 0)} cells={getattr(mesh, 'cell_count', 0)} "
                f"layers={len(set(str(v) for v in layers)) if layers else 0} "
                f"bad={len(getattr(quality, 'bad_cell_ids', []) or [])}。"
            )
            self.metadata["mesh_overlay"] = {"ok": True, "backend": "qt_only", "node_count": getattr(mesh, 'node_count', 0), "cell_count": getattr(mesh, 'cell_count', 0)}
        self._emit_status(msg)
        return dict(self.metadata.get("mesh_overlay", {}))

    def render_result_overlay(self, project: Any, *, field_name: str = "cell_von_mises", phase_id: str | None = None, clear: bool = True) -> dict[str, Any]:
        results = dict(getattr(getattr(project, "result_store", None), "phase_results", {}) or {})
        if not results:
            msg = "Qt-only 工作台：暂无 FEM 求解结果；请先执行求解至稳态。"
            self.metadata["fem_result_overlay"] = {"ok": False, "backend": "qt_only", "reason": "no_phase_results"}
            self._emit_status(msg)
            return dict(self.metadata["fem_result_overlay"])
        if phase_id is None:
            try:
                phase_order = [pid for pid in project.phase_ids() if pid in results]
            except Exception:
                phase_order = list(results)
            phase_id = phase_order[-1] if phase_order else next(iter(results))
        stage = results.get(str(phase_id))
        metrics = dict(getattr(stage, "metrics", {}) or {}) if stage is not None else {}
        msg = (
            f"Qt-only 工作台：FEM 结果 phase={phase_id} field={field_name}; "
            f"max|u|={metrics.get('max_displacement', 0.0)} settlement={metrics.get('max_settlement', 0.0)} "
            f"von_mises={metrics.get('max_von_mises_stress', 0.0)}。"
        )
        self.metadata["fem_result_overlay"] = {"ok": stage is not None, "backend": "qt_only", "phase_id": str(phase_id), "field_name": str(field_name), "metrics": metrics}
        self._emit_status(msg)
        return dict(self.metadata["fem_result_overlay"])

    def render_selection(self, selection: Any | None) -> dict[str, Any]:
        self.metadata["last_selection"] = selection.to_dict() if hasattr(selection, "to_dict") else selection
        return {"ok": True, "backend": "qt_only"}

    def safe_render(self, *, reason: str = "") -> bool:
        self.metadata["last_render_reason"] = reason
        return True

    def suspend_rendering(self, reason: str = "") -> None:
        self.metadata["rendering_suspended"] = True
        self.metadata["rendering_suspended_reason"] = reason

    def apply_tool_output(self, output: Any) -> None:
        self.metadata["last_tool_output"] = output.to_dict() if hasattr(output, "to_dict") else output
        self._emit_status("Qt-only 工作台：鼠标建模工具不可用；请优先使用导入拼接工作流。")

    def render_constraint_lock_state(self, state: dict[str, Any]) -> None:
        self.metadata["constraint_lock"] = dict(state or {})

    def render_constraint_unlock_feedback(self, feedback: dict[str, Any]) -> None:
        self.metadata["last_unlock_feedback"] = dict(feedback or {})


__all__ = ["QT_ONLY_VIEWPORT_ADAPTER_CONTRACT", "QtOnlyViewportAdapter"]
