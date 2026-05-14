from __future__ import annotations

"""Modern six-phase CAD workbench shell.

1.4.6 focuses on CAD usability: a compact top navigation bar, dockable/floating
browser/inspector/console panels, a real PyVista 3D viewport, stable scene
refreshes that avoid unnecessary clear/rebuild flicker, and a single persistent
GeoProjectDocument so new geometry is not lost when tools change.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import queue
from pathlib import Path
from typing import Any, Callable

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.benchmark_panel import (
    STEP_IFC_GUI_READINESS_CONTRACT,
    load_step_ifc_benchmark_readiness_payload,
)
from geoai_simkit.app.shell.modern_phase_theme import (
    build_modern_phase_ui_contract,
    modern_phase_workbench_stylesheet,
    phase_visual_token,
)
from geoai_simkit.app.shell.startup_dependency_dialog import build_startup_dependency_payload
from geoai_simkit.app.shell.gui_action_state import GUI_ACTION_STATE_CONTRACT, GuiActionDescriptor, GuiActionStateRegistry
from geoai_simkit.app.viewport.selection_controller import SelectionController
from geoai_simkit.app.viewport.tool_runtime import default_geometry_tool_runtime
from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.app.viewport.visualization_diagnostics import build_gui_visualization_diagnostic
from geoai_simkit.app.viewport.opengl_context_guard import (
    OPENGL_CONTEXT_GUARD_CONTRACT,
    apply_qt_vtk_opengl_policy,
    build_default_qt_vtk_opengl_policy,
)
from geoai_simkit.core.gui_workflow_module_spec import GUI_WORKFLOW_MODULE_SPEC_CONTRACT, build_gui_workflow_module_payload
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.cad_structure_workflow import (
    CAD_STRUCTURE_WORKFLOW_CONTRACT,
    apply_structure_context_action,
    auto_assign_materials_by_geometry_role,
    auto_assign_materials_by_recognized_strata_and_structures,
    build_cad_structure_workflow_payload,
    build_structure_mouse_interaction_payload,
    context_actions_for_selection,
    ensure_default_engineering_materials,
    promote_geometry_to_structure,
    recommended_material_for_entity,
)
from geoai_simkit.app.tools.base import ToolContext
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.services.boolean_topology_lineage import build_boolean_topology_lineage, validate_boolean_topology_lineage
from geoai_simkit.core.cad_fem_preprocessor import CAD_FEM_PREPROCESSOR_CONTRACT
from geoai_simkit.core.step_ifc_native_benchmark import STEP_IFC_NATIVE_BENCHMARK_CONTRACT
from geoai_simkit.services.cad_facade_kernel import probe_cad_facade_kernel
from geoai_simkit.services.demo_project_runner import build_demo_catalog, load_demo_project, run_all_demo_calculations, run_demo_complete_calculation
from geoai_simkit.services.desktop_interaction_recording import build_desktop_interaction_recording_contract
from geoai_simkit.services.gmsh_occ_boolean_roundtrip import probe_gmsh_occ_boolean_roundtrip
from geoai_simkit.services.ifc_representation_expansion import expand_ifc_product_representations
from geoai_simkit.services.import_driven_model_assembly import (
    IMPORT_DRIVEN_ASSEMBLY_CONTRACT,
    build_import_driven_workflow_payload,
    run_import_driven_assembly,
)
from geoai_simkit.services.native_import_assembly import (
    NATIVE_IMPORT_ASSEMBLY_CONTRACT,
    build_native_import_assembly_payload,
    run_native_import_assembly,
)
from geoai_simkit.services.native_brep_serialization import probe_native_brep_capability
from geoai_simkit.services.native_runtime_verification import verify_native_desktop_runtime
from geoai_simkit.services.step_ifc_shape_import import probe_step_ifc_import_capability
from geoai_simkit.services.topology_material_phase_binding import bind_topology_material_phase, validate_topology_material_phase_bindings
from geoai_simkit.services.workbench_phase_service import build_workbench_phases, phase_workbench_ui_state




def _deferred_probe_payload(contract: str, probe_name: str, probe: Callable[[], Any] | None = None) -> dict[str, Any]:
    if os.environ.get("GEOAI_SIMKIT_PROBE_NATIVE_PAYLOAD", "").strip() == "1" and probe is not None:
        try:
            result = probe()
            return result.to_dict() if hasattr(result, "to_dict") else dict(result)
        except Exception as exc:  # pragma: no cover - host/native dependent
            return {"contract": contract, "status": "probe_failed", "probe": probe_name, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "contract": contract,
        "status": "deferred_to_startup_preflight",
        "probe": probe_name,
        "message": "Native/3D backend probing is deferred during GUI payload construction; set GEOAI_SIMKIT_PROBE_NATIVE_PAYLOAD=1 to probe immediately.",
    }

def _native_runtime_payload_for_gui() -> dict[str, Any]:
    # Importing native CAD modules such as gmsh/OCP/IfcOpenShell can leave
    # host-dependent runtime state behind in headless tests.  The GUI startup
    # still has the strict dependency preflight, while this static payload keeps
    # module-spec/readiness rendering cheap unless an explicit probe is asked for.
    if os.environ.get("GEOAI_SIMKIT_PROBE_NATIVE_PAYLOAD", "").strip() == "1":
        try:
            return verify_native_desktop_runtime().to_dict()
        except Exception as exc:  # pragma: no cover - host dependent
            return {"status": "probe_failed", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "contract": "geoai_simkit_native_runtime_verification_v1",
        "status": "deferred_to_startup_preflight",
        "desktop_runtime_ready": None,
        "native_brep_certification_possible": None,
        "exact_step_import_possible": None,
        "exact_ifc_product_extraction_possible": None,
        "message": "Native CAD runtime probing is deferred in GUI payloads; set GEOAI_SIMKIT_PROBE_NATIVE_PAYLOAD=1 to probe immediately.",
    }


def build_phase_workbench_qt_payload(active_phase: str = "geology") -> dict[str, Any]:
    state = phase_workbench_ui_state(active_phase)
    modern_ui = build_modern_phase_ui_contract(str(state["active_phase"]))
    demo_catalog = build_demo_catalog()
    dependency_screen = build_startup_dependency_payload()
    return {
        "contract": "phase_workbench_qt_payload_v2",
        "version": __version__,
        "active_phase": state["active_phase"],
        "active_phase_label": state["active_phase_label"],
        "phase_tabs": state["phase_tabs"],
        "toolbar_groups": state["toolbar_groups"],
        "selection_filter": state["selection_filter"],
        "modern_ui": modern_ui,
        "phase_cards": modern_ui["phase_cards"],
        "layout_regions": [
            {"key": "top_navigation", "label": "紧凑顶部六阶段导航"},
            {"key": "floating_ribbon", "label": "可移动/可浮动图形化工具栏"},
            {"key": "dock_browser", "label": "可停靠模型树"},
            {"key": "viewport", "label": "持久化 3D CAD 视口"},
            {"key": "dock_inspector", "label": "属性与材料/阶段"},
            {"key": "dock_console", "label": "底部日志/诊断/Benchmark/Readiness"},
            {"key": "floating_help", "label": "可浮动说明工具窗"},
        ],
        "next_optimization_roadmap": modern_ui["roadmap"],
        "cad_ux_stabilization": {
            "contract": "cad_workbench_ux_stabilization_v1",
            "persistent_project_state": True,
            "scene_refresh_policy": "render only on explicit project/geometry changes; phase/tool changes do not clear the 3D scene",
            "flicker_reduction": True,
            "tool_activation_does_not_reset_model": True,
            "dockable_panels": True,
            "floating_toolbars": True,
            "top_navbar": True,
            "graphical_toolbar": True,
        },
        "startup_dependency_screen": dependency_screen,
        "dependency_preflight": dependency_screen.get("report", {}),
        "demo_center": {
            "contract": "phase_workbench_demo_center_v2",
            "catalog": demo_catalog,
            "default_demo_id": demo_catalog.get("default_demo_id", "foundation_pit_3d_beta"),
            "template_count": demo_catalog.get("template_count", len(demo_catalog.get("demos", []))),
            "templates": demo_catalog.get("templates", demo_catalog.get("demos", [])),
            "actions": ["load_demo_project", "run_complete_calculation", "export_demo_bundle", "run_all_templates"],
            "one_click_load": True,
            "complete_calculation": True,
        },
        "geometry_interaction": {
            "contract": "phase_workbench_geometry_interaction_v15",
            "runtime_tools": ["select", "point", "line", "surface", "block_box", "drag_move", "move", "copy", "rotate", "scale", "extrude", "cut", "boolean", "boolean_subtract", "apply_cad_features"],
            "viewport_runtime_bound": True,
            "mouse_creation": True,
            "snap_modes": ["grid", "endpoint", "midpoint", "wall_endpoint", "beam_endpoint", "anchor_endpoint", "stratum_boundary_intersection", "excavation_contour_intersection"],
            "constraint_snap_modes": ["horizontal", "vertical", "along_edge", "along_normal"],
            "constraint_locking": {"toolbar": True, "right_click_menu": True, "continuous_placement": ["point", "line", "surface", "block_box"], "unlock_action": True, "visualization": ["locked_edge_highlight", "locked_normal_arrow", "continuous_placement_trail", "unlock_feedback"]},
            "engineering_snap_targets": ["wall_endpoint", "beam_endpoint", "anchor_endpoint", "stratum_boundary_intersection", "excavation_contour_intersection"],
            "workplanes": ["XZ", "XY", "YZ"],
            "hover_highlight": True,
            "cursor_preview": True,
            "screen_space_crosshair": True,
            "visible_grid_snap_point": True,
            "endpoint_midpoint_snap_hints": True,
            "surface_right_click_completion_menu": True,
            "constraint_visual_feedback": {"locked_edge_highlight": True, "locked_normal_arrow": True, "continuous_placement_trail": True, "unlock_feedback": True},
            "created_entity_auto_selection": True,
            "right_click_selects_before_menu": True,
            "edit_handles": True,
            "numeric_coordinate_input": True,
            "multi_select": ["shift_add", "ctrl_toggle", "invert", "box_select_contract"],
            "transforms": ["move", "copy", "rotate_z", "scale", "drag_handle"],
            "solid_modeling": ["extrude_surface", "cut_axis_plane", "boolean_union_native_or_fallback", "boolean_subtract_native_or_fallback", "persistent_cad_topology_index"],
            "semantic_property_panel": True,
            "cad_facade": {"contract": "phase_workbench_cad_facade_v1", "backend_status": _deferred_probe_payload("geoai_simkit_cad_facade_capability_v1", "probe_cad_facade_kernel", probe_cad_facade_kernel), "native_cad_claimed": False, "native_brep_certified": False, "persistent_naming": True, "gui_status_required": True},
            "gmsh_occ_roundtrip": {"contract": "phase_workbench_gmsh_occ_roundtrip_v1", "backend_status": _deferred_probe_payload("geoai_simkit_gmsh_occ_boolean_roundtrip_capability_v1", "probe_gmsh_occ_boolean_roundtrip", probe_gmsh_occ_boolean_roundtrip), "physical_group_roundtrip": True, "mesh_tags": ["physical_volume", "material_id", "block_id"]},
            "step_ifc_shape_binding": {"contract": "phase_workbench_step_ifc_shape_binding_v1", "backend_status": _deferred_probe_payload("geoai_simkit_step_ifc_import_capability_v1", "probe_step_ifc_import_capability", probe_step_ifc_import_capability), "supported_formats": ["step", "stp", "ifc"], "surrogate_binding_is_explicit": True, "cad_shape_store_binding": True},
            "cad_shape_store": {"contract": "phase_workbench_cad_shape_store_v1", "stores": ["CadShapeRecord", "CadSerializedShapeReference", "CadTopologyRecord", "CadEntityBinding", "CadTopologyBinding", "CadTopologyLineageRecord", "CadOperationHistoryRecord"], "brep_reference_roundtrip": True, "save_load_persistent": True},
            "native_brep_serialization": {"contract": "phase_workbench_native_brep_serialization_v1", "backend_status": _deferred_probe_payload("geoai_simkit_native_brep_serialization_capability_v1", "probe_native_brep_capability", probe_native_brep_capability), "native_certified_requires": "real TopoDS_Shape serialization plus native topology enumeration"},
            "native_runtime_verification": {"contract": "phase_workbench_native_runtime_verification_v1", "backend_status": _native_runtime_payload_for_gui(), "certification_modes": ["contract", "native_brep_certified"]},
            "ifc_representation_expansion": {"contract": "phase_workbench_ifc_representation_expansion_v1", "representation_types": ["IfcExtrudedAreaSolid", "IfcBooleanResult", "IfcCsgSolid", "IfcFacetedBrep", "IfcAdvancedBrep"]},
            "boolean_topology_lineage": {"contract": "phase_workbench_boolean_topology_lineage_v1", "lineage_types": ["preserved", "split", "merge", "generated"]},
            "topology_material_phase_binding": {"contract": "phase_workbench_topology_material_phase_binding_v1", "binding_levels": ["solid", "face", "edge"], "after_step_ifc_import": True, "direct_face_edge_gui_assignment": True},
            "p7_topology_identity": {
                "contract": "phase_workbench_topology_identity_v1",
                "identity_layers": ["ModelEntity", "ShapeNode", "TopologyElement", "SelectionState", "OperationLineage"],
                "viewport_selection_key": "topology:{kind}:{shape_id}:{topology_id}",
                "headless_service": "geoai_simkit.services.topology_identity_service",
                "gui_contract": "face/edge picks carry topology_identity_key into property, material and phase panels",
            },
            "cad_fem_preprocessor": {
                "contract": CAD_FEM_PREPROCESSOR_CONTRACT,
                "headless_service": "geoai_simkit.services.cad_fem_preprocessor",
                "command": "BuildCadFemPreprocessorCommand",
                "produces": ["physical_groups", "boundary_candidates", "mesh_controls", "solver_requirements"],
                "gui_contract": "face/edge topology picks can be promoted to boundary conditions, loads, interfaces and mesh size controls before meshing/solving",
            },

            "import_driven_assembly": {
                "contract": IMPORT_DRIVEN_ASSEMBLY_CONTRACT,
                "headless_service": "geoai_simkit.services.import_driven_model_assembly",
                "recommended_primary_path": "borehole/mesh/STL/IFC/STEP import + support structure import + boolean subtract + remesh",
                "deprioritizes_mouse_cad": True,
                "payload": build_import_driven_workflow_payload(),
                "gui_panel": "导入拼接",
                "outputs": ["geology_volumes", "structure_cutters", "boolean_trimmed_soil_volumes", "physical_groups", "mesh_entity_map", "solver_readiness"],
            },
            "native_import_assembly": {
                "contract": NATIVE_IMPORT_ASSEMBLY_CONTRACT,
                "headless_service": "geoai_simkit.services.native_import_assembly",
                "payload": build_native_import_assembly_payload(),
                "gui_panel": "导入拼接",
                "supported_sources": ["borehole_csv", "stl", "msh", "vtu", "ifc", "step", "box_bounds"],
                "safe_without_pyvista": True,
                "button_action_contract": "gui_action_audit_v2",
                "file_dialog_policy": "generic_import_button_with_format_specific_filters",
                "direct_import_buttons": ["import_geology_model", "import_structure_model"],
                "direct_import_dispatch": "async_file_select_then_path_override_import",
            },
            "p85_step_ifc_native_benchmark": {
                "contract": STEP_IFC_NATIVE_BENCHMARK_CONTRACT,
                "headless_service": "geoai_simkit.services.step_ifc_native_benchmark",
                "cli": "tools/run_step_ifc_native_benchmark.py",
                "validates": ["native_step_ifc_import", "persistent_naming_stability", "physical_group_stability", "mesh_entity_map", "solver_region_map", "native_boolean_lineage_when_required"],
                "modes": ["native_certification", "fallback_dry_run"],
                "gui_contract": "real STEP/IFC benchmark reports can be loaded by the benchmark/readiness panels without claiming native certification on fallback runs",
            },
            "right_click_structure_actions": True,
            "structure_mouse_interaction": build_structure_mouse_interaction_payload(load_demo_project(demo_catalog.get("default_demo_id", "foundation_pit_3d_beta"))),
            "mouse_context_menu": {"contract": CAD_STRUCTURE_WORKFLOW_CONTRACT, "actions": ["create_point_line_surface_volume", "promote_selection_to_structure", "assign_material_to_selection"]},
            "undo_redo": True,
        },
        "workflow_module_specs": build_gui_workflow_module_payload(),
        "cad_structure_workflow": build_cad_structure_workflow_payload(load_demo_project(demo_catalog.get("default_demo_id", "foundation_pit_3d_beta"))),
        "benchmark_readiness_panel": {
            "contract": STEP_IFC_GUI_READINESS_CONTRACT,
            "report_loader": "geoai_simkit.app.shell.benchmark_panel.load_step_ifc_benchmark_readiness_payload",
            "bottom_tab": True,
            "clickable_fix_suggestions": True,
            "case_blockers_to_actions": True,
        },
        "gui_cleanup": {
            "contract": "geoai_simkit_gui_cleanup_p152_v1",
            "right_dock_tabs": ["属性", "语义/材料/阶段", "导入拼接", "FEM分析流程", "结构建模", "材料库"],
            "bottom_tabs": ["日志", "3D诊断", "Readiness", "Benchmark", "修复建议", "计算链", "Demo", "依赖自检", "模块界面", "交互自检"],
            "floating_help_dock": True,
            "verbose_inline_descriptions_removed": True,
            "centralized_logs": True,
            "right_side_explanations_are_floating": True,
        },
        "opengl_context_guard": {
            "contract": OPENGL_CONTEXT_GUARD_CONTRACT,
            "policy": build_default_qt_vtk_opengl_policy().to_dict(),
            "fixes": [
                "set AA_ShareOpenGLContexts before QApplication creation",
                "install conservative QSurfaceFormat before QApplication creation",
                "skip rendering while Qt/VTK widget is hidden, closing or not exposed",
                "suspend repeated renders after VTK/OpenGL context failure",
                "document GEOAI_SIMKIT_DISABLE_PYVISTA=1 and GEOAI_SIMKIT_QT_OPENGL=software fallbacks",
            ],
        },
        "desktop_interaction_recording": build_desktop_interaction_recording_contract().to_dict(),
        "imported_geology_fem_analysis": {
            "contract": "geoai_simkit_imported_geology_fem_analysis_workflow_v1",
            "headless_service": "geoai_simkit.services.geology_fem_analysis_workflow",
            "gui_panel": "FEM分析流程",
            "flow_steps": ["导入模型准备", "FEM网格质量/材料状态检查", "有限元网格划分", "自动地应力配置", "有限元求解", "求解结果查看"],
            "progress_events": True,
            "background_long_running_action": "fem_run_complete_analysis",
            "result_views": ["displacement", "uz", "cell_stress_zz", "cell_von_mises", "cell_equivalent_strain"],
        },
        "gui_action_audit": {
            "contract": GUI_ACTION_STATE_CONTRACT,
            "bottom_tab": "交互自检",
            "rule": "Every user-facing production button must have an action_id, tooltip/status text and a testable expected_effect.",
            "critical_actions": ["import_geology_model", "import_structure_model", "run_import_driven_assembly", "run_native_import_assembly", "fem_check_imported_geology", "fem_generate_or_repair_mesh", "fem_solve_to_steady_state", "fem_refresh_result_view", "fem_run_complete_analysis", "assign_material_to_selection", "run_gui_button_smoke"],
        },
        "launcher_fix": {"legacy_flat_editor_default": False, "default_when_pyvista_missing": "launch_phase_workbench_qt_qt_only", "strict_dependency_preflight": True, "qt_only_fallback": True},
    }


def launch_phase_workbench_qt() -> None:
    from PySide6 import QtCore, QtGui, QtWidgets

    opengl_policy_result = apply_qt_vtk_opengl_policy(QtCore, QtGui, QtWidgets)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet(modern_phase_workbench_stylesheet())

    pyvista_import_error = ""
    QtInteractor = None
    PyVistaViewportAdapter = None
    if os.environ.get("GEOAI_SIMKIT_DISABLE_PYVISTA", "").strip() != "1":
        try:
            from pyvistaqt import QtInteractor as _QtInteractor
            from geoai_simkit.app.viewport.pyvista_adapter import PyVistaViewportAdapter as _PyVistaViewportAdapter
            QtInteractor = _QtInteractor
            PyVistaViewportAdapter = _PyVistaViewportAdapter
        except Exception as exc:  # pragma: no cover - host/OpenGL dependent
            pyvista_import_error = f"{type(exc).__name__}: {exc}"
            os.environ["GEOAI_SIMKIT_LAST_PYVISTA_LAUNCH_ERROR"] = pyvista_import_error
    else:
        pyvista_import_error = "GEOAI_SIMKIT_DISABLE_PYVISTA=1"

    def _icon(widget: QtWidgets.QWidget, name: str) -> QtGui.QIcon:
        # QStyle.StandardPixmap deliberately has no SP_ArrowCursor.  Keep all
        # icon lookups lazy and string-based so PySide/Qt minor-version enum
        # differences cannot abort GUI startup during toolbar construction.
        mapping = {
            "select": ("SP_ArrowForward", "SP_ArrowRight", "SP_FileDialogDetailedView"),
            "point": ("SP_DialogYesButton", "SP_DialogApplyButton"),
            "line": ("SP_TitleBarShadeButton", "SP_ArrowRight"),
            "surface": ("SP_FileDialogDetailedView", "SP_FileIcon"),
            "block_box": ("SP_DesktopIcon", "SP_DirIcon"),
            "run": ("SP_MediaPlay", "SP_ArrowForward"),
            "export": ("SP_DriveFDIcon", "SP_DialogSaveButton"),
            "undo": ("SP_ArrowBack", "SP_ArrowLeft"),
            "redo": ("SP_ArrowForward", "SP_ArrowRight"),
            "settings": ("SP_FileDialogInfoView", "SP_MessageBoxInformation"),
            "default": ("SP_CommandLink", "SP_FileIcon"),
        }
        for enum_name in mapping.get(name, mapping["default"]):
            enum = getattr(QtWidgets.QStyle.StandardPixmap, enum_name, None)
            if enum is None:
                enum = getattr(QtWidgets.QStyle, enum_name, None)
            if enum is not None:
                try:
                    return widget.style().standardIcon(enum)
                except Exception:
                    continue
        return QtGui.QIcon()

    class PhaseWorkbenchWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("geoai-modern-cad-workbench")
            self.setWindowTitle(f"GeoAI SimKit {__version__} — CAD 六阶段建模工作台")
            self.resize(1680, 980)
            self.setDockOptions(
                QtWidgets.QMainWindow.DockOption.AllowNestedDocks
                | QtWidgets.QMainWindow.DockOption.AllowTabbedDocks
                | QtWidgets.QMainWindow.DockOption.AnimatedDocks
            )
            self.active_phase = "geology"
            self.selected_demo_id = "foundation_pit_3d_beta"
            self.current_demo_project = GeoProjectDocument.create_empty(name="空白工程 - 请导入地质/网格模型或加载模板")
            self.current_demo_project.metadata.update({"startup_empty_scene": True, "template_loaded": False})
            self.last_demo_run: dict[str, Any] | None = None
            self.last_action_error: str | None = None
            self._operation_running = False
            self._closing = False
            self.opengl_policy_result = dict(opengl_policy_result)
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="geoai-cad-workbench")
            self._active_future = None
            self._active_timer: Any = None
            self._analysis_progress_events: queue.Queue[dict[str, Any]] = queue.Queue()
            self._last_render_revision = -1
            self._scene_revision = 0
            self._suspend_property_sync = False
            self.command_stack = CommandStack()
            self.viewport_state = ViewportState()
            self.selection_controller = SelectionController()
            self.tool_runtime = None
            self.gui_action_registry: list[dict[str, Any]] = []
            self._gui_action_widgets: dict[str, Any] = {}
            self.gui_action_state = GuiActionStateRegistry()
            self._last_gui_action_status: dict[str, str] = {}
            # Keep non-modal QFileDialog instances alive.  Without a strong
            # reference, PySide can destroy the dialog immediately; with modal
            # exec() the dialog can also become invisible behind VTK/OpenGL on
            # Windows.  1.6.3 uses non-modal dialogs plus explicit callbacks.
            self._active_file_dialogs: dict[str, Any] = {}
            self._build_ui()
            self._setup_interactive_modeling_runtime()
            self._set_phase("geology", render=False)
            self._render_scene(reset_camera=True, force=True, reason="startup")

        # ---------- UI construction ----------
        def _build_ui(self) -> None:
            from PySide6 import QtCore, QtWidgets

            self._build_menu_bar()
            self._build_top_navigation_toolbar()
            self._build_contextual_ribbon()
            self._build_modeling_toolbar()
            self._build_viewport_central_widget()
            self._build_docks()
            self.statusBar().showMessage("CAD 工作台已启动：工具切换不会重置模型，视口只在几何变化时刷新。")

        def _build_menu_bar(self) -> None:
            file_menu = self.menuBar().addMenu("文件")
            load = file_menu.addAction("加载 Demo 模板")
            load.triggered.connect(self._load_demo_project)
            export = file_menu.addAction("导出审查包")
            export.triggered.connect(self._export_demo_bundle)
            view_menu = self.menuBar().addMenu("视图")
            view_menu.addAction("重置相机").triggered.connect(lambda: self._reset_camera())
            view_menu.addAction("刷新 3D 场景").triggered.connect(lambda: self._render_scene(reset_camera=False, force=True, reason="manual_refresh"))

        def _build_top_navigation_toolbar(self) -> None:
            from PySide6 import QtCore
            self.phase_toolbar = self.addToolBar("主流程")
            self.phase_toolbar.setObjectName("cad-top-navigation-toolbar-slim")
            self.phase_toolbar.setMovable(False)
            self.phase_toolbar.setFloatable(False)
            self.phase_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.phase_actions = {}
            actions = [
                ("导入拼接", "导入地质/结构并执行差分重网格", lambda: self._focus_right_tab("导入拼接")),
                ("材料库", "管理土体、梁、锚杆、墙和界面材料", lambda: self._focus_right_tab("材料库")),
                ("FEM分析", "导入地质模型 FEM 检查、网格、求解与结果查看", lambda: self._focus_right_tab("FEM分析流程")),
                ("Readiness", "查看求解前检查与阻塞项", lambda: self._focus_bottom_tab("Readiness")),
                ("交互自检", "检查当前所有按钮是否接入动作系统", lambda: self._focus_bottom_tab("交互自检")),
                ("刷新", "刷新当前视图和状态面板", lambda: self._run_gui_action("refresh_workbench_state", self._refresh_workbench_state_from_gui)),
            ]
            for text, tip, callback in actions:
                action = self.phase_toolbar.addAction(_icon(self, "settings"), text)
                action.setToolTip(tip)
                action.triggered.connect(callback)

        def _focus_tab_by_text(self, tabs: Any, text: str) -> bool:
            if tabs is None:
                return False
            for index in range(tabs.count()):
                if str(tabs.tabText(index)).strip() == str(text).strip():
                    tabs.setCurrentIndex(index)
                    return True
            return False

        def _focus_right_tab(self, text: str) -> str:
            ok = self._focus_tab_by_text(getattr(self, "right", None), text)
            return f"right tab {'focused' if ok else 'not found'}: {text}"

        def _focus_bottom_tab(self, text: str) -> str:
            ok = self._focus_tab_by_text(getattr(self, "bottom", None), text)
            return f"bottom tab {'focused' if ok else 'not found'}: {text}"

        def _refresh_workbench_state_from_gui(self) -> str:
            self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
            self._populate_gui_action_audit_table()
            self._mark_scene_dirty("refresh_workbench_state")
            self._render_scene(reset_camera=False, force=True, reason="refresh_workbench_state")
            return "refreshed"

        def _build_contextual_ribbon(self) -> None:
            # 1.6.5 fully disables the historical contextual ribbon.  Earlier
            # 1.6.4 code removed the toolbar widget but still called
            # _rebuild_ribbon() during _set_phase(), which raised
            # AttributeError: 'PhaseWorkbenchWindow' object has no attribute
            # 'ribbon' on startup.  Keep explicit sentinel attributes so any
            # remaining legacy routes are safe no-ops instead of startup blockers.
            self.ribbon = None
            self.ribbon_actions = []

        def _build_modeling_toolbar(self) -> None:
            # Mouse-CAD buttons are intentionally removed from the top toolbar.
            # Import-driven geology/structure assembly is now the primary path;
            # advanced sketch tools remain in the right "结构建模" panel.
            self.modeling_bar = None

        def _build_viewport_central_widget(self) -> None:
            center = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(center)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(4)
            self.setCentralWidget(center)
            self.viewport_backend = "pyvista"
            if QtInteractor is not None and PyVistaViewportAdapter is not None:
                try:
                    self.viewport_widget = QtInteractor(center)
                    self.viewport_widget.setObjectName("phase-workbench-3d-model-view")
                    self.viewport_widget.setMinimumSize(760, 560)
                    layout.addWidget(self.viewport_widget, 1)
                    self.viewport_adapter = PyVistaViewportAdapter(
                        plotter=self.viewport_widget,
                        refresh_callback=self._after_viewport_command,
                        status_callback=lambda message: self.statusBar().showMessage(str(message)),
                        selection_callback=self._on_viewport_selection_changed,
                    )
                except Exception as exc:  # pragma: no cover - host/OpenGL dependent
                    self.viewport_backend = "qt_only"
                    os.environ["GEOAI_SIMKIT_LAST_PYVISTA_LAUNCH_ERROR"] = f"{type(exc).__name__}: {exc}"
                    from geoai_simkit.app.viewport.qt_only_adapter import QtOnlyViewportAdapter
                    self.viewport_widget = QtWidgets.QPlainTextEdit(center)
                    self.viewport_widget.setReadOnly(True)
                    self.viewport_widget.setObjectName("phase-workbench-qt-only-view")
                    self.viewport_widget.setMinimumSize(760, 560)
                    self.viewport_widget.setPlainText(
                        "Qt-only 工作台已启动。PyVista/VTK OpenGL 视口创建失败，"
                        "但导入拼接、材料、网格、Readiness、Benchmark 面板仍可使用。\n\n"
                        f"PyVista error: {os.environ.get('GEOAI_SIMKIT_LAST_PYVISTA_LAUNCH_ERROR', '')}"
                    )
                    layout.addWidget(self.viewport_widget, 1)
                    self.viewport_adapter = QtOnlyViewportAdapter(
                        widget=self.viewport_widget,
                        refresh_callback=self._after_viewport_command,
                        status_callback=lambda message: self.statusBar().showMessage(str(message)),
                        selection_callback=self._on_viewport_selection_changed,
                    )
            else:
                self.viewport_backend = "qt_only"
                from geoai_simkit.app.viewport.qt_only_adapter import QtOnlyViewportAdapter
                self.viewport_widget = QtWidgets.QPlainTextEdit(center)
                self.viewport_widget.setReadOnly(True)
                self.viewport_widget.setObjectName("phase-workbench-qt-only-view")
                self.viewport_widget.setMinimumSize(760, 560)
                self.viewport_widget.setPlainText(
                    "Qt-only 工作台已启动。PyVista/VTK OpenGL 视口已禁用或导入失败，"
                    "请优先使用导入拼接、网格、Readiness 与 Benchmark 面板。\n\n"
                    f"原因: {pyvista_import_error}"
                )
                layout.addWidget(self.viewport_widget, 1)
                self.viewport_adapter = QtOnlyViewportAdapter(
                    widget=self.viewport_widget,
                    refresh_callback=self._after_viewport_command,
                    status_callback=lambda message: self.statusBar().showMessage(str(message)),
                    selection_callback=self._on_viewport_selection_changed,
                )
            self.viewport_adapter.bind_context_menu_callback(self._show_viewport_context_menu)

        def _build_docks(self) -> None:
            from PySide6 import QtCore
            self.left = QtWidgets.QTreeWidget()
            self.left.setHeaderLabels(["模型对象", "类别"])
            self.left.itemSelectionChanged.connect(self._on_object_tree_selection_changed)
            self.left_dock = self._dock("模型浏览器", self.left, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)

            self.right = QtWidgets.QTabWidget()
            self.properties = QtWidgets.QTableWidget(0, 2)
            self.properties.setHorizontalHeaderLabels(["属性", "值"])
            self.properties.horizontalHeader().setStretchLastSection(True)
            self.property_editor = self._build_property_editor()
            self.right.addTab(self.properties, "属性")
            self.right.addTab(self.property_editor, "语义/材料/阶段")
            self.import_assembly_panel = self._build_import_assembly_panel()
            self.right.addTab(self.import_assembly_panel, "导入拼接")
            self.fem_analysis_panel = self._build_fem_analysis_panel()
            self.right.addTab(self.fem_analysis_panel, "FEM分析流程")
            self.structure_modeling_panel = self._build_structure_modeling_panel()
            self.right.addTab(self.structure_modeling_panel, "结构建模")
            self.material_library_panel = self._build_material_library_panel()
            self.right.addTab(self.material_library_panel, "材料库")
            self.right_dock = self._dock("检查器", self.right, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)

            self.bottom = QtWidgets.QTabWidget()
            self.messages = QtWidgets.QPlainTextEdit(); self.messages.setReadOnly(True)
            self.diagnostics = QtWidgets.QPlainTextEdit(); self.diagnostics.setReadOnly(True)
            self.readiness = QtWidgets.QTableWidget(0, 2); self.readiness.setHorizontalHeaderLabels(["Item", "Value"]); self.readiness.horizontalHeader().setStretchLastSection(True)
            self.benchmark_panel = self._build_benchmark_panel()
            self.fix_panel = self._build_fix_suggestion_panel()
            self.workflow = QtWidgets.QPlainTextEdit(); self.workflow.setReadOnly(True)
            self.demo_panel = self._build_demo_panel()
            self.dependency_table = QtWidgets.QTableWidget(0, 5); self.dependency_table.setHorizontalHeaderLabels(["状态", "模块", "依赖", "版本", "用途"]); self.dependency_table.horizontalHeader().setStretchLastSection(True)
            self.workflow_spec = self._build_workflow_spec_panel()
            self.gui_action_audit_panel = self._build_gui_action_audit_panel()
            self.bottom.addTab(self.messages, "日志")
            self.bottom.addTab(self.diagnostics, "3D 诊断")
            self.bottom.addTab(self.readiness, "Readiness")
            self.bottom.addTab(self.benchmark_panel, "Benchmark")
            self.bottom.addTab(self.fix_panel, "修复建议")
            self.bottom.addTab(self.workflow, "计算链")
            self.bottom.addTab(self.demo_panel, "Demo")
            self.bottom.addTab(self.dependency_table, "依赖自检")
            self.bottom.addTab(self.workflow_spec, "模块界面")
            self.bottom.addTab(self.gui_action_audit_panel, "交互自检")
            self.bottom_dock = self._dock("日志 / Readiness / Benchmark / 交互自检", self.bottom, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)

            self.help_text = QtWidgets.QPlainTextEdit(); self.help_text.setReadOnly(True)
            self.help_text.setPlainText("选择模型或 Benchmark 失败项后，这里显示对应修复建议。")
            self.help_dock = self._dock("说明 / 修复说明", self.help_text, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
            self.help_dock.setFloating(True)
            self.help_dock.resize(440, 520)
            self._populate_gui_action_audit_table()

        def _dock(self, title: str, widget: Any, area: Any) -> Any:
            dock = QtWidgets.QDockWidget(title, self)
            dock.setObjectName(f"cad-dock-{title}")
            dock.setWidget(widget)
            dock.setAllowedAreas(
                QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
                | QtCore.Qt.DockWidgetArea.RightDockWidgetArea
                | QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
            )
            dock.setFeatures(
                QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
                | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
            self.addDockWidget(area, dock)
            return dock

        def _build_property_editor(self) -> Any:
            editor = QtWidgets.QWidget()
            layout = QtWidgets.QFormLayout(editor)
            self.entity_id_input = QtWidgets.QLineEdit()
            self.entity_name_input = QtWidgets.QLineEdit()
            self.entity_name_input.setPlaceholderText("选中对象名称 / 地层显示名")
            self.entity_type_combo = QtWidgets.QComboBox(); self.entity_type_combo.addItems(["point", "curve", "surface", "volume"])
            self.coord_x = self._spin(-1e6, 1e6, 0.0); self.coord_y = self._spin(-1e6, 1e6, 0.0); self.coord_z = self._spin(-1e6, 1e6, 0.0)
            self.dim_x = self._spin(0.0, 1e6, 1.0); self.dim_y = self._spin(0.0, 1e6, 1.0); self.dim_z = self._spin(0.0, 1e6, 1.0)
            self.semantic_combo = QtWidgets.QComboBox(); self.semantic_combo.addItems(["", "soil_volume", "excavation", "wall", "plate", "beam", "anchor", "pile", "interface", "control_point"])
            self.material_combo = QtWidgets.QComboBox(); self.material_combo.setEditable(True); self.material_combo.addItems(["", "sand", "clay", "concrete", "steel", "interface_default"])
            self.topology_id_input = QtWidgets.QLineEdit()
            self.topology_phase_input = QtWidgets.QLineEdit(); self.topology_phase_input.setPlaceholderText("initial, excavation_1, support_1")
            self.topology_role_combo = QtWidgets.QComboBox(); self.topology_role_combo.setEditable(True); self.topology_role_combo.addItems(["", "boundary", "interface", "excavation_face", "support_contact", "monitoring_edge"])
            for label, widget in (("实体 ID", self.entity_id_input), ("名称", self.entity_name_input), ("实体类型", self.entity_type_combo), ("X", self.coord_x), ("Y", self.coord_y), ("Z", self.coord_z), ("宽 X", self.dim_x), ("深 Y", self.dim_y), ("高 Z", self.dim_z), ("语义", self.semantic_combo), ("材料", self.material_combo), ("Face/Edge/Solid ID", self.topology_id_input), ("阶段 IDs", self.topology_phase_input), ("拓扑角色", self.topology_role_combo)):
                layout.addRow(label, widget)
            self.apply_object_info_button = QtWidgets.QPushButton("应用名称/材料")
            self.apply_coordinates_button = QtWidgets.QPushButton("应用坐标/尺寸")
            self.apply_semantic_button = QtWidgets.QPushButton("赋语义/材料")
            self.apply_topology_binding_button = QtWidgets.QPushButton("赋 Face/Edge 材料/阶段")
            self.apply_object_info_button.clicked.connect(lambda _checked=False: self._run_gui_action("apply_object_name_material", self._apply_object_name_material))
            self.apply_coordinates_button.clicked.connect(lambda _checked=False: self._run_gui_action("apply_numeric_coordinates", self._apply_numeric_coordinates))
            self.apply_semantic_button.clicked.connect(lambda _checked=False: self._run_gui_action("apply_semantic_material", self._apply_semantic_material))
            self.apply_topology_binding_button.clicked.connect(lambda _checked=False: self._run_gui_action("apply_topology_material_phase", self._apply_topology_material_phase))
            self._register_gui_button(self.apply_object_info_button, "apply_object_name_material", "给当前选中对象修改名称并绑定材料", panel="属性", expected_effect="更新模型树、属性面板和视口选中对象 metadata")
            self._register_gui_button(self.apply_coordinates_button, "apply_numeric_coordinates", "把坐标/尺寸输入应用到当前实体", panel="属性", expected_effect="修改实体几何参数并刷新视口")
            self._register_gui_button(self.apply_semantic_button, "apply_semantic_material", "给当前实体赋语义和材料", panel="语义/材料/阶段", expected_effect="更新实体 semantic/material metadata")
            self._register_gui_button(self.apply_topology_binding_button, "apply_topology_material_phase", "给选中的 face/edge/solid 绑定材料和阶段", panel="语义/材料/阶段", expected_effect="更新拓扑级材料/阶段绑定")
            layout.addRow(self.apply_object_info_button)
            layout.addRow(self.apply_coordinates_button)
            layout.addRow(self.apply_semantic_button)
            layout.addRow(self.apply_topology_binding_button)
            return editor

        def _spin(self, lo: float, hi: float, value: float) -> Any:
            box = QtWidgets.QDoubleSpinBox(); box.setRange(lo, hi); box.setDecimals(3); box.setValue(value); return box

        def _register_gui_button(self, button: Any, action_id: str, description: str, *, panel: str = "", expected_effect: str = "", dialog_policy: str = "none") -> Any:
            """Register a user-facing button for interaction audit and status reporting.

            The audit registry records which GUI controls are expected to perform
            project-changing actions.  Dialog policy is explicit so import
            buttons can be audited: direct import buttons should open a file
            chooser every time, while auto-import buttons may use the existing
            path if present.
            """
            try:
                button.setObjectName(f"geoai-action-{action_id}")
                button.setProperty("geoai_action_id", str(action_id))
                button.setProperty("geoai_action_panel", str(panel))
                button.setEnabled(True)
                button.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
                button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            except Exception:
                pass
            if hasattr(button, "setToolTip") and description:
                try:
                    button.setToolTip(description)
                except Exception:
                    pass
            row = {
                "action_id": str(action_id),
                "label": str(button.text()) if hasattr(button, "text") else str(action_id),
                "panel": str(panel),
                "description": str(description),
                "expected_effect": str(expected_effect),
                "object_name": f"geoai-action-{action_id}",
                "connected": True,
                "dialog_policy": str(dialog_policy),
            }
            self.gui_action_registry.append(row)
            self._gui_action_widgets[str(action_id)] = button
            try:
                self.gui_action_state.register(GuiActionDescriptor(action_id=str(action_id), label=str(row["label"]), panel=str(panel), expected_effect=str(expected_effect), dialog_policy=str(dialog_policy), connected=True))
            except Exception:
                pass
            return button

        def _set_gui_action_status(self, action_id: str, message: str, *, ok: bool | None = None) -> None:
            prefix = "[OK]" if ok is True else ("[FAIL]" if ok is False else "[INFO]")
            line = f"{prefix} {action_id}: {message}"
            self._last_gui_action_status[str(action_id)] = line
            try:
                self.gui_action_state.set_status(str(action_id), line)
            except Exception:
                pass
            try:
                self.statusBar().showMessage(line)
            except Exception:
                pass
            if hasattr(self, "messages"):
                self.messages.appendPlainText(line)
            if hasattr(self, "gui_action_audit_table"):
                self._populate_gui_action_audit_table()

        def _run_gui_action(self, action_id: str, callback: Callable[[], Any]) -> None:
            self._set_gui_action_status(action_id, "started")
            try:
                result = callback()
            except Exception as exc:
                self._set_gui_action_status(action_id, f"{type(exc).__name__}: {exc}", ok=False)
                return
            if result is None:
                result = "done"
            self._set_gui_action_status(action_id, str(result), ok=True)

        def _build_gui_action_audit_panel(self) -> Any:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            top = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel("交互动作自检：列出关键按钮、所属面板、预期效果和最近状态。新增按钮应进入此表，避免出现点击无响应。")
            label.setWordWrap(True)
            refresh = QtWidgets.QPushButton("刷新交互自检")
            refresh.clicked.connect(self._populate_gui_action_audit_table)
            self._register_gui_button(refresh, "refresh_gui_action_audit", "刷新按钮动作自检表", panel="交互自检", expected_effect="更新交互动作列表")
            smoke = QtWidgets.QPushButton("按钮烟测")
            smoke.clicked.connect(lambda _checked=False: self._run_gui_action("run_gui_button_smoke", self._run_gui_button_smoke_from_gui))
            self._register_gui_button(smoke, "run_gui_button_smoke", "检查所有关键按钮是否在新状态机中注册、启用、具备 objectName 与动作状态", panel="交互自检", expected_effect="输出按钮运行期可用性报告")
            top.addWidget(label, 1)
            top.addWidget(refresh)
            top.addWidget(smoke)
            layout.addLayout(top)
            self.gui_action_audit_table = QtWidgets.QTableWidget(0, 7)
            self.gui_action_audit_table.setHorizontalHeaderLabels(["Action", "Label", "Panel", "Expected", "Dialog", "Connected", "Last status"])
            self.gui_action_audit_table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.gui_action_audit_table, 1)
            return panel

        def _populate_gui_action_audit_table(self) -> None:
            if not hasattr(self, "gui_action_audit_table"):
                return
            rows = list(getattr(self, "gui_action_registry", []) or [])
            self.gui_action_audit_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                values = [
                    row.get("action_id", ""),
                    row.get("label", ""),
                    row.get("panel", ""),
                    row.get("expected_effect", ""),
                    row.get("dialog_policy", "none"),
                    "yes" if row.get("connected") else "no",
                    self._last_gui_action_status.get(str(row.get("action_id", "")), "not clicked"),
                ]
                for c, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    item.setData(256, dict(row))
                    self.gui_action_audit_table.setItem(r, c, item)


        def _build_import_assembly_panel(self) -> Any:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)

            geology_filter = "地质/网格模型 (*.csv *.stl *.msh *.vtu *.ifc *.step *.stp);;钻孔 CSV (*.csv);;表面模型 STL (*.stl);;网格模型 MSH/VTU (*.msh *.vtu);;IFC/STEP (*.ifc *.step *.stp);;All Files (*)"
            structure_filter = "结构/围护模型 (*.stl *.ifc *.step *.stp *.msh *.vtu);;STL (*.stl);;IFC/STEP (*.ifc *.step *.stp);;网格模型 MSH/VTU (*.msh *.vtu);;All Files (*)"

            geology_box = QtWidgets.QGroupBox("1. 导入地质/网格模型")
            geology_layout = QtWidgets.QGridLayout(geology_box)
            self.import_geology_path = QtWidgets.QLineEdit()
            self.import_geology_path.setPlaceholderText("boreholes.csv / geology.stl / geology.msh / geology.vtu / geology.ifc / geology.step")
            browse_geo = QtWidgets.QPushButton("浏览")
            browse_geo.clicked.connect(lambda _checked=False: self._browse_import_path(self.import_geology_path, "选择地质/网格源", geology_filter, action_id="browse_geology_source"))
            self._register_gui_button(browse_geo, "browse_geology_source", "选择钻孔 CSV、STL、MSH、VTU、IFC 或 STEP 地质源", panel="导入拼接", expected_effect="把文件路径写入地质源输入框", dialog_policy="open_dialog")
            import_geo = QtWidgets.QPushButton("导入地质/钻孔")
            import_geo.clicked.connect(lambda _checked=False: self._select_import_file_then_run("import_geology_model", self.import_geology_path, "选择地质/网格源", geology_filter, lambda path: self._import_geology_source_from_gui(path_override=path), prefer_existing_path=False))
            self._register_gui_button(import_geo, "import_geology_model", "打开文件框并按后缀导入钻孔表或地质/网格模型", panel="导入拼接", expected_effect="生成或替换当前地质项目，并刷新网格/Readiness 输入", dialog_policy="always_open")
            import_geo_path = QtWidgets.QPushButton("按路径导入")
            import_geo_path.clicked.connect(lambda _checked=False: self._import_geology_auto_clicked())
            self._register_gui_button(import_geo_path, "import_geology_auto", "使用路径框内容自动导入；路径为空时打开同一文件框", panel="导入拼接", expected_effect="生成或替换当前地质项目", dialog_policy="if_empty")
            geology_layout.addWidget(self.import_geology_path, 0, 0, 1, 3)
            geology_layout.addWidget(browse_geo, 0, 3)
            geology_layout.addWidget(import_geo, 1, 0, 1, 2)
            geology_layout.addWidget(import_geo_path, 1, 2, 1, 2)
            layout.addWidget(geology_box)

            structure_file_box = QtWidgets.QGroupBox("2A. 导入围护/结构模型")
            file_layout = QtWidgets.QGridLayout(structure_file_box)
            self.import_structure_path = QtWidgets.QLineEdit()
            self.import_structure_path.setPlaceholderText("structure.ifc / wall.stl / support.step / structure.msh / structure.vtu")
            browse_structure = QtWidgets.QPushButton("浏览")
            browse_structure.clicked.connect(lambda _checked=False: self._browse_import_path(self.import_structure_path, "选择结构源", structure_filter, action_id="browse_structure_source"))
            self._register_gui_button(browse_structure, "browse_structure_source", "选择围护结构、支撑、锚杆、开挖体等结构源文件", panel="导入拼接", expected_effect="把结构文件路径写入结构源输入框", dialog_policy="open_dialog")
            self.import_structure_kind_combo = QtWidgets.QComboBox(); self.import_structure_kind_combo.setEditable(True)
            self.import_structure_kind_combo.addItems(["diaphragm_wall", "retaining_wall", "basement_wall", "strut", "beam", "anchor", "pile", "excavation", "void"])
            self.import_structure_material_edit = QtWidgets.QLineEdit("concrete_c30")
            register_file = QtWidgets.QPushButton("导入结构/围护")
            register_file.clicked.connect(lambda _checked=False: self._select_import_file_then_run("import_structure_model", self.import_structure_path, "选择结构/围护模型", structure_filter, lambda path: self._register_imported_structure_file_from_gui(path_override=path), prefer_existing_path=False))
            self._register_gui_button(register_file, "import_structure_model", "打开文件框并按后缀导入围护结构、支撑或开挖体", panel="导入拼接", expected_effect="把结构或开挖体注册为 boolean cutter", dialog_policy="always_open")
            register_file_path = QtWidgets.QPushButton("按路径导入")
            register_file_path.clicked.connect(lambda _checked=False: self._import_structure_auto_clicked())
            self._register_gui_button(register_file_path, "import_structure_auto", "使用路径框内容导入结构；路径为空时打开同一文件框", panel="导入拼接", expected_effect="把结构或开挖体注册为 boolean cutter", dialog_policy="if_empty")
            file_layout.addWidget(self.import_structure_path, 0, 0, 1, 3)
            file_layout.addWidget(browse_structure, 0, 3)
            file_layout.addWidget(register_file, 1, 0, 1, 2)
            file_layout.addWidget(register_file_path, 1, 2, 1, 2)
            file_layout.addWidget(QtWidgets.QLabel("类型"), 2, 0)
            file_layout.addWidget(self.import_structure_kind_combo, 2, 1)
            file_layout.addWidget(QtWidgets.QLabel("材料"), 2, 2)
            file_layout.addWidget(self.import_structure_material_edit, 2, 3)
            layout.addWidget(structure_file_box)

            box = QtWidgets.QGroupBox("2B. 注册结构包围盒")
            box_layout = QtWidgets.QGridLayout(box)
            self.structure_bounds_edit = QtWidgets.QLineEdit("2,4,-1,11,-12,0")
            self.structure_kind_combo = QtWidgets.QComboBox(); self.structure_kind_combo.setEditable(True)
            self.structure_kind_combo.addItems(["diaphragm_wall", "retaining_wall", "excavation", "void", "basement", "strut", "anchor", "pile"])
            self.structure_material_edit = QtWidgets.QLineEdit("concrete_c30")
            register_box = QtWidgets.QPushButton("注册结构盒")
            register_box.clicked.connect(lambda _checked=False: self._run_gui_action("register_structure_box", self._register_structure_box_from_gui))
            self._register_gui_button(register_box, "register_structure_box", "根据 bounds 注册结构/开挖包围盒 cutter", panel="导入拼接", expected_effect="新增结构 volume 并刷新场景")
            box_layout.addWidget(QtWidgets.QLabel("bounds xmin,xmax,ymin,ymax,zmin,zmax"), 0, 0, 1, 2)
            box_layout.addWidget(self.structure_bounds_edit, 1, 0, 1, 2)
            box_layout.addWidget(QtWidgets.QLabel("类型"), 1, 2)
            box_layout.addWidget(self.structure_kind_combo, 1, 3)
            box_layout.addWidget(QtWidgets.QLabel("材料"), 2, 0)
            box_layout.addWidget(self.structure_material_edit, 2, 1)
            box_layout.addWidget(register_box, 2, 3)
            layout.addWidget(box)

            options = QtWidgets.QGroupBox("3. 拼接 / 布尔差分 / 重网格")
            options_layout = QtWidgets.QGridLayout(options)
            self.import_assembly_element_size = QtWidgets.QDoubleSpinBox(); self.import_assembly_element_size.setRange(0.01, 1e6); self.import_assembly_element_size.setValue(2.0); self.import_assembly_element_size.setDecimals(3)
            self.import_assembly_preserve_original = QtWidgets.QCheckBox("保留原始地质体")
            self.import_assembly_require_native_import = QtWidgets.QCheckBox("要求 native IFC/STEP 导入")
            self.import_assembly_require_native_boolean = QtWidgets.QCheckBox("要求 native Gmsh/OCC 布尔")
            run_fallback = QtWidgets.QPushButton("执行拼接/差分/重网格")
            run_fallback.clicked.connect(lambda _checked=False: self._run_gui_action("run_import_driven_assembly", self._run_import_driven_assembly_from_gui))
            self._register_gui_button(run_fallback, "run_import_driven_assembly", "对土体和结构重叠区做差分并重新划分 Tet4 网格", panel="导入拼接", expected_effect="生成裁剪土体、physical groups、网格和 readiness report")
            run_native = QtWidgets.QPushButton("执行 1.6 Native Import Assembly")
            run_native.clicked.connect(lambda _checked=False: self._run_gui_action("run_native_import_assembly", self._run_native_import_assembly_from_gui))
            self._register_gui_button(run_native, "run_native_import_assembly", "执行 native/fallback-aware 导入拼接流程", panel="导入拼接", expected_effect="输出 native import assembly report 和重网格结果")
            options_layout.addWidget(QtWidgets.QLabel("单元尺寸"), 0, 0)
            options_layout.addWidget(self.import_assembly_element_size, 0, 1)
            options_layout.addWidget(self.import_assembly_preserve_original, 0, 2)
            options_layout.addWidget(self.import_assembly_require_native_import, 1, 0, 1, 2)
            options_layout.addWidget(self.import_assembly_require_native_boolean, 1, 2, 1, 2)
            options_layout.addWidget(run_fallback, 2, 0, 1, 2)
            options_layout.addWidget(run_native, 2, 2, 1, 2)
            layout.addWidget(options)

            mesh_tools = QtWidgets.QGroupBox("4. 网格显示 / FEM 优化")
            mesh_tools_layout = QtWidgets.QGridLayout(mesh_tools)
            show_mesh = QtWidgets.QPushButton("刷新网格显示")
            show_mesh.clicked.connect(lambda _checked=False: self._run_gui_action("refresh_mesh_visualization", self._refresh_mesh_visualization_from_gui))
            self._register_gui_button(show_mesh, "refresh_mesh_visualization", "按地质分层/网格单元刷新 3D 网格显示", panel="导入拼接", expected_effect="显示导入 MSH/VTU 网格、单元边线、分层和坏单元提示")
            check_mesh = QtWidgets.QPushButton("检查网格质量")
            check_mesh.clicked.connect(lambda _checked=False: self._run_gui_action("check_fem_mesh_quality", self._check_fem_mesh_quality_from_gui))
            self._register_gui_button(check_mesh, "check_fem_mesh_quality", "计算有限元网格质量、坏单元、长宽比和分层标签", panel="导入拼接", expected_effect="输出 FEM 网格质量报告并刷新 Readiness")
            optimize_mesh = QtWidgets.QPushButton("优化为 FEM 网格")
            optimize_mesh.clicked.connect(lambda _checked=False: self._run_gui_action("optimize_fem_mesh", self._optimize_fem_mesh_from_gui))
            self._register_gui_button(optimize_mesh, "optimize_fem_mesh", "合并重复节点、移除退化单元并刷新地质分层显示标签", panel="导入拼接", expected_effect="生成更适合有限元求解的 MeshDocument")
            identify_layers = QtWidgets.QPushButton("识别地质分层")
            identify_layers.clicked.connect(lambda _checked=False: self._run_gui_action("identify_geology_layers", self._identify_geology_layers_from_gui))
            self._register_gui_button(identify_layers, "identify_geology_layers", "优先读取 soil_id/material_index/gmsh_physical，缺失时按高程识别地质分层", panel="导入拼接", expected_effect="刷新 geology_layer_id/display_group 并输出层数统计")
            reduce_mesh = QtWidgets.QPushButton("网格降重")
            reduce_mesh.clicked.connect(lambda _checked=False: self._run_gui_action("reduce_mesh_weight", self._reduce_mesh_weight_from_gui))
            self._register_gui_button(reduce_mesh, "reduce_mesh_weight", "合并重复节点、移除重复/退化单元、删除未用节点，保留地质 cell tag", panel="导入拼接", expected_effect="生成更轻量的导入网格但不破坏地质分层标签")
            nonmanifold = QtWidgets.QPushButton("非流形检查")
            nonmanifold.clicked.connect(lambda _checked=False: self._run_gui_action("diagnose_nonmanifold_mesh", self._diagnose_nonmanifold_mesh_from_gui))
            self._register_gui_button(nonmanifold, "diagnose_nonmanifold_mesh", "统计边界面、重复单元和 face-use>2 的非流形面", panel="导入拼接", expected_effect="输出非流形报告并刷新 3D 诊断")
            mesh_tools_layout.addWidget(show_mesh, 0, 0)
            mesh_tools_layout.addWidget(check_mesh, 0, 1)
            mesh_tools_layout.addWidget(optimize_mesh, 0, 2)
            mesh_tools_layout.addWidget(identify_layers, 1, 0)
            mesh_tools_layout.addWidget(reduce_mesh, 1, 1)
            mesh_tools_layout.addWidget(nonmanifold, 1, 2)
            layout.addWidget(mesh_tools)

            self.import_assembly_status = QtWidgets.QPlainTextEdit()
            self.import_assembly_status.setReadOnly(True)
            self.import_assembly_status.setMaximumHeight(220)
            self.import_assembly_status.setPlainText("建议路线：导入地质 → 导入/注册结构 cutter → 执行差分与重网格。3D 视口不可用时仍可使用本面板。")
            layout.addWidget(self.import_assembly_status, 1)
            return panel

        def _build_fem_analysis_panel(self) -> Any:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            intro = QtWidgets.QLabel("导入地质模型 FEM 分析流程：模型/材料检查 → 有限元网格 → 自动地应力 → 求解稳态 → 结果查看。")
            intro.setWordWrap(True)
            layout.addWidget(intro)

            check_box = QtWidgets.QGroupBox("1. 模型导入后 FEM 状态检查")
            check_layout = QtWidgets.QGridLayout(check_box)
            check_btn = QtWidgets.QPushButton("检查网格质量 / 材料状态")
            check_btn.clicked.connect(lambda _checked=False: self._run_gui_action("fem_check_imported_geology", self._fem_check_imported_geology_from_gui))
            self._register_gui_button(check_btn, "fem_check_imported_geology", "检查导入地质模型的 FEM 网格质量、分层、材料和非流形状态", panel="FEM分析流程", expected_effect="输出 FEM readiness 报告并刷新模型树/Readiness")
            prepare_btn = QtWidgets.QPushButton("准备地层体 / 材料映射")
            prepare_btn.clicked.connect(lambda _checked=False: self._run_gui_action("fem_prepare_imported_geology", self._fem_prepare_imported_geology_from_gui))
            self._register_gui_button(prepare_btn, "fem_prepare_imported_geology", "把导入 VTU/MSH 的 geology_layer 映射为显式体对象、材料和 block_id", panel="FEM分析流程", expected_effect="地质体按层进入 FEM 编译器")
            check_layout.addWidget(check_btn, 0, 0)
            check_layout.addWidget(prepare_btn, 0, 1)
            layout.addWidget(check_box)

            mesh_box = QtWidgets.QGroupBox("2. 有限元网格划分 / 修复")
            mesh_layout = QtWidgets.QGridLayout(mesh_box)
            self.fem_element_size = QtWidgets.QDoubleSpinBox(); self.fem_element_size.setRange(0.01, 1e6); self.fem_element_size.setDecimals(3); self.fem_element_size.setValue(2.0)
            self.fem_require_native_mesher = QtWidgets.QCheckBox("要求 native Gmsh/OCC")
            fem_mesh_btn = QtWidgets.QPushButton("生成/修复 FEM 网格")
            fem_mesh_btn.clicked.connect(lambda _checked=False: self._run_gui_action("fem_generate_or_repair_mesh", self._fem_generate_or_repair_mesh_from_gui))
            self._register_gui_button(fem_mesh_btn, "fem_generate_or_repair_mesh", "复用导入体网格或按地层体重新生成 Tet4 FEM 网格", panel="FEM分析流程", expected_effect="生成 MeshDocument、质量报告和 block/material tags")
            mesh_layout.addWidget(QtWidgets.QLabel("目标单元尺寸"), 0, 0)
            mesh_layout.addWidget(self.fem_element_size, 0, 1)
            mesh_layout.addWidget(self.fem_require_native_mesher, 0, 2)
            mesh_layout.addWidget(fem_mesh_btn, 0, 3)
            layout.addWidget(mesh_box)

            solve_box = QtWidgets.QGroupBox("3. 自动地应力与有限元求解")
            solve_layout = QtWidgets.QGridLayout(solve_box)
            self.fem_surcharge_qz = QtWidgets.QDoubleSpinBox(); self.fem_surcharge_qz.setRange(-1e6, 1e6); self.fem_surcharge_qz.setDecimals(3); self.fem_surcharge_qz.setValue(0.0)
            self.fem_tolerance = QtWidgets.QDoubleSpinBox(); self.fem_tolerance.setRange(1e-12, 1.0); self.fem_tolerance.setDecimals(8); self.fem_tolerance.setValue(1e-5)
            setup_btn = QtWidgets.QPushButton("配置自动地应力")
            setup_btn.clicked.connect(lambda _checked=False: self._run_gui_action("fem_setup_automatic_stress", self._fem_setup_automatic_stress_from_gui))
            self._register_gui_button(setup_btn, "fem_setup_automatic_stress", "自动配置重力体力、底部固定、侧向法向约束和计算控制", panel="FEM分析流程", expected_effect="生成自动地应力阶段输入")
            compile_btn = QtWidgets.QPushButton("编译求解输入")
            compile_btn.clicked.connect(lambda _checked=False: self._run_gui_action("fem_compile_solver_model", self._fem_compile_solver_model_from_gui))
            self._register_gui_button(compile_btn, "fem_compile_solver_model", "把 GeoProjectDocument 编译为阶段有限元求解模型", panel="FEM分析流程", expected_effect="生成 CompiledPhaseModels")
            solve_btn = QtWidgets.QPushButton("求解至稳态")
            solve_btn.clicked.connect(lambda _checked=False: self._run_gui_action("fem_solve_to_steady_state", self._fem_solve_to_steady_state_from_gui))
            self._register_gui_button(solve_btn, "fem_solve_to_steady_state", "执行自动地应力 FEM 求解并按相对残差判定稳态", panel="FEM分析流程", expected_effect="写入 ResultStore 并输出稳态判定")
            solve_layout.addWidget(QtWidgets.QLabel("面荷载 qz/kPa"), 0, 0)
            solve_layout.addWidget(self.fem_surcharge_qz, 0, 1)
            solve_layout.addWidget(QtWidgets.QLabel("稳态残差容限"), 0, 2)
            solve_layout.addWidget(self.fem_tolerance, 0, 3)
            solve_layout.addWidget(setup_btn, 1, 0)
            solve_layout.addWidget(compile_btn, 1, 1)
            solve_layout.addWidget(solve_btn, 1, 2)
            layout.addWidget(solve_box)

            result_box = QtWidgets.QGroupBox("4. 求解结果查看")
            result_layout = QtWidgets.QGridLayout(result_box)
            self.fem_result_field_combo = QtWidgets.QComboBox(); self.fem_result_field_combo.addItems(["cell_von_mises", "cell_stress_zz", "cell_equivalent_strain", "uz", "displacement"])
            view_btn = QtWidgets.QPushButton("刷新结果摘要")
            view_btn.clicked.connect(lambda _checked=False: self._run_gui_action("fem_refresh_result_view", self._fem_refresh_result_view_from_gui))
            self._register_gui_button(view_btn, "fem_refresh_result_view", "刷新 ResultStore 阶段结果、工程指标和视口结果叠加", panel="FEM分析流程", expected_effect="展示位移、沉降、应力和残差摘要")
            full_btn = QtWidgets.QPushButton("一键完整分析流程")
            full_btn.clicked.connect(lambda _checked=False: self._run_gui_action("fem_run_complete_analysis", self._fem_run_complete_analysis_from_gui))
            self._register_gui_button(full_btn, "fem_run_complete_analysis", "后台执行检查、网格、自动地应力、编译、求解和结果查看", panel="FEM分析流程", expected_effect="长耗时流程显示进度并生成完整报告")
            result_layout.addWidget(QtWidgets.QLabel("结果场"), 0, 0)
            result_layout.addWidget(self.fem_result_field_combo, 0, 1)
            result_layout.addWidget(view_btn, 0, 2)
            result_layout.addWidget(full_btn, 0, 3)
            layout.addWidget(result_box)

            self.fem_analysis_progress = QtWidgets.QProgressBar(); self.fem_analysis_progress.setRange(0, 100); self.fem_analysis_progress.setValue(0)
            self.fem_analysis_phase_label = QtWidgets.QLabel("等待执行 FEM 分析流程。")
            self.fem_analysis_phase_label.setWordWrap(True)
            self.fem_analysis_status = QtWidgets.QPlainTextEdit(); self.fem_analysis_status.setReadOnly(True); self.fem_analysis_status.setMaximumHeight(220)
            self.fem_result_table = QtWidgets.QTableWidget(0, 5)
            self.fem_result_table.setHorizontalHeaderLabels(["Phase", "Max |u|", "Settlement", "Von Mises", "Residual"])
            self.fem_result_table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.fem_analysis_phase_label)
            layout.addWidget(self.fem_analysis_progress)
            layout.addWidget(self.fem_result_table, 1)
            layout.addWidget(self.fem_analysis_status)
            return panel

        def _analysis_progress_callback(self, event: dict[str, Any]) -> None:
            try:
                self._analysis_progress_events.put(dict(event or {}))
            except Exception:
                pass

        def _set_fem_analysis_progress(self, percent: int, message: str, *, phase: str = "") -> None:
            if hasattr(self, "fem_analysis_progress"):
                self.fem_analysis_progress.setRange(0, 100)
                self.fem_analysis_progress.setValue(max(0, min(100, int(percent))))
            if hasattr(self, "fem_analysis_phase_label"):
                prefix = f"{phase}: " if phase else ""
                self.fem_analysis_phase_label.setText(prefix + str(message))
            try:
                self.statusBar().showMessage(str(message))
            except Exception:
                pass

        def _drain_analysis_progress_events(self) -> None:
            if not hasattr(self, "_analysis_progress_events"):
                return
            while True:
                try:
                    event = self._analysis_progress_events.get_nowait()
                except Exception:
                    break
                self._set_fem_analysis_progress(int(event.get("percent", 0)), str(event.get("message", "")), phase=str(event.get("phase", "")))
                if hasattr(self, "messages"):
                    self.messages.appendPlainText(f"[FEM] {event.get('percent', 0)}% {event.get('phase', '')}: {event.get('message', '')}")

        def _update_fem_analysis_report_ui(self, report: Any, *, render: bool = False, overlay_result: bool = False) -> str:
            payload = report.to_dict() if hasattr(report, "to_dict") else dict(report or {})
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            if hasattr(self, "fem_analysis_status"):
                self.fem_analysis_status.setPlainText(text)
            if hasattr(self, "import_assembly_status"):
                self.import_assembly_status.setPlainText(text)
            self._populate_fem_result_table(payload)
            stage = str(payload.get("stage", ""))
            ok = bool(payload.get("ok", False))
            if hasattr(self, "messages"):
                self.messages.appendPlainText(f"FEM analysis report: ok={payload.get('ok')} stage={payload.get('stage')}")
            self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
            if hasattr(self, "fem_analysis_progress"):
                self.fem_analysis_progress.setRange(0, 100)
                self.fem_analysis_progress.setValue(100)
            if hasattr(self, "fem_analysis_phase_label"):
                suffix = "完成" if ok else "完成但存在警告/阻塞"
                self.fem_analysis_phase_label.setText(f"{stage}: {suffix}")
            if overlay_result:
                try:
                    if hasattr(self.viewport_adapter, "render_result_overlay"):
                        self.viewport_adapter.render_result_overlay(self.current_demo_project, field_name=str(self.fem_result_field_combo.currentText()), clear=False)
                    elif hasattr(self.viewport_adapter, "render_project_mesh_overlay"):
                        self.viewport_adapter.render_project_mesh_overlay(self.current_demo_project, clear=False)
                    self.viewport_adapter.safe_render(reason="fem_result_overlay")
                except Exception as exc:
                    if hasattr(self, "messages"):
                        self.messages.appendPlainText(f"结果视图叠加失败: {type(exc).__name__}: {exc}")
            elif render:
                self._mark_scene_dirty("fem_analysis_workflow")
                self._render_scene(reset_camera=False, force=True, reason="fem_analysis_workflow")
            return f"ok={payload.get('ok')} stage={payload.get('stage')}"

        def _start_fem_background_action(self, label: str, phase: str, initial_percent: int, worker: Callable[[], Any], *, render: bool = False, overlay_result: bool = False) -> str:
            self._set_fem_analysis_progress(initial_percent, label, phase=phase)
            if hasattr(self, "fem_analysis_progress"):
                self.fem_analysis_progress.setRange(0, 100)
            def success(report: Any) -> None:
                self._drain_analysis_progress_events()
                self._update_fem_analysis_report_ui(report, render=render, overlay_result=overlay_result)
            self._start_background_operation(label, worker, success)
            return f"{label} 已启动；完成后进度会到 100%。"

        def _populate_fem_result_table(self, payload: dict[str, Any] | None = None) -> None:
            if not hasattr(self, "fem_result_table"):
                return
            rows = []
            try:
                result_view = dict((payload or {}).get("metadata", {}).get("results", {}) or {})
                rows = list(result_view.get("phase_results", []) or [])
            except Exception:
                rows = []
            if not rows:
                for phase_id, result in dict(getattr(self.current_demo_project.result_store, "phase_results", {}) or {}).items():
                    metrics = dict(getattr(result, "metrics", {}) or {})
                    rows.append({
                        "phase_id": phase_id,
                        "max_displacement": metrics.get("max_displacement", 0.0),
                        "max_settlement": metrics.get("max_settlement", 0.0),
                        "max_von_mises_stress": metrics.get("max_von_mises_stress", 0.0),
                        "residual_norm": metrics.get("residual_norm", 0.0),
                    })
            self.fem_result_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                values = [
                    row.get("phase_id", ""),
                    f"{float(row.get('max_displacement', 0.0) or 0.0):.6g}",
                    f"{float(row.get('max_settlement', 0.0) or 0.0):.6g}",
                    f"{float(row.get('max_von_mises_stress', 0.0) or 0.0):.6g}",
                    f"{float(row.get('residual_norm', 0.0) or 0.0):.6g}",
                ]
                for c, value in enumerate(values):
                    self.fem_result_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(value)))

        def _fem_prepare_imported_geology_from_gui(self) -> str:
            from geoai_simkit.services.geology_fem_analysis_workflow import prepare_imported_geology_for_fem
            return self._start_fem_background_action(
                "准备导入地质 FEM 映射", "prepare", 0,
                lambda: prepare_imported_geology_for_fem(self.current_demo_project, progress_callback=self._analysis_progress_callback),
                render=False,
            )

        def _fem_check_imported_geology_from_gui(self) -> str:
            from geoai_simkit.services.geology_fem_analysis_workflow import check_imported_geology_fem_state
            return self._start_fem_background_action(
                "检查导入模型 FEM 状态", "check", 20,
                lambda: check_imported_geology_fem_state(self.current_demo_project, progress_callback=self._analysis_progress_callback),
                render=False,
            )

        def _fem_generate_or_repair_mesh_from_gui(self) -> str:
            from geoai_simkit.services.geology_fem_analysis_workflow import generate_or_repair_imported_geology_fem_mesh
            element_size = float(self.fem_element_size.value()) if hasattr(self, "fem_element_size") else None
            require_native = bool(self.fem_require_native_mesher.isChecked()) if hasattr(self, "fem_require_native_mesher") else False
            return self._start_fem_background_action(
                "生成或修复 FEM 网格", "mesh", 34,
                lambda: generate_or_repair_imported_geology_fem_mesh(self.current_demo_project, element_size=element_size, require_native=require_native, progress_callback=self._analysis_progress_callback),
                render=True,
            )

        def _fem_setup_automatic_stress_from_gui(self) -> str:
            from geoai_simkit.services.geology_fem_analysis_workflow import setup_automatic_stress_conditions
            surcharge_qz = float(self.fem_surcharge_qz.value()) if hasattr(self, "fem_surcharge_qz") else 0.0
            tolerance = float(self.fem_tolerance.value()) if hasattr(self, "fem_tolerance") else 1.0e-5
            return self._start_fem_background_action(
                "配置自动地应力", "stress", 58,
                lambda: setup_automatic_stress_conditions(self.current_demo_project, surcharge_qz=surcharge_qz, tolerance=tolerance, progress_callback=self._analysis_progress_callback),
                render=False,
            )

        def _fem_compile_solver_model_from_gui(self) -> str:
            from geoai_simkit.services.geology_fem_analysis_workflow import compile_imported_geology_solver_model
            return self._start_fem_background_action(
                "编译 FEM 求解输入", "compile", 68,
                lambda: compile_imported_geology_solver_model(self.current_demo_project, progress_callback=self._analysis_progress_callback),
                render=False,
            )

        def _fem_solve_to_steady_state_from_gui(self) -> str:
            from geoai_simkit.services.geology_fem_analysis_workflow import solve_imported_geology_to_steady_state
            return self._start_fem_background_action(
                "求解至自动地应力稳态", "solve", 78,
                lambda: solve_imported_geology_to_steady_state(self.current_demo_project, progress_callback=self._analysis_progress_callback),
                render=False,
            )

        def _fem_refresh_result_view_from_gui(self) -> str:
            from geoai_simkit.services.geology_fem_analysis_workflow import build_imported_geology_result_view
            return self._start_fem_background_action(
                "刷新 FEM 结果查看", "results", 94,
                lambda: build_imported_geology_result_view(self.current_demo_project, progress_callback=self._analysis_progress_callback),
                render=False, overlay_result=True,
            )

        def _fem_run_complete_analysis_from_gui(self) -> str:
            from geoai_simkit.services.geology_fem_analysis_workflow import run_complete_imported_geology_fem_analysis
            self._set_fem_analysis_progress(0, "后台启动完整 FEM 分析流程", phase="start")
            if hasattr(self, "fem_analysis_progress"):
                self.fem_analysis_progress.setRange(0, 100)
                self.fem_analysis_progress.setValue(0)
            element_size = float(self.fem_element_size.value()) if hasattr(self, "fem_element_size") else None
            surcharge_qz = float(self.fem_surcharge_qz.value()) if hasattr(self, "fem_surcharge_qz") else 0.0
            require_native = bool(self.fem_require_native_mesher.isChecked()) if hasattr(self, "fem_require_native_mesher") else False
            def work():
                return run_complete_imported_geology_fem_analysis(
                    self.current_demo_project,
                    element_size=element_size,
                    surcharge_qz=surcharge_qz,
                    require_native_mesher=require_native,
                    progress_callback=self._analysis_progress_callback,
                )
            def success(report: Any) -> None:
                if hasattr(self, "fem_analysis_progress"):
                    self.fem_analysis_progress.setRange(0, 100)
                    self.fem_analysis_progress.setValue(100)
                self._drain_analysis_progress_events()
                self._update_fem_analysis_report_ui(report, render=False, overlay_result=True)
            self._start_background_operation("导入地质模型 FEM 完整分析流程", work, success)
            return "完整 FEM 分析流程已启动，进度条会持续更新。"

        def _build_structure_modeling_panel(self) -> Any:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            self.structure_active_tool_label = QtWidgets.QLabel("当前工具：select；请在视口中点选或创建几何。")
            self.structure_selected_label = QtWidgets.QLabel("当前选择：无")
            self.structure_selected_label.setWordWrap(True)
            layout.addWidget(self.structure_active_tool_label)
            layout.addWidget(self.structure_selected_label)

            workplane_box = QtWidgets.QGroupBox("工作面 / 捕捉 / 反馈")
            workplane_layout = QtWidgets.QGridLayout(workplane_box)
            self.structure_workplane_combo = QtWidgets.QComboBox(); self.structure_workplane_combo.addItems(["XZ", "XY", "YZ"])
            self.structure_workplane_combo.currentTextChanged.connect(lambda text: self._set_workplane(str(text).lower()))
            self.structure_snap_checkbox = QtWidgets.QCheckBox("捕捉")
            self.structure_snap_checkbox.setChecked(True)
            self.structure_snap_checkbox.toggled.connect(lambda checked: self._set_snap_enabled_from_structure_panel(bool(checked)))
            self.structure_endpoint_snap_checkbox = QtWidgets.QCheckBox("端点")
            self.structure_endpoint_snap_checkbox.setChecked(True)
            self.structure_endpoint_snap_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("endpoint", bool(checked)))
            self.structure_midpoint_snap_checkbox = QtWidgets.QCheckBox("中点")
            self.structure_midpoint_snap_checkbox.setChecked(True)
            self.structure_midpoint_snap_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("midpoint", bool(checked)))
            self.structure_grid_snap_checkbox = QtWidgets.QCheckBox("网格")
            self.structure_grid_snap_checkbox.setChecked(True)
            self.structure_grid_snap_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("grid", bool(checked)))
            self.structure_wall_endpoint_snap_checkbox = QtWidgets.QCheckBox("墙端点")
            self.structure_wall_endpoint_snap_checkbox.setChecked(True)
            self.structure_wall_endpoint_snap_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("wall_endpoint", bool(checked)))
            self.structure_beam_endpoint_snap_checkbox = QtWidgets.QCheckBox("梁端点")
            self.structure_beam_endpoint_snap_checkbox.setChecked(True)
            self.structure_beam_endpoint_snap_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("beam_endpoint", bool(checked)))
            self.structure_anchor_endpoint_snap_checkbox = QtWidgets.QCheckBox("锚杆端点")
            self.structure_anchor_endpoint_snap_checkbox.setChecked(True)
            self.structure_anchor_endpoint_snap_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("anchor_endpoint", bool(checked)))
            self.structure_stratum_intersection_snap_checkbox = QtWidgets.QCheckBox("地层交点")
            self.structure_stratum_intersection_snap_checkbox.setChecked(True)
            self.structure_stratum_intersection_snap_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("stratum_intersection", bool(checked)))
            self.structure_excavation_intersection_snap_checkbox = QtWidgets.QCheckBox("开挖交点")
            self.structure_excavation_intersection_snap_checkbox.setChecked(True)
            self.structure_excavation_intersection_snap_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("excavation_intersection", bool(checked)))
            self.structure_constraint_horizontal_checkbox = QtWidgets.QCheckBox("水平约束")
            self.structure_constraint_horizontal_checkbox.setChecked(True)
            self.structure_constraint_horizontal_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("horizontal_constraint", bool(checked)))
            self.structure_constraint_vertical_checkbox = QtWidgets.QCheckBox("垂直约束")
            self.structure_constraint_vertical_checkbox.setChecked(True)
            self.structure_constraint_vertical_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("vertical_constraint", bool(checked)))
            self.structure_constraint_edge_checkbox = QtWidgets.QCheckBox("沿边")
            self.structure_constraint_edge_checkbox.setChecked(True)
            self.structure_constraint_edge_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("along_edge_constraint", bool(checked)))
            self.structure_constraint_normal_checkbox = QtWidgets.QCheckBox("沿法向")
            self.structure_constraint_normal_checkbox.setChecked(True)
            self.structure_constraint_normal_checkbox.toggled.connect(lambda checked: self._set_snap_mode_from_structure_panel("along_normal_constraint", bool(checked)))
            self.lock_edge_constraint_button = QtWidgets.QPushButton("锁定沿边")
            self.lock_edge_constraint_button.setToolTip("从当前选择或右键位置锁定一条边/线，后续点线面体会连续投影到同一边。")
            self.lock_edge_constraint_button.clicked.connect(lambda _checked=False: self._lock_constraint_from_current_selection("along_edge"))
            self.lock_normal_constraint_button = QtWidgets.QPushButton("锁定沿法向")
            self.lock_normal_constraint_button.setToolTip("从当前选择或右键位置锁定法向，后续点线面体会连续沿同一法向布置。")
            self.lock_normal_constraint_button.clicked.connect(lambda _checked=False: self._lock_constraint_from_current_selection("along_normal"))
            self.unlock_constraint_button = QtWidgets.QPushButton("解除锁定")
            self.unlock_constraint_button.clicked.connect(self._unlock_viewport_constraint_lock)
            self.constraint_lock_label = QtWidgets.QLabel("约束锁定：无")
            self.constraint_lock_label.setWordWrap(True)
            self.structure_tool_state_label = QtWidgets.QLabel("反馈：移动鼠标显示十字光标、语义吸附点；Shift 水平，Ctrl 垂直；也可用工具条或右键菜单锁定沿边/沿法向。")
            self.structure_tool_state_label.setWordWrap(True)
            workplane_layout.addWidget(QtWidgets.QLabel("工作面"), 0, 0)
            workplane_layout.addWidget(self.structure_workplane_combo, 0, 1)
            workplane_layout.addWidget(self.structure_snap_checkbox, 0, 2)
            workplane_layout.addWidget(self.structure_grid_snap_checkbox, 1, 0)
            workplane_layout.addWidget(self.structure_endpoint_snap_checkbox, 1, 1)
            workplane_layout.addWidget(self.structure_midpoint_snap_checkbox, 1, 2)
            workplane_layout.addWidget(self.structure_wall_endpoint_snap_checkbox, 2, 0)
            workplane_layout.addWidget(self.structure_beam_endpoint_snap_checkbox, 2, 1)
            workplane_layout.addWidget(self.structure_anchor_endpoint_snap_checkbox, 2, 2)
            workplane_layout.addWidget(self.structure_stratum_intersection_snap_checkbox, 3, 0)
            workplane_layout.addWidget(self.structure_excavation_intersection_snap_checkbox, 3, 1)
            workplane_layout.addWidget(self.structure_constraint_horizontal_checkbox, 4, 0)
            workplane_layout.addWidget(self.structure_constraint_vertical_checkbox, 4, 1)
            workplane_layout.addWidget(self.structure_constraint_edge_checkbox, 5, 0)
            workplane_layout.addWidget(self.structure_constraint_normal_checkbox, 5, 1)
            workplane_layout.addWidget(self.lock_edge_constraint_button, 6, 0)
            workplane_layout.addWidget(self.lock_normal_constraint_button, 6, 1)
            workplane_layout.addWidget(self.unlock_constraint_button, 6, 2)
            workplane_layout.addWidget(self.constraint_lock_label, 7, 0, 1, 3)
            workplane_layout.addWidget(self.structure_tool_state_label, 8, 0, 1, 3)
            layout.addWidget(workplane_box)

            create_box = QtWidgets.QGroupBox("鼠标创建几何")
            create_layout = QtWidgets.QGridLayout(create_box)
            creation_buttons = [
                ("创建点", "point", "移动预览，左键创建"),
                ("创建线", "line", "左键起点，再移动预览，左键终点"),
                ("创建面", "surface", "左键逐点，右键或 Enter 完成"),
                ("创建体", "block_box", "左键第一角点，移动预览，左键对角点"),
            ]
            for index, (label, tool, hint) in enumerate(creation_buttons):
                button = QtWidgets.QPushButton(label)
                button.setToolTip(hint)
                button.clicked.connect(lambda _checked=False, t=tool, h=hint: self._run_gui_action(f"activate_creation_{t}", lambda: self._activate_structure_creation_tool(t, h)))
                self._register_gui_button(button, f"activate_creation_{tool}", hint, panel="结构建模", expected_effect=f"激活 {tool} 创建工具")
                create_layout.addWidget(button, index // 2, index % 2)
            layout.addWidget(create_box)

            promote_box = QtWidgets.QGroupBox("右键/选中后创建结构")
            promote_layout = QtWidgets.QGridLayout(promote_box)
            promote_buttons = [
                ("体→土层/土体", "soil_volume"),
                ("体→开挖体", "excavation"),
                ("体→混凝土结构", "concrete_block"),
                ("面→墙/板", "wall"),
                ("面→界面", "interface"),
                ("线→梁/支撑", "beam"),
                ("线→锚杆", "anchor"),
                ("线→桩/嵌入梁", "embedded_beam"),
                ("点→监测/控制点", "control_point"),
            ]
            for index, (label, semantic) in enumerate(promote_buttons):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(lambda _checked=False, sem=semantic: self._run_gui_action(f"promote_selection_{sem}", lambda: self._promote_selected_geometry_from_gui(sem)))
                self._register_gui_button(button, f"promote_selection_{semantic}", f"把当前选择提升为 {semantic} 工程对象", panel="结构建模", expected_effect="写入结构模型/材料/拓扑关系")
                promote_layout.addWidget(button, index // 2, index % 2)
            layout.addWidget(promote_box)

            material_box = QtWidgets.QGroupBox("材料快速赋值")
            material_layout = QtWidgets.QVBoxLayout(material_box)
            self.structure_material_recommendation = QtWidgets.QLabel("材料建议：选择对象后显示。")
            self.structure_material_recommendation.setWordWrap(True)
            material_layout.addWidget(self.structure_material_recommendation)
            row = QtWidgets.QHBoxLayout()
            self.quick_assign_selected_button = QtWidgets.QPushButton("推荐材料赋给选择")
            self.quick_assign_layer_button = QtWidgets.QPushButton("按识别地层/结构赋值")
            self.quick_assign_selected_button.clicked.connect(lambda _checked=False: self._run_gui_action("assign_recommended_material_to_selection", self._assign_recommended_material_to_selection_from_gui))
            self.quick_assign_layer_button.clicked.connect(lambda _checked=False: self._run_gui_action("auto_assign_recognized_materials", self._auto_assign_recognized_materials_from_gui))
            self._register_gui_button(self.quick_assign_selected_button, "assign_recommended_material_to_selection", "把推荐材料赋给当前选择", panel="结构建模", expected_effect="更新当前对象材料")
            self._register_gui_button(self.quick_assign_layer_button, "auto_assign_recognized_materials", "按识别地层和结构类型批量赋材料", panel="结构建模", expected_effect="更新土层/结构材料绑定")
            row.addWidget(self.quick_assign_selected_button)
            row.addWidget(self.quick_assign_layer_button)
            material_layout.addLayout(row)
            layout.addWidget(material_box)
            layout.addStretch(1)
            return panel

        def _build_material_library_panel(self) -> Any:
            import json
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            top = QtWidgets.QHBoxLayout()
            self.material_category_filter = QtWidgets.QComboBox(); self.material_category_filter.addItems(["soil", "plate", "beam", "interface"])
            self.material_category_filter.currentIndexChanged.connect(self._populate_material_library_table)
            self.ensure_default_materials_button = QtWidgets.QPushButton("补齐默认材料")
            self.ensure_default_materials_button.clicked.connect(self._ensure_default_materials_from_gui)
            self.auto_assign_materials_button = QtWidgets.QPushButton("按地层/结构快速赋值")
            self.auto_assign_materials_button.clicked.connect(self._auto_assign_materials_from_gui)
            top.addWidget(self.material_category_filter)
            top.addWidget(self.ensure_default_materials_button)
            top.addWidget(self.auto_assign_materials_button)
            layout.addLayout(top)
            self.material_library_table = QtWidgets.QTableWidget(0, 5)
            self.material_library_table.setHorizontalHeaderLabels(["ID", "名称", "类别", "模型", "主要参数"])
            self.material_library_table.horizontalHeader().setStretchLastSection(True)
            self.material_library_table.itemSelectionChanged.connect(self._on_material_library_selection_changed)
            layout.addWidget(self.material_library_table, 1)
            form = QtWidgets.QFormLayout()
            self.material_id_edit = QtWidgets.QLineEdit()
            self.material_name_edit = QtWidgets.QLineEdit()
            self.material_model_combo = QtWidgets.QComboBox(); self.material_model_combo.setEditable(True); self.material_model_combo.addItems(["mohr_coulomb", "linear_elastic", "interface_frictional"])
            self.material_drainage_combo = QtWidgets.QComboBox(); self.material_drainage_combo.setEditable(True); self.material_drainage_combo.addItems(["drained", "undrained", "not_applicable"])
            self.material_parameters_edit = QtWidgets.QPlainTextEdit(); self.material_parameters_edit.setMaximumHeight(88); self.material_parameters_edit.setPlainText('{"E_ref": 30000, "nu": 0.3}')
            for label, widget in (("材料 ID", self.material_id_edit), ("名称", self.material_name_edit), ("模型", self.material_model_combo), ("排水", self.material_drainage_combo), ("参数 JSON", self.material_parameters_edit)):
                form.addRow(label, widget)
            layout.addLayout(form)
            buttons = QtWidgets.QHBoxLayout()
            self.upsert_material_button = QtWidgets.QPushButton("保存材料")
            self.assign_material_to_selection_button = QtWidgets.QPushButton("赋给当前选择")
            self.upsert_material_button.clicked.connect(lambda _checked=False: self._run_gui_action("upsert_material", self._upsert_material_from_gui))
            self.assign_material_to_selection_button.clicked.connect(lambda _checked=False: self._run_gui_action("assign_material_to_selection", self._assign_material_to_selection_from_gui))
            self._register_gui_button(self.upsert_material_button, "upsert_material", "保存或更新当前材料表单", panel="材料库", expected_effect="写入 material_library")
            self._register_gui_button(self.assign_material_to_selection_button, "assign_material_to_selection", "把当前材料赋给选中对象", panel="材料库", expected_effect="更新当前对象材料")
            buttons.addWidget(self.upsert_material_button)
            buttons.addWidget(self.assign_material_to_selection_button)
            layout.addLayout(buttons)
            return panel

        def _build_workflow_spec_panel(self) -> Any:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            self.workflow_spec_table = QtWidgets.QTableWidget(0, 5)
            self.workflow_spec_table.setHorizontalHeaderLabels(["模块", "阶段", "必需元素", "输出", "检查项"])
            self.workflow_spec_table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.workflow_spec_table, 1)
            return panel

        def _material_bucket(self, category: str) -> dict[str, Any]:
            category = str(category or "soil").lower()
            lib = self.current_demo_project.material_library
            if category == "plate":
                return lib.plate_materials
            if category == "beam":
                return lib.beam_materials
            if category == "interface":
                return lib.interface_materials
            return lib.soil_materials

        def _populate_material_library_table(self) -> None:
            category = self.material_category_filter.currentText() if hasattr(self, "material_category_filter") else "soil"
            bucket = self._material_bucket(category)
            self.material_library_table.setRowCount(len(bucket))
            for r, material in enumerate(bucket.values()):
                params = dict(getattr(material, "parameters", {}) or {})
                values = [material.id, material.name, category, material.model_type, ", ".join(f"{k}={v}" for k, v in list(params.items())[:5])]
                for c, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    item.setData(256, {"category": category, "material": material.to_dict()})
                    self.material_library_table.setItem(r, c, item)
            self._refresh_material_combo_items()

        def _refresh_material_combo_items(self) -> None:
            if not hasattr(self, "material_combo"):
                return
            current = self.material_combo.currentText()
            self.material_combo.blockSignals(True)
            self.material_combo.clear(); self.material_combo.addItem("")
            ids = []
            lib = self.current_demo_project.material_library
            for bucket in (lib.soil_materials, lib.plate_materials, lib.beam_materials, lib.interface_materials):
                ids.extend(bucket.keys())
            self.material_combo.addItems(sorted(dict.fromkeys(ids)))
            if current:
                self._set_combo_text(self.material_combo, current)
            self.material_combo.blockSignals(False)

        def _on_material_library_selection_changed(self) -> None:
            items = self.material_library_table.selectedItems()
            if not items:
                return
            data = dict(items[0].data(256) or {})
            material = dict(data.get("material", {}) or {})
            if not material:
                return
            self.material_category_filter.setCurrentText(str(data.get("category", "soil")))
            self.material_id_edit.setText(str(material.get("id", "")))
            self.material_name_edit.setText(str(material.get("name", "")))
            self._set_combo_text(self.material_model_combo, str(material.get("model_type", "")))
            self._set_combo_text(self.material_drainage_combo, str(material.get("drainage", "not_applicable")))
            self.material_parameters_edit.setPlainText(json.dumps(dict(material.get("parameters", {}) or {}), ensure_ascii=False, indent=2))
            self._set_combo_text(self.material_combo, str(material.get("id", "")))

        def _upsert_material_from_gui(self) -> None:
            import json
            from geoai_simkit.geoproject import MaterialRecord
            category = self.material_category_filter.currentText().strip() or "soil"
            mid = self.material_id_edit.text().strip()
            if not mid:
                self.messages.appendPlainText("材料 ID 不能为空。")
                return
            try:
                params = json.loads(self.material_parameters_edit.toPlainText() or "{}")
                if not isinstance(params, dict):
                    raise ValueError("parameters must be a JSON object")
            except Exception as exc:
                self.messages.appendPlainText(f"材料参数 JSON 无效: {exc}")
                return
            material = MaterialRecord(id=mid, name=self.material_name_edit.text().strip() or mid, model_type=self.material_model_combo.currentText().strip() or "linear_elastic", parameters=params, drainage=self.material_drainage_combo.currentText().strip() or "not_applicable", metadata={"created_by": "gui_material_library"})
            self.current_demo_project.upsert_material(category, material)
            self.current_demo_project.mark_changed(["material"], action="gui_upsert_material", affected_entities=[mid])
            self._populate_material_library_table()
            self.messages.appendPlainText(f"Material saved: {category}/{mid}")

        def _ensure_default_materials_from_gui(self) -> None:
            result = ensure_default_engineering_materials(self.current_demo_project)
            self._populate_material_library_table()
            self.messages.appendPlainText(f"Default materials checked: created={result.get('created', [])}")

        def _auto_assign_materials_from_gui(self) -> None:
            result = auto_assign_materials_by_recognized_strata_and_structures(self.current_demo_project)
            self._populate_material_library_table()
            self._populate_object_tree()
            self._populate_properties(phase_workbench_ui_state(self.active_phase))
            self._mark_scene_dirty("auto_assign_materials")
            self._render_scene(reset_camera=False, force=True, reason="auto_assign_materials")
            self.messages.appendPlainText(f"Auto material assignment: {result.get('assigned_count', 0)} entity(ies)")

        def _assign_material_to_selection_from_gui(self) -> None:
            material = self.material_id_edit.text().strip() or self.material_combo.currentText().strip()
            if not material:
                self.messages.appendPlainText("请选择或输入材料。")
                return
            ids = self.selection_controller.selected_ids()
            target = self.entity_id_input.text().strip() or (ids[0] if ids else "")
            if not target:
                self.messages.appendPlainText("当前没有选中对象可赋材料。")
                return
            try:
                payload = self.current_demo_project.assign_entity_material(target, material)
                self.messages.appendPlainText(f"Assigned material {material} to {target}: {payload.get('ok')}")
            except Exception as exc:
                self.messages.appendPlainText(f"Assign material failed: {type(exc).__name__}: {exc}")
                return
            self._populate_material_library_table()
            self._mark_scene_dirty("assign_material")
            self._render_scene(reset_camera=False, force=True, reason="assign_material")

        def _active_entity_id_from_gui(self) -> str:
            eid = ""
            try:
                eid = self.entity_id_input.text().strip()
            except Exception:
                eid = ""
            if eid:
                return eid
            ids = self.selection_controller.selected_ids() if hasattr(self, "selection_controller") else []
            return str(ids[0]) if ids else ""

        def _activate_structure_creation_tool(self, tool_name: str, hint: str = "") -> None:
            self._activate_named_runtime_tool(tool_name)
            if hasattr(self, "structure_active_tool_label"):
                self.structure_active_tool_label.setText(f"当前工具：{tool_name}；{hint or '请在视口中点击'}")
            if hasattr(self, "structure_tool_state_label"):
                self.structure_tool_state_label.setText(f"反馈：{tool_name} 已激活。{hint or '在视口中点击；Esc 取消。'} 创建完成后会自动选中新对象，并刷新右键动作和材料建议。")
            self.statusBar().showMessage(f"结构建模工具 {tool_name} 已激活：{hint}")

        def _promote_selected_geometry_from_gui(self, semantic_type: str) -> None:
            entity_id = self._active_entity_id_from_gui()
            if not entity_id:
                self.messages.appendPlainText("请先在视口或模型树中选择点、线、面或体。")
                return
            material = self.material_combo.currentText().strip() if hasattr(self, "material_combo") else ""
            try:
                payload = promote_geometry_to_structure(self.current_demo_project, entity_id, semantic_type, material_id=material)
            except Exception as exc:
                self.messages.appendPlainText(f"创建结构失败: {type(exc).__name__}: {exc}")
                return
            self.messages.appendPlainText(f"Promoted {entity_id} -> {semantic_type}: ok={payload.get('ok')}")
            self._populate_material_library_table()
            self._populate_object_tree()
            self._sync_selected_entity_to_property_editor()
            self._mark_scene_dirty("promote_structure")
            self._render_scene(reset_camera=False, force=True, reason="promote_structure")

        def _assign_recommended_material_to_selection_from_gui(self) -> None:
            entity_id = self._active_entity_id_from_gui()
            if not entity_id:
                self.messages.appendPlainText("请先选择对象。")
                return
            try:
                recommendation = recommended_material_for_entity(self.current_demo_project, entity_id)
                material_id = str(recommendation.get("material_id") or "")
                if not material_id:
                    raise ValueError("No material recommendation")
                payload = self.current_demo_project.assign_entity_material(entity_id, material_id, category=str(recommendation.get("category") or ""))
            except Exception as exc:
                self.messages.appendPlainText(f"推荐材料赋值失败: {type(exc).__name__}: {exc}")
                return
            self.messages.appendPlainText(f"Recommended material assigned: {entity_id} -> {material_id}; ok={payload.get('ok')}")
            self._populate_material_library_table()
            self._sync_selected_entity_to_property_editor()
            self._mark_scene_dirty("assign_recommended_material")
            self._render_scene(reset_camera=False, force=True, reason="assign_recommended_material")

        def _auto_assign_recognized_materials_from_gui(self) -> None:
            result = auto_assign_materials_by_recognized_strata_and_structures(self.current_demo_project)
            self._populate_material_library_table()
            self._populate_object_tree()
            self._populate_properties(phase_workbench_ui_state(self.active_phase))
            self._mark_scene_dirty("auto_assign_recognized_materials")
            self._render_scene(reset_camera=False, force=True, reason="auto_assign_recognized_materials")
            self.messages.appendPlainText(f"Layer/structure material assignment: assigned={result.get('assigned_count', 0)}, skipped={result.get('skipped_count', 0)}")

        def _build_demo_panel(self) -> Any:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            self.demo_status = QtWidgets.QPlainTextEdit(); self.demo_status.setReadOnly(True)
            layout.addWidget(self.demo_status, 1)
            self.demo_selector = QtWidgets.QComboBox()
            for row_data in build_demo_catalog().get("demos", []):
                self.demo_selector.addItem(str(row_data.get("short_label", row_data.get("label"))), row_data.get("demo_id"))
            self.demo_selector.currentIndexChanged.connect(self._select_demo_template)
            layout.addWidget(self.demo_selector)
            row = QtWidgets.QHBoxLayout()
            self.load_demo_button = QtWidgets.QPushButton("一键加载")
            self.run_demo_button = QtWidgets.QPushButton("完整计算")
            self.export_demo_button = QtWidgets.QPushButton("导出包")
            self.run_all_demo_button = QtWidgets.QPushButton("全部模板")
            self.load_demo_button.clicked.connect(lambda _checked=False: self._run_gui_action("load_demo_project", self._load_demo_project))
            self.run_demo_button.clicked.connect(lambda _checked=False: self._run_gui_action("run_demo_complete_calculation", self._run_demo_complete_calculation))
            self.export_demo_button.clicked.connect(lambda _checked=False: self._run_gui_action("export_demo_bundle", self._export_demo_bundle))
            self.run_all_demo_button.clicked.connect(lambda _checked=False: self._run_gui_action("run_all_demo_templates", self._run_all_demo_templates))
            self._register_gui_button(self.load_demo_button, "load_demo_project", "加载当前 Demo 模板", panel="Demo", expected_effect="替换当前 project 并刷新视图")
            self._register_gui_button(self.run_demo_button, "run_demo_complete_calculation", "运行完整 Demo 计算链", panel="Demo", expected_effect="生成计算结果和报告")
            self._register_gui_button(self.export_demo_button, "export_demo_bundle", "导出 Demo 审查包", panel="Demo", expected_effect="写入 exports 目录")
            self._register_gui_button(self.run_all_demo_button, "run_all_demo_templates", "批量运行全部模板", panel="Demo", expected_effect="生成全部模板运行摘要")
            for btn in (self.load_demo_button, self.run_demo_button, self.export_demo_button, self.run_all_demo_button):
                row.addWidget(btn)
            layout.addLayout(row)
            return panel

        def _build_benchmark_panel(self) -> Any:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            header = QtWidgets.QHBoxLayout()
            self.benchmark_status_label = QtWidgets.QLabel("STEP/IFC benchmark report: not loaded")
            self.refresh_benchmark_button = QtWidgets.QPushButton("刷新 report")
            self.refresh_benchmark_button.clicked.connect(lambda _checked=False: self._run_gui_action("refresh_benchmark_report", self._populate_benchmark_readiness_tabs))
            self._register_gui_button(self.refresh_benchmark_button, "refresh_benchmark_report", "重新加载 STEP/IFC benchmark report", panel="Benchmark", expected_effect="刷新 Benchmark / Readiness / 修复建议")
            header.addWidget(self.benchmark_status_label, 1)
            header.addWidget(self.refresh_benchmark_button)
            layout.addLayout(header)
            self.benchmark_table = QtWidgets.QTableWidget(0, 10)
            self.benchmark_table.setHorizontalHeaderLabels(["Case", "Status", "Native", "BRep", "Name", "PG", "Mesh", "Solver", "Lineage", "Topology"])
            self.benchmark_table.horizontalHeader().setStretchLastSection(True)
            self.benchmark_table.cellClicked.connect(self._on_benchmark_case_clicked)
            layout.addWidget(self.benchmark_table, 1)
            return panel

        def _build_fix_suggestion_panel(self) -> Any:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            self.fix_table = QtWidgets.QTableWidget(0, 5)
            self.fix_table.setHorizontalHeaderLabels(["Case", "Blocker", "建议", "动作", "Artifact"] )
            self.fix_table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.fix_table, 1)
            return panel

        def _benchmark_report_payload(self) -> dict[str, Any]:
            try:
                return load_step_ifc_benchmark_readiness_payload()
            except Exception as exc:
                return {"contract": STEP_IFC_GUI_READINESS_CONTRACT, "available": False, "status": "load_error", "message": str(exc), "case_rows": [], "fix_suggestions": []}

        def _populate_benchmark_readiness_tabs(self) -> None:
            payload = self._benchmark_report_payload()
            self._last_benchmark_readiness_payload = payload
            self._populate_benchmark_cases(payload)
            self._populate_fix_suggestions(payload)
            source = payload.get("source") or "reports/step_ifc_native_benchmark.json"
            status = payload.get("status", "missing_report")
            summary = dict(payload.get("summary", {}) or {})
            self.benchmark_status_label.setText(f"{status} · cases={summary.get('case_count', payload.get('case_count', 0))} · source={source}")

        def _populate_benchmark_cases(self, payload: dict[str, Any]) -> None:
            rows = list(payload.get("case_rows", []) or [])
            self.benchmark_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                values = [
                    row.get("case_id", ""),
                    row.get("status", ""),
                    "Y" if row.get("native_backend_used") else "N",
                    "Y" if row.get("native_brep_certified") else "N",
                    "Y" if row.get("persistent_name_stable") else "N",
                    "Y" if row.get("physical_group_stable") else "N",
                    "Y" if row.get("mesh_entity_map_stable") else "N",
                    "Y" if row.get("solver_region_map_stable") else "N",
                    "Y" if row.get("lineage_verified") else "N",
                    f"S{row.get('solid_count', 0)}/F{row.get('face_count', 0)}/E{row.get('edge_count', 0)}",
                ]
                for c, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    item.setData(256, row)
                    self.benchmark_table.setItem(r, c, item)

        def _populate_fix_suggestions(self, payload: dict[str, Any]) -> None:
            suggestions = list(payload.get("fix_suggestions", []) or [])
            self.fix_table.setRowCount(len(suggestions))
            for r, suggestion in enumerate(suggestions):
                values = [
                    suggestion.get("case_id", ""),
                    suggestion.get("blocker", ""),
                    suggestion.get("title", ""),
                    suggestion.get("action_id", ""),
                    suggestion.get("artifact_dir", ""),
                ]
                for c, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    item.setData(256, suggestion)
                    self.fix_table.setItem(r, c, item)
                button = QtWidgets.QPushButton("查看/执行建议")
                button.clicked.connect(lambda _checked=False, s=dict(suggestion): self._on_fix_suggestion_clicked(s))
                self.fix_table.setCellWidget(r, 3, button)

        def _on_benchmark_case_clicked(self, row: int, column: int) -> None:
            item = self.benchmark_table.item(row, column)
            data = dict(item.data(256) or {}) if item is not None else {}
            if not data:
                return
            blockers = "\n".join(str(x) for x in list(data.get("blockers", []) or [])) or "无 blocker"
            warnings = "\n".join(str(x) for x in list(data.get("warnings", []) or [])) or "无 warning"
            artifact = data.get("artifact_dir") or ""
            self.help_text.setPlainText(f"Case: {data.get('case_id')}\nStatus: {data.get('status')}\nArtifact: {artifact}\n\nBlockers:\n{blockers}\n\nWarnings:\n{warnings}")
            if not self.help_dock.isVisible():
                self.help_dock.show()

        def _on_fix_suggestion_clicked(self, suggestion: dict[str, Any]) -> None:
            text = (
                f"Case: {suggestion.get('case_id', '')}\n"
                f"Blocker: {suggestion.get('blocker', '')}\n\n"
                f"建议: {suggestion.get('title', '')}\n"
                f"说明: {suggestion.get('detail', '')}\n\n"
                f"建议命令/操作:\n{suggestion.get('command', '')}\n\n"
                f"Artifact: {suggestion.get('artifact_dir', '')}"
            )
            self.help_text.setPlainText(text)
            self.messages.appendPlainText(f"Fix suggestion selected: {suggestion.get('action_id', '')} for {suggestion.get('case_id', '')}")
            if not self.help_dock.isVisible():
                self.help_dock.show()

        # ---------- Runtime and state ----------
        def _setup_interactive_modeling_runtime(self) -> None:
            self.viewport_state.update_from_geoproject_document(self.current_demo_project)
            self.tool_runtime = default_geometry_tool_runtime(ToolContext(document=self.current_demo_project, viewport=self.viewport_state, command_stack=self.command_stack, metadata={"selection_controller": self.selection_controller, "snap_controller": self.viewport_adapter.snap}))
            self.viewport_adapter.bind_runtime(self.tool_runtime)
            self.viewport_adapter.bind_viewport_state(self.viewport_state)
            self.viewport_adapter.bind_events()

        def _mark_scene_dirty(self, reason: str = "geometry") -> None:
            self._scene_revision += 1
            try:
                self.current_demo_project.mark_changed(["geometry", "mesh", "solver", "result"], action=f"ui_{reason}")
            except Exception:
                pass

        def _render_scene(self, *, reset_camera: bool = False, force: bool = False, reason: str = "") -> dict[str, Any]:
            if not force and self._last_render_revision == self._scene_revision:
                return {"ok": True, "skipped": True, "reason": "scene_not_dirty"}
            diagnostic = build_gui_visualization_diagnostic(self.current_demo_project).to_dict()
            try:
                self.viewport_state.update_from_geoproject_document(self.current_demo_project)
                self.viewport_adapter.bind_viewport_state(self.viewport_state)
                incremental = str(reason or "").startswith("interactive_") or str(reason or "").startswith("selection")
                self.viewport_adapter.render_viewport_state(self.viewport_state, clear=not incremental)
                try:
                    if hasattr(self.viewport_adapter, "render_project_mesh_overlay") and not incremental:
                        self.viewport_adapter.render_project_mesh_overlay(self.current_demo_project, clear=False)
                except Exception as exc:
                    self.messages.appendPlainText(f"网格显示刷新失败: {type(exc).__name__}: {exc}")
                self.viewport_adapter.render_selection(self.selection_controller.current_selection())
                try:
                    self.viewport_widget.add_axes()
                    self.viewport_widget.show_grid()
                except Exception:
                    pass
                if reset_camera and hasattr(self.viewport_widget, "reset_camera"):
                    self.viewport_widget.reset_camera()
                rendered = self.viewport_adapter.safe_render(reason=reason or "scene_refresh")
                if rendered:
                    self._last_render_revision = self._scene_revision
                guard = dict(getattr(self.viewport_adapter, "metadata", {}).get("opengl_guard", {}) or {})
                exposure = dict(getattr(self.viewport_adapter, "metadata", {}).get("opengl_exposure_state", {}) or {})
                self.diagnostics.setPlainText(
                    f"视口已刷新; backend={getattr(self, 'viewport_backend', 'pyvista')}; reason={reason}\n"
                    f"template={self.selected_demo_id}\n"
                    f"ok={diagnostic.get('ok')} primitives={diagnostic.get('primitive_count')} blocks={diagnostic.get('block_count')} surfaces={diagnostic.get('surface_count')} supports={diagnostic.get('support_count')}\n"
                    f"bounds={diagnostic.get('bounds')}\n"
                    f"OpenGL guard={guard}\n"
                    f"Widget exposure={exposure}\n"
                    f"warnings={'; '.join(diagnostic.get('warnings', [])) or 'none'}"
                )
            except Exception as exc:
                diagnostic["ok"] = False
                diagnostic.setdefault("warnings", []).append(f"render failed: {type(exc).__name__}: {exc}")
                self.diagnostics.setPlainText(str(diagnostic))
            return diagnostic

        def _after_viewport_command(self) -> None:
            self._mark_scene_dirty("interactive_command")
            # Interactive CAD edits should update the persistent primitive actors
            # without clearing and rebuilding the imported geology mesh.  Full
            # scene rebuild remains available from the manual refresh/import paths.
            self._render_scene(reset_camera=False, force=True, reason="interactive_incremental")
            self._sync_selected_entity_to_property_editor()
            QtCore.QTimer.singleShot(0, self._populate_object_tree)
            self.statusBar().showMessage("几何交互命令已执行；几何体已持久化，视口采用增量刷新。")

        # ---------- Phase and toolbar ----------
        def _set_phase(self, key: str, *, render: bool = False) -> None:
            self.active_phase = key
            for phase_key, action in self.phase_actions.items():
                if hasattr(action, "setChecked"):
                    action.setChecked(phase_key == key)
            state = phase_workbench_ui_state(key)
            # The old dynamic ribbon is intentionally absent from the production
            # UI.  Phase changes update panels and state only.
            self._rebuild_ribbon(state)
            self._populate_panels(state, render=render)

        def _rebuild_ribbon(self, state: dict[str, Any]) -> None:
            # Startup-safe no-op for historical phase-ribbon payloads.  The
            # action dispatcher and right-dock panels are the only supported
            # production controls after 1.6.4.
            self.ribbon_actions = []
            return None

        def _activate_tool(self, tool: dict[str, Any]) -> None:
            key = str(tool.get("key", "select"))
            state = phase_workbench_ui_state(self.active_phase, key)
            self._activate_runtime_tool(tool, state)
            self._handle_phase_action(tool, state)
            self.statusBar().showMessage(f"{state['active_phase_label']} · {tool.get('label', key)} 已激活。模型不会因工具切换被初始化。")

        def _activate_runtime_tool(self, tool: dict[str, Any], state: dict[str, Any]) -> None:
            if self.tool_runtime is None:
                self._setup_interactive_modeling_runtime()
            output = self.tool_runtime.activate_phase_tool(tool)
            self.viewport_adapter.apply_tool_output(output)
            runtime_tool = str(state.get("runtime_tool") or dict(tool.get("metadata", {}) or {}).get("runtime_tool") or "select")
            self.messages.appendPlainText(f"Activated runtime tool: {runtime_tool}; click the 3D viewport to create/select/edit.")

        def _activate_named_runtime_tool(self, tool_name: str) -> None:
            if self.tool_runtime is None:
                self._setup_interactive_modeling_runtime()
            output = self.tool_runtime.activate(tool_name)
            self.viewport_adapter.apply_tool_output(output)
            self.messages.appendPlainText(f"Activated geometry tool: {tool_name}")

        def _handle_phase_action(self, tool: dict[str, Any], state: dict[str, Any]) -> None:
            command = str(tool.get("command") or tool.get("key") or "select")
            if command in {"run_check", "validate_stage", "check_quality"}:
                diagnostic = self._render_scene(reset_camera=False, force=True, reason="validation")
                self.messages.appendPlainText(f"Validation: primitives={diagnostic.get('primitive_count')}, ok={diagnostic.get('ok')}")
            elif command in {"solid_linear_static_cpu", "staged_mohr_coulomb_cpu", "contact_interface_cpu"}:
                self._run_demo_complete_calculation()
            elif command in {"export_vtk", "runtime_bundle"}:
                self._export_demo_bundle()
            elif command in {"gmsh_occ_fragment_tet4_from_stl", "structured_hex8_box"}:
                self._run_demo_complete_calculation()

        # ---------- View/model panels ----------
        def _populate_panels(self, state: dict[str, Any], *, render: bool = False) -> None:
            self._populate_object_tree()
            self._populate_properties(state)
            self._populate_readiness()
            self._populate_benchmark_readiness_tabs()
            self._populate_dependency_table()
            self._populate_material_library_table()
            self._populate_workflow_spec_table()
            self.workflow.setPlainText(
                "CAD → Mesh → Solve 前处理链\n"
                "1. 拓扑选择：solid/face/edge identity\n"
                "2. 物理组：volume/surface/curve tags\n"
                "3. 网格：Gmsh/OCC + mesh entity map\n"
                "4. 求解：material / BC / load / phase readiness"
            )
            self._refresh_demo_status()
            if render:
                self._render_scene(reset_camera=False, force=True, reason="phase_render")

        def _populate_object_tree(self) -> None:
            self.left.clear()
            try:
                from geoai_simkit.app.panels.object_tree import build_compact_engineering_object_tree
                root = build_compact_engineering_object_tree(self.current_demo_project)
                self._append_tree_node(None, root)
            except Exception as exc:
                self.left.addTopLevelItem(QtWidgets.QTreeWidgetItem([f"Object tree failed: {exc}", "error"]))
            self.left.expandToDepth(1)

        def _append_tree_node(self, parent: Any, node: Any) -> None:
            item = QtWidgets.QTreeWidgetItem([str(node.label), str(node.type)])
            item.setData(0, 256, node.entity_id or "")
            item.setData(1, 256, node.type or "")
            item.setData(0, 257, getattr(node, "metadata", {}) or {})
            item.setData(1, 257, getattr(node, "source", "") or "")
            if parent is None:
                self.left.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in getattr(node, "children", []) or []:
                self._append_tree_node(item, child)

        def _on_object_tree_selection_changed(self) -> None:
            items = self.left.selectedItems()
            if not items:
                return
            entity_id = str(items[0].data(0, 256) or "")
            entity_type = str(items[0].data(1, 256) or "")
            if not entity_id:
                return
            metadata = dict(items[0].data(0, 257) or {})
            source = str(items[0].data(1, 257) or "")
            if source:
                metadata.setdefault("source", source)
            self.selection_controller.clear()
            self.selection_controller.select(entity_id, entity_type or "entity", mode="replace", metadata=metadata)
            self._sync_selected_entity_to_property_editor()
            self.viewport_adapter.render_selection(self.selection_controller.current_selection())

        def _populate_workflow_spec_table(self) -> None:
            payload = build_gui_workflow_module_payload()
            modules = list(payload.get("modules", []) or [])
            self.workflow_spec_table.setRowCount(len(modules))
            for r, module in enumerate(modules):
                elements = ", ".join(str(e.get("label", e.get("key"))) for e in list(module.get("required_elements", []) or []))
                outputs = ", ".join(str(x) for x in list(module.get("outputs", []) or []))
                checks = ", ".join(str(x) for x in list(module.get("readiness_checks", []) or []))
                values = [module.get("label", ""), module.get("workflow_stage", ""), elements, outputs, checks]
                for c, value in enumerate(values):
                    self.workflow_spec_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(value)))

        def _populate_properties(self, state: dict[str, Any]) -> None:
            rows = [
                ("版本", __version__),
                ("当前阶段", state.get("active_phase_label", "")),
                ("当前工具数", sum(len(v or []) for v in dict(state.get("toolbar_groups", {}) or {}).values())),
                ("点/线/面/体", f"{len(self.current_demo_project.geometry_model.points)} / {len(self.current_demo_project.geometry_model.curves)} / {len(self.current_demo_project.geometry_model.surfaces)} / {len(self.current_demo_project.geometry_model.volumes)}"),
                ("场景刷新策略", "dirty-only"),
                ("可浮动工具栏", "true"),
                ("可停靠面板", "true"),
            ]
            self.properties.setRowCount(len(rows))
            for r, (k, v) in enumerate(rows):
                self.properties.setItem(r, 0, QtWidgets.QTableWidgetItem(str(k)))
                self.properties.setItem(r, 1, QtWidgets.QTableWidgetItem(str(v)))

        def _populate_readiness(self) -> None:
            benchmark = getattr(self, "_last_benchmark_readiness_payload", None) or self._benchmark_report_payload()
            rows = [
                ("project", self.current_demo_project.project_settings.name),
                ("scene_revision", self._scene_revision),
                ("active_tool", getattr(self.tool_runtime, "active_tool_key", "")),
                ("selected", ", ".join(self.selection_controller.selected_ids())),
                ("step_ifc_report", benchmark.get("status", "missing_report")),
                ("benchmark_cases", benchmark.get("case_count", 0)),
                ("benchmark_blocked", benchmark.get("blocked_case_count", 0)),
                ("fix_suggestions", len(list(benchmark.get("fix_suggestions", []) or []))),
            ]
            self.readiness.setRowCount(len(rows))
            for r, (k, v) in enumerate(rows):
                self.readiness.setItem(r, 0, QtWidgets.QTableWidgetItem(str(k)))
                self.readiness.setItem(r, 1, QtWidgets.QTableWidgetItem(str(v)))

        def _populate_dependency_table(self) -> None:
            payload = build_startup_dependency_payload()
            checks = list(payload.get("report", {}).get("checks", []) or [])
            self.dependency_table.setRowCount(len(checks))
            for r, row in enumerate(checks):
                values = ["OK" if row.get("ok") else "BROKEN", row.get("group", ""), row.get("label", ""), row.get("installed_version") or "not installed", row.get("purpose", "")]
                for c, value in enumerate(values):
                    self.dependency_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(value)))

        def _refresh_demo_status(self) -> None:
            lines = [f"GeoAI SimKit {__version__}", f"Selected template: {self.selected_demo_id}", f"Loaded project: {self.current_demo_project.project_settings.name}", "", "状态保持：切换阶段/工具不会重载 Demo。"]
            if self.last_demo_run is not None:
                lines.append(f"Last run ok: {self.last_demo_run.get('ok')}")
            self.demo_status.setPlainText("\n".join(lines))

        # ---------- Geometry actions ----------
        def _set_workplane(self, name: str) -> None:
            normalized = str(name or "xz").lower()
            self.viewport_adapter.workplane.set_named_plane(normalized)
            if hasattr(self, "structure_workplane_combo"):
                target = normalized.upper()
                if self.structure_workplane_combo.currentText() != target:
                    self.structure_workplane_combo.blockSignals(True)
                    self.structure_workplane_combo.setCurrentText(target)
                    self.structure_workplane_combo.blockSignals(False)
            self.messages.appendPlainText(f"Work plane set to {normalized.upper()}.")
            self.statusBar().showMessage(f"当前工作面：{normalized.upper()}；鼠标点位会投影到该平面。")

        def _toggle_snap(self) -> None:
            enabled = bool(self.snap_action.isChecked())
            self.viewport_adapter.snap.enabled = enabled
            self.snap_action.setText("捕捉 On" if enabled else "捕捉 Off")
            if hasattr(self, "structure_snap_checkbox") and self.structure_snap_checkbox.isChecked() != enabled:
                self.structure_snap_checkbox.blockSignals(True)
                self.structure_snap_checkbox.setChecked(enabled)
                self.structure_snap_checkbox.blockSignals(False)

        def _set_snap_enabled_from_structure_panel(self, enabled: bool) -> None:
            self.viewport_adapter.snap.enabled = bool(enabled)
            if hasattr(self, "snap_action"):
                self.snap_action.blockSignals(True)
                self.snap_action.setChecked(bool(enabled))
                self.snap_action.setText("捕捉 On" if enabled else "捕捉 Off")
                self.snap_action.blockSignals(False)
            self.statusBar().showMessage("捕捉已开启：移动鼠标会显示吸附点" if enabled else "捕捉已关闭")

        def _set_snap_mode_from_structure_panel(self, mode: str, enabled: bool) -> None:
            key = str(mode).lower()
            snap = self.viewport_adapter.snap
            if key == "grid":
                snap.grid_enabled = bool(enabled)
            elif key == "endpoint":
                snap.endpoint_enabled = bool(enabled)
            elif key == "midpoint":
                snap.midpoint_enabled = bool(enabled)
            elif key == "wall_endpoint":
                snap.wall_endpoint_enabled = bool(enabled)
            elif key == "beam_endpoint":
                snap.beam_endpoint_enabled = bool(enabled)
            elif key == "anchor_endpoint":
                snap.anchor_endpoint_enabled = bool(enabled)
            elif key == "stratum_intersection":
                snap.stratum_intersection_enabled = bool(enabled)
            elif key == "excavation_intersection":
                snap.excavation_intersection_enabled = bool(enabled)
            elif key == "horizontal_constraint":
                snap.horizontal_constraint_enabled = bool(enabled)
            elif key == "vertical_constraint":
                snap.vertical_constraint_enabled = bool(enabled)
            elif key == "along_edge_constraint":
                snap.along_edge_constraint_enabled = bool(enabled)
            elif key == "along_normal_constraint":
                snap.along_normal_constraint_enabled = bool(enabled)
            self.statusBar().showMessage(f"{key} 捕捉/约束已{'开启' if enabled else '关闭'}")

        def _primitive_for_entity_id(self, entity_id: str) -> Any | None:
            if not entity_id or self.viewport_state is None:
                return None
            return next((p for p in self.viewport_state.primitives.values() if p.entity_id == entity_id or p.id == entity_id), None)

        def _constraint_lock_status_text(self) -> str:
            try:
                data = self.viewport_adapter.snap.constraint_lock_dict()
            except Exception:
                data = {}
            if not data or not data.get("enabled"):
                return "约束锁定：无"
            label = str(data.get("label") or data.get("mode") or "")
            target = str(data.get("target_entity_id") or "")
            trail_count = len(list(data.get("trail") or []))
            suffix = (f" · {target}" if target else "") + (f" · 连续点 {trail_count}" if trail_count else "")
            return f"约束锁定：{label}" + suffix

        def _refresh_constraint_lock_label(self) -> None:
            text = self._constraint_lock_status_text()
            if hasattr(self, "constraint_lock_label"):
                self.constraint_lock_label.setText(text)
            self.statusBar().showMessage(text)

        def _lock_constraint_from_current_selection(self, mode: str) -> None:
            selection = self.selection_controller.current_selection()
            items = list(getattr(selection, "items", ()) or [])
            if not items:
                self.statusBar().showMessage("请先选择一条边/线/面，或在视口中右键使用约束锁定。")
                return
            item = items[0]
            entity_id = str(getattr(item, "entity_id", "") or "")
            primitive = self._primitive_for_entity_id(entity_id)
            if primitive is None:
                self.statusBar().showMessage("当前选择没有可用于约束锁定的视口几何。")
                return
            point = (0.0, 0.0, 0.0)
            if getattr(primitive, "bounds", None) is not None:
                b = tuple(float(v) for v in primitive.bounds)
                point = ((b[0] + b[1]) * 0.5, (b[2] + b[3]) * 0.5, (b[4] + b[5]) * 0.5)
            metadata = {"source": "structure_constraint_toolbar", "primitive_id": getattr(primitive, "id", ""), **dict(getattr(primitive, "metadata", {}) or {})}
            normal = None
            try:
                n = metadata.get("normal")
                if n is not None and len(n) >= 3:
                    normal = (float(n[0]), float(n[1]), float(n[2]))
            except Exception:
                normal = None
            lock = self.viewport_adapter.snap.lock_constraint(mode, point=point, state=self.viewport_state, normal=normal, target_entity_id=entity_id, metadata=metadata)
            self._refresh_constraint_lock_label()
            try:
                self.viewport_adapter.render_constraint_lock_state(lock.to_dict())
            except Exception:
                pass
            if hasattr(self, "structure_tool_state_label"):
                self.structure_tool_state_label.setText(f"反馈：已锁定 {lock.label or lock.mode}。视口会高亮锁定边或显示法向箭头，并记录连续布置轨迹；点击解除锁定可恢复自由输入。")

        def _lock_constraint_from_pick(self, mode: str, pick: Any) -> None:
            metadata = dict(getattr(pick, "metadata", {}) or {})
            point = tuple(float(v) for v in getattr(pick, "world", (0.0, 0.0, 0.0)))
            normal = getattr(pick, "normal", None)
            if normal is None:
                try:
                    n = metadata.get("normal")
                    if n is not None and len(n) >= 3:
                        normal = (float(n[0]), float(n[1]), float(n[2]))
                except Exception:
                    normal = None
            target = str(getattr(pick, "entity_id", "") or metadata.get("source_entity_id") or "")
            lock = self.viewport_adapter.snap.lock_constraint(mode, point=point, state=self.viewport_state, normal=normal, target_entity_id=target, metadata={"source": "viewport_context_menu", **metadata})
            self._refresh_constraint_lock_label()
            try:
                self.viewport_adapter.render_constraint_lock_state(lock.to_dict())
            except Exception:
                pass
            if hasattr(self, "structure_tool_state_label"):
                self.structure_tool_state_label.setText(f"反馈：已从右键位置锁定 {lock.label or lock.mode}；视口会高亮锁定约束并显示连续布置轨迹。")

        def _unlock_viewport_constraint_lock(self) -> None:
            self.viewport_adapter.snap.unlock_constraint()
            try:
                self.viewport_adapter.render_constraint_unlock_feedback(self.viewport_adapter.snap.last_unlock_feedback_dict())
            except Exception:
                pass
            self._refresh_constraint_lock_label()
            if hasattr(self, "structure_tool_state_label"):
                self.structure_tool_state_label.setText("反馈：约束锁定已解除；视口给出解除提示，继续使用网格/端点/中点/语义吸附。")

        def _undo_geometry_command(self) -> None:
            result = self.command_stack.undo(self.current_demo_project)
            self.messages.appendPlainText(result.message or f"Undo: {result.ok}")
            self._mark_scene_dirty("undo")
            self._render_scene(reset_camera=False, force=True, reason="undo")

        def _redo_geometry_command(self) -> None:
            result = self.command_stack.redo(self.current_demo_project)
            self.messages.appendPlainText(result.message or f"Redo: {result.ok}")
            self._mark_scene_dirty("redo")
            self._render_scene(reset_camera=False, force=True, reason="redo")

        def _invert_selection(self) -> None:
            self.selection_controller.invert(self.viewport_state)
            self.viewport_adapter.render_selection(self.selection_controller.current_selection())
            self._sync_selected_entity_to_property_editor()

        def _set_combo_text(self, combo: Any, text: str) -> None:
            if not text:
                return
            index = combo.findText(text)
            if index >= 0:
                combo.setCurrentIndex(index)
            elif combo.isEditable():
                combo.setEditText(text)

        def _on_viewport_selection_changed(self, selection: Any | None = None) -> None:
            self._sync_object_tree_to_selection(selection)
            self._sync_selected_entity_to_property_editor(selection)
            if selection is not None and hasattr(self, "structure_tool_state_label"):
                items = list(getattr(selection, "items", ()) or [])
                if items:
                    item = items[0]
                    self.structure_tool_state_label.setText(f"反馈：已选中 {getattr(item, 'kind', '')} · {getattr(item, 'entity_id', '')}。可右键创建结构或执行材料赋值。")
            self._populate_readiness()

        def _sync_object_tree_to_selection(self, selection: Any | None = None) -> None:
            if not hasattr(self, "left"):
                return
            items = list(getattr(selection, "items", ()) or []) if selection is not None else []
            if not items:
                return
            target = str(getattr(items[0], "entity_id", "") or "")
            meta = dict(getattr(items[0], "metadata", {}) or {})
            aliases = {target, str(meta.get("source_entity_id") or ""), str(meta.get("source_block_id") or ""), str(meta.get("block_id") or "")}
            layer_value = str(meta.get("layer_value") or meta.get("material_id") or meta.get("picked_layer_value") or "")
            if layer_value:
                aliases.add(f"geology_layer:{layer_value}")
            aliases = {a for a in aliases if a}
            if not aliases:
                return
            blocker = getattr(self.left, "blockSignals", None)
            old_blocked = blocker(True) if blocker is not None else False
            try:
                iterator = QtWidgets.QTreeWidgetItemIterator(self.left)
                while iterator.value():
                    item = iterator.value()
                    eid = str(item.data(0, 256) or "")
                    if eid in aliases:
                        self.left.setCurrentItem(item)
                        item.setSelected(True)
                        self.left.scrollToItem(item)
                        break
                    iterator += 1
            finally:
                if blocker is not None:
                    blocker(old_blocked)

        def _sync_selected_entity_to_property_editor(self, selection: Any | None = None) -> None:
            items = list(getattr(selection, "items", ()) or []) if selection is not None else []
            if not items and hasattr(self.selection_controller, "current_selection"):
                try:
                    items = list(self.selection_controller.current_selection().items)
                except Exception:
                    items = []
            if items:
                item = items[0]
                metadata = dict(getattr(item, "metadata", {}) or {})
                kind = str(getattr(item, "kind", "") or metadata.get("picked_kind") or metadata.get("kind") or "")
                entity_id = str(getattr(item, "entity_id", "") or "")
                source_entity_id = str(metadata.get("source_entity_id") or metadata.get("source_block_id") or metadata.get("block_id") or "")
                topology_id = str(metadata.get("topology_id") or metadata.get("picked_topology_id") or "")
                display_name = str(metadata.get("name") or metadata.get("label") or "")
                if hasattr(self, "entity_name_input"):
                    self.entity_name_input.setText(display_name)
                if kind in {"face", "edge", "mesh_face", "mesh_edge", "boundary_face", "mesh_cell"}:
                    self.topology_id_input.setText(topology_id or entity_id)
                    if source_entity_id:
                        self.entity_id_input.setText(source_entity_id)
                    else:
                        self.entity_id_input.setText(entity_id)
                    if kind in {"face", "mesh_face", "boundary_face"}:
                        self._set_combo_text(self.entity_type_combo, "surface")
                    elif kind in {"edge", "mesh_edge"}:
                        self._set_combo_text(self.entity_type_combo, "edge")
                    else:
                        self._set_combo_text(self.entity_type_combo, "volume")
                else:
                    self.entity_id_input.setText(entity_id)
                    if kind in {"block", "volume", "solid", "mesh_cell"}:
                        self._set_combo_text(self.entity_type_combo, "volume")
                    elif kind in {"surface", "face"}:
                        self._set_combo_text(self.entity_type_combo, "surface")
                    elif kind in {"edge", "curve", "line"}:
                        self._set_combo_text(self.entity_type_combo, "edge")
                material_id = str(metadata.get("material_id") or "")
                if not material_id and str(entity_id).startswith("geology_layer:"):
                    material_id = self._material_for_geology_layer(str(entity_id).replace("geology_layer:", ""))
                if material_id:
                    self._set_combo_text(self.material_combo, material_id)
                role = str(metadata.get("role") or metadata.get("orientation") or "")
                if role:
                    self._set_combo_text(self.topology_role_combo, role)
                self._refresh_structure_selection_panel(entity_id or source_entity_id, kind)
                return
            selected = self.selection_controller.selected_ids()
            if selected:
                self.entity_id_input.setText(str(selected[0]))
                self._refresh_structure_selection_panel(str(selected[0]), "")
            else:
                self._refresh_structure_selection_panel("", "")

        def _refresh_structure_selection_panel(self, entity_id: str = "", kind: str = "") -> None:
            if not hasattr(self, "structure_selected_label"):
                return
            if not entity_id:
                self.structure_selected_label.setText("当前选择：无")
                if hasattr(self, "structure_material_recommendation"):
                    self.structure_material_recommendation.setText("材料建议：选择对象后显示。")
                return
            self.structure_selected_label.setText(f"当前选择：{kind or 'entity'} · {entity_id}")
            try:
                recommendation = recommended_material_for_entity(self.current_demo_project, entity_id, kind=kind)
                material_id = str(recommendation.get("material_id") or "")
                if material_id and hasattr(self, "material_combo"):
                    self._set_combo_text(self.material_combo, material_id)
                if hasattr(self, "structure_material_recommendation"):
                    self.structure_material_recommendation.setText(
                        f"材料建议：{material_id or '-'}；类别={recommendation.get('category', '-')}; 来源={recommendation.get('reason', '-')}"
                    )
            except Exception as exc:
                if hasattr(self, "structure_material_recommendation"):
                    self.structure_material_recommendation.setText(f"材料建议生成失败：{type(exc).__name__}: {exc}")

        def _selected_item_payload(self) -> tuple[str, str, dict[str, Any]]:
            try:
                selection = self.selection_controller.current_selection()
                items = list(getattr(selection, "items", ()) or [])
            except Exception:
                items = []
            if items:
                item = items[0]
                return str(getattr(item, "entity_id", "") or ""), str(getattr(item, "kind", "") or ""), dict(getattr(item, "metadata", {}) or {})
            return self.entity_id_input.text().strip(), "", {}

        def _active_mesh_layer_scalar(self) -> str:
            mesh = getattr(getattr(self.current_demo_project, "mesh_model", None), "mesh_document", None)
            if mesh is None:
                return "geology_layer_id"
            tags = dict(getattr(mesh, "cell_tags", {}) or {})
            meta = dict(getattr(mesh, "metadata", {}) or {})
            candidates = [str(meta.get("preferred_geology_scalar") or ""), str(meta.get("active_cell_scalar") or ""), "geology_layer_id", "display_group", "material_id", "soil_id", "SoilID", "layer_id", "Layer", "gmsh_physical"]
            for key in candidates:
                if key and list(tags.get(key, []) or []):
                    return key
            return "geology_layer_id"

        def _material_for_geology_layer(self, layer_value: str) -> str:
            mesh = getattr(getattr(self.current_demo_project, "mesh_model", None), "mesh_document", None)
            if mesh is None:
                return ""
            props = dict(dict(getattr(mesh, "metadata", {}) or {}).get("layer_properties", {}) or {})
            prop = dict(props.get(str(layer_value), {}) or {})
            if prop.get("material_id"):
                return str(prop.get("material_id") or "")
            scalar = self._active_mesh_layer_scalar()
            tags = dict(getattr(mesh, "cell_tags", {}) or {})
            layers = [str(v) for v in list(tags.get(scalar, []) or [])]
            mats = [str(v) for v in list(tags.get("material_id", []) or [])]
            for idx, value in enumerate(layers):
                if value == str(layer_value) and idx < len(mats):
                    return mats[idx]
            return ""

        def _ensure_soil_material(self, material_id: str) -> None:
            if not material_id:
                return
            try:
                if material_id not in self.current_demo_project.material_library.material_ids():
                    from geoai_simkit.geoproject.document import MaterialRecord
                    self.current_demo_project.material_library.soil_materials[material_id] = MaterialRecord(
                        id=material_id,
                        name=material_id,
                        model_type="mohr_coulomb_placeholder",
                        drainage="drained",
                        parameters={"gamma_unsat": 18.0, "gamma_sat": 20.0, "E_ref": 30000.0, "nu": 0.3, "c_ref": 10.0, "phi": 30.0},
                        metadata={"created_by": "apply_object_name_material"},
                    )
            except Exception:
                pass

        def _update_named_object(self, entity_id: str, kind: str, name: str, material_id: str) -> list[str]:
            changed: list[str] = []
            project = self.current_demo_project
            if entity_id in project.geometry_model.volumes:
                volume = project.geometry_model.volumes[entity_id]
                if name:
                    volume.name = name; changed.append("name")
                if material_id:
                    project.assign_entity_material(entity_id, material_id); changed.append("material")
            elif entity_id in project.geometry_model.surfaces:
                surface = project.geometry_model.surfaces[entity_id]
                if name:
                    surface.name = name; changed.append("name")
                if material_id:
                    project.assign_entity_material(entity_id, material_id); changed.append("material")
            elif entity_id in project.geometry_model.curves:
                curve = project.geometry_model.curves[entity_id]
                if name:
                    curve.name = name; changed.append("name")
                if material_id:
                    project.assign_entity_material(entity_id, material_id); changed.append("material")
            elif entity_id in project.soil_model.soil_clusters:
                cluster = project.soil_model.soil_clusters[entity_id]
                if name:
                    cluster.name = name; changed.append("name")
                if material_id:
                    cluster.material_id = material_id; changed.append("material")
                    for volume_id in list(cluster.volume_ids):
                        if volume_id in project.geometry_model.volumes:
                            project.assign_entity_material(volume_id, material_id)
            else:
                record = project.get_structure_record(entity_id)
                if record is not None:
                    if name:
                        record.name = name; changed.append("name")
                    if material_id:
                        project.assign_entity_material(entity_id, material_id); changed.append("material")
                elif entity_id == "imported_geology_model" or entity_id.startswith("geology_layer:"):
                    changed.extend(self._update_imported_geology_layer_properties(entity_id, name, material_id))
                else:
                    raise KeyError(f"未找到可编辑对象: {entity_id}")
            if changed:
                try:
                    project.mark_changed(["geometry", "soil", "structure", "material", "mesh"], action="apply_object_name_material", affected_entities=[entity_id, material_id] if material_id else [entity_id])
                except Exception:
                    pass
            return changed

        def _update_imported_geology_layer_properties(self, entity_id: str, name: str, material_id: str) -> list[str]:
            mesh = getattr(getattr(self.current_demo_project, "mesh_model", None), "mesh_document", None)
            if mesh is None:
                raise KeyError("当前项目没有导入地质网格。")
            changed: list[str] = []
            mesh.metadata.setdefault("layer_properties", {})
            props = mesh.metadata["layer_properties"]
            if entity_id == "imported_geology_model":
                if name:
                    mesh.metadata["display_name"] = name; changed.append("name")
                if material_id:
                    self._ensure_soil_material(material_id)
                    mesh.cell_tags["material_id"] = [material_id for _ in range(len(mesh.cells))]
                    changed.append("material")
                return changed
            layer = entity_id.replace("geology_layer:", "")
            row = dict(props.get(layer, {}) or {})
            if name:
                row["name"] = name; changed.append("name")
            if material_id:
                self._ensure_soil_material(material_id)
                row["material_id"] = material_id; changed.append("material")
                scalar = self._active_mesh_layer_scalar()
                layers = [str(v) for v in list(mesh.cell_tags.get(scalar, []) or [])]
                if len(layers) == len(mesh.cells):
                    mats = [str(v) for v in list(mesh.cell_tags.get("material_id", []) or [])]
                    if len(mats) != len(mesh.cells):
                        mats = ["" for _ in mesh.cells]
                    for idx, value in enumerate(layers):
                        if value == layer:
                            mats[idx] = material_id
                    mesh.cell_tags["material_id"] = mats
            props[layer] = row
            return changed

        def _apply_object_name_material(self) -> None:
            entity_id, kind, metadata = self._selected_item_payload()
            if not entity_id:
                entity_id = self.entity_id_input.text().strip()
            if not entity_id:
                self.messages.appendPlainText("No entity id specified for object info edit.")
                return
            name = self.entity_name_input.text().strip() if hasattr(self, "entity_name_input") else ""
            material = self.material_combo.currentText().strip() if hasattr(self, "material_combo") else ""
            if not name and not material:
                self.messages.appendPlainText("No name or material specified for object info edit.")
                return
            try:
                changed = self._update_named_object(entity_id, kind, name, material)
            except Exception as exc:
                self.messages.appendPlainText(f"应用名称/材料失败: {type(exc).__name__}: {exc}")
                return
            self.messages.appendPlainText(f"应用名称/材料: {entity_id}; changed={','.join(changed) or 'none'}")
            self._populate_material_library_table()
            self._populate_object_tree()
            self._mark_scene_dirty("object_name_material")
            self._render_scene(reset_camera=False, force=True, reason="object_name_material")

        def _apply_numeric_coordinates(self) -> None:
            from geoai_simkit.commands.interactive_geometry_commands import SetEntityCoordinatesCommand
            eid = self.entity_id_input.text().strip()
            if not eid:
                self.messages.appendPlainText("No entity id specified for numeric edit.")
                return
            result = self.command_stack.execute(SetEntityCoordinatesCommand(entity_id=eid, entity_type=self.entity_type_combo.currentText(), center=(float(self.coord_x.value()), float(self.coord_y.value()), float(self.coord_z.value())), dimensions=(float(self.dim_x.value()), float(self.dim_y.value()), float(self.dim_z.value()))), self.current_demo_project)
            self.messages.appendPlainText(result.message or f"Numeric edit: {result.ok}")
            self._mark_scene_dirty("numeric_edit")
            self._render_scene(reset_camera=False, force=True, reason="numeric_edit")

        def _apply_semantic_material(self) -> None:
            from geoai_simkit.commands.semantic_commands import AssignEntityMaterialCommand, AssignGeometrySemanticCommand
            eid = self.entity_id_input.text().strip()
            if not eid:
                self.messages.appendPlainText("No entity id specified for semantic/material assignment.")
                return
            semantic = self.semantic_combo.currentText().strip()
            material = self.material_combo.currentText().strip()
            if semantic:
                self.messages.appendPlainText(str(self.command_stack.execute(AssignGeometrySemanticCommand(entity_id=eid, semantic_type=semantic, material_id=material or None), self.current_demo_project).message))
            if material:
                self.messages.appendPlainText(str(self.command_stack.execute(AssignEntityMaterialCommand(entity_id=eid, material_id=material), self.current_demo_project).message))
            self._mark_scene_dirty("semantic_material")
            self._render_scene(reset_camera=False, force=True, reason="semantic_material")

        def _apply_topology_material_phase(self) -> None:
            from geoai_simkit.commands.cad_kernel_commands import AssignTopologyMaterialPhaseCommand
            tid = self.topology_id_input.text().strip()
            if not tid:
                self.messages.appendPlainText("No topology id specified.")
                return
            phase_ids = [p.strip() for p in self.topology_phase_input.text().split(",") if p.strip()]
            result = self.command_stack.execute(AssignTopologyMaterialPhaseCommand(topology_id=tid, material_id=self.material_combo.currentText().strip() or None, phase_ids=phase_ids, role=self.topology_role_combo.currentText().strip() or None), self.current_demo_project)
            self.messages.appendPlainText(result.message or f"Topology assignment: {result.ok}")
            self._mark_scene_dirty("topology_binding")
            self._render_scene(reset_camera=False, force=True, reason="topology_binding")

        def _execute_cad_features_from_gui(self) -> None:
            from geoai_simkit.commands.cad_kernel_commands import ExecuteCadFeaturesCommand
            result = self.command_stack.execute(ExecuteCadFeaturesCommand(require_native=False, allow_fallback=True), self.current_demo_project)
            self.messages.appendPlainText(result.message or f"CAD facade execution: {result.ok}")
            self._mark_scene_dirty("cad_facade")
            self._render_scene(reset_camera=False, force=True, reason="cad_facade")

        def _execute_gmsh_occ_roundtrip_from_gui(self) -> None:
            from geoai_simkit.commands.cad_kernel_commands import ExecuteGmshOccBooleanMeshRoundtripCommand
            result = self.command_stack.execute(ExecuteGmshOccBooleanMeshRoundtripCommand(require_native=False, allow_contract_fallback=True), self.current_demo_project)
            self.messages.appendPlainText(result.message or f"Gmsh/OCC roundtrip: {result.ok}")
            self._mark_scene_dirty("gmsh_roundtrip")
            self._render_scene(reset_camera=False, force=True, reason="gmsh_roundtrip")

        def _show_viewport_context_menu(self, pick: Any) -> bool:
            menu = QtWidgets.QMenu(self)
            metadata = dict(getattr(pick, "metadata", {}) or {})
            if metadata.get("context_menu_kind") == "surface_tool_completion":
                menu.addAction("完成当前面", lambda: self._commit_active_runtime_tool())
                menu.addAction("撤销上一个面点", lambda: self._send_active_runtime_key("Backspace"))
                menu.addAction("取消当前面", lambda: self._cancel_active_runtime_tool())
                menu.addSeparator()
                menu.addAction("锁定沿边约束", lambda p=pick: self._lock_constraint_from_pick("along_edge", p))
                menu.addAction("锁定沿法向约束", lambda p=pick: self._lock_constraint_from_pick("along_normal", p))
                menu.addAction("解除约束锁定", self._unlock_viewport_constraint_lock)
                menu.addSeparator()
                hint = menu.addAction("提示：左键继续加点；Enter 完成；Esc 取消；可锁定沿边/沿法向连续布点")
                hint.setEnabled(False)
                menu.exec(QtGui.QCursor.pos())
                return True
            if metadata.get("context_menu_kind") == "creation_constraint_menu":
                active = str(metadata.get("active_tool") or "创建工具")
                title = menu.addAction(f"{active} 约束工具")
                title.setEnabled(False)
                menu.addAction("锁定沿边约束", lambda p=pick: self._lock_constraint_from_pick("along_edge", p))
                menu.addAction("锁定沿法向约束", lambda p=pick: self._lock_constraint_from_pick("along_normal", p))
                menu.addAction("解除约束锁定", self._unlock_viewport_constraint_lock)
                menu.addSeparator()
                hint = menu.addAction("锁定后可连续布置墙线、梁线、锚杆点或开挖轮廓点")
                hint.setEnabled(False)
                menu.exec(QtGui.QCursor.pos())
                return True
            entity_id = str(getattr(pick, "entity_id", "") or "")
            kind = str(getattr(pick, "kind", "") or "")
            if entity_id:
                try:
                    self.selection_controller.select(entity_id, kind or "entity", mode="replace", metadata=dict(getattr(pick, "metadata", {}) or {}))
                    self._sync_selected_entity_to_property_editor(self.selection_controller.current_selection())
                    self.viewport_adapter.render_selection(self.selection_controller.current_selection())
                except Exception:
                    pass
            material = self.material_combo.currentText().strip() if hasattr(self, "material_combo") else ""
            if entity_id and not material:
                try:
                    material = str(recommended_material_for_entity(self.current_demo_project, entity_id, kind=kind).get("material_id") or "")
                except Exception:
                    material = ""
            actions = context_actions_for_selection(self.current_demo_project, entity_id, kind, material_id=material)
            if not entity_id:
                menu.addAction("创建点", lambda: self._activate_named_runtime_tool("point"))
                menu.addAction("创建线", lambda: self._activate_named_runtime_tool("line"))
                menu.addAction("创建面", lambda: self._activate_named_runtime_tool("surface"))
                menu.addAction("创建体", lambda: self._activate_named_runtime_tool("block_box"))
            else:
                title = menu.addAction(f"已选: {kind or 'entity'} · {entity_id}")
                title.setEnabled(False)
                for row in actions:
                    if row.action_id == "assign_material":
                        callback = lambda _checked=False, eid=entity_id, mid=material: self._assign_material_to_entity_from_context(eid, mid)
                    else:
                        callback = lambda _checked=False, eid=entity_id, aid=row.action_id: self._apply_structure_context_action_from_gui(eid, aid)
                    action = menu.addAction(row.label, callback)
                    action.setEnabled(bool(row.enabled))
                menu.addSeparator()
                menu.addAction("锁定沿边约束", lambda p=pick: self._lock_constraint_from_pick("along_edge", p))
                menu.addAction("锁定沿法向约束", lambda p=pick: self._lock_constraint_from_pick("along_normal", p))
                menu.addAction("解除约束锁定", self._unlock_viewport_constraint_lock)
                menu.addSeparator()
                menu.addAction("属性面板定位", lambda: self._select_entity_from_context(entity_id, kind))
            if menu.isEmpty():
                return False
            menu.exec(QtGui.QCursor.pos())
            return True


        def _send_active_runtime_key(self, key: str) -> None:
            if self.tool_runtime is None:
                return
            output = self.tool_runtime.key_press(str(key))
            self.viewport_adapter.apply_tool_output(output)
            if output.message:
                self.statusBar().showMessage(output.message)
                if hasattr(self, "structure_tool_state_label"):
                    self.structure_tool_state_label.setText(f"反馈：{output.message}")

        def _commit_active_runtime_tool(self) -> None:
            self._send_active_runtime_key("Enter")

        def _cancel_active_runtime_tool(self) -> None:
            self._send_active_runtime_key("Escape")

        def _select_entity_from_context(self, entity_id: str, kind: str = "") -> None:
            self.selection_controller.clear()
            self.selection_controller.select(entity_id, kind or "entity", mode="replace")
            self._sync_selected_entity_to_property_editor()
            self.viewport_adapter.render_selection(self.selection_controller.current_selection())
            self._populate_readiness()

        def _assign_material_to_entity_from_context(self, entity_id: str, material_id: str) -> None:
            if not material_id:
                try:
                    material_id = str(recommended_material_for_entity(self.current_demo_project, entity_id).get("material_id") or "")
                except Exception:
                    material_id = ""
            if not material_id:
                self.messages.appendPlainText("右键赋材料失败：材料为空，请先在材料库选择材料。")
                return
            try:
                payload = self.current_demo_project.assign_entity_material(entity_id, material_id)
                self.messages.appendPlainText(f"Right-click material assignment: {entity_id} -> {material_id}; ok={payload.get('ok')}")
            except Exception as exc:
                self.messages.appendPlainText(f"Right-click material assignment failed: {type(exc).__name__}: {exc}")
                return
            self._populate_material_library_table()
            self._mark_scene_dirty("context_assign_material")
            self._render_scene(reset_camera=False, force=True, reason="context_assign_material")

        def _apply_structure_context_action_from_gui(self, entity_id: str, action_id: str) -> None:
            material = self.material_combo.currentText().strip() if hasattr(self, "material_combo") else ""
            try:
                payload = apply_structure_context_action(self.current_demo_project, entity_id, action_id, material_id=material)
            except Exception as exc:
                self.messages.appendPlainText(f"Structure context action failed: {type(exc).__name__}: {exc}")
                return
            self.messages.appendPlainText(f"Structure context action: {action_id} on {entity_id}; ok={payload.get('ok')}")
            self._populate_material_library_table()
            self._populate_object_tree()
            self._populate_properties(phase_workbench_ui_state(self.active_phase))
            self._mark_scene_dirty("context_structure_action")
            self._render_scene(reset_camera=False, force=True, reason="context_structure_action")

        def _run_gui_button_smoke_from_gui(self) -> str:
            """Validate user-facing buttons after the real window has been built.

            This is a runtime smoke check for the exact symptom where the
            interface opens but buttons appear inert.  It confirms the live
            PhaseWorkbenchWindow owns each production button, that the button is
            enabled, and that it is registered in the canonical action state.
            Destructive actions are not clicked by this smoke check.
            """
            import json

            required = [
                "import_geology_model",
                "import_geology_auto",
                "import_structure_model",
                "import_structure_auto",
                "register_structure_box",
                "run_import_driven_assembly",
                "run_native_import_assembly",
                "refresh_mesh_visualization",
                "check_fem_mesh_quality",
                "optimize_fem_mesh",
                "fem_check_imported_geology",
                "fem_prepare_imported_geology",
                "fem_generate_or_repair_mesh",
                "fem_setup_automatic_stress",
                "fem_compile_solver_model",
                "fem_solve_to_steady_state",
                "fem_refresh_result_view",
                "fem_run_complete_analysis",
                "assign_material_to_selection",
                "refresh_workbench_state",
                "refresh_gui_action_audit",
                "run_gui_button_smoke",
            ]
            rows: list[dict[str, Any]] = []
            blockers: list[str] = []
            registry_ids = {str(row.get("action_id")) for row in getattr(self, "gui_action_registry", []) or []}
            for action_id in required:
                widget = getattr(self, "_gui_action_widgets", {}).get(action_id)
                row = {
                    "action_id": action_id,
                    "registered": action_id in registry_ids,
                    "widget_present": widget is not None,
                    "enabled": bool(widget.isEnabled()) if widget is not None and hasattr(widget, "isEnabled") else False,
                    "object_name": str(widget.objectName()) if widget is not None and hasattr(widget, "objectName") else "",
                    "status": self._last_gui_action_status.get(action_id, "not clicked"),
                }
                row["ok"] = bool(row["registered"] and row["widget_present"] and row["enabled"] and row["object_name"] == f"geoai-action-{action_id}")
                if not row["ok"]:
                    blockers.append(f"{action_id}: registered={row['registered']} widget_present={row['widget_present']} enabled={row['enabled']} object_name={row['object_name']}")
                rows.append(row)
            payload = {
                "contract": "geoai_simkit_runtime_button_smoke_v1",
                "ok": not blockers,
                "required_action_count": len(required),
                "registered_action_count": len(registry_ids),
                "blockers": blockers,
                "actions": rows,
                "hint": "If this report is ok but a button still appears inert, use the path field plus 按路径导入 to bypass OS file dialog focus issues and check the Last status column.",
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            if hasattr(self, "import_assembly_status"):
                self.import_assembly_status.setPlainText(text)
            if hasattr(self, "messages"):
                self.messages.appendPlainText(text)
            if hasattr(self, "gui_action_audit_table"):
                self._populate_gui_action_audit_table()
            return f"button smoke ok={payload['ok']} blockers={len(blockers)}"


        def _mesh_quality_payload_text(self) -> str:
            import json
            mesh = getattr(getattr(self.current_demo_project, "mesh_model", None), "mesh_document", None)
            if mesh is None:
                return json.dumps({"ok": False, "message": "未加载网格。"}, ensure_ascii=False, indent=2)
            quality = getattr(mesh, "quality", None)
            layer_tags = list(getattr(mesh, "cell_tags", {}).get("geology_layer_id", []) or [])
            payload = {
                "contract": "geoai_simkit_mesh_visual_quality_gui_v1",
                "node_count": getattr(mesh, "node_count", 0),
                "cell_count": getattr(mesh, "cell_count", 0),
                "cell_types": sorted(set(str(v) for v in getattr(mesh, "cell_types", []) or [])),
                "layer_count": len(set(str(v) for v in layer_tags)) if layer_tags else 0,
                "layer_tags": list(dict.fromkeys(str(v) for v in layer_tags))[:20],
                "quality": quality.to_dict() if hasattr(quality, "to_dict") else {},
                "metadata": dict(getattr(mesh, "metadata", {}) or {}).get("fem_quality_report", {}),
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        def _refresh_mesh_visualization_from_gui(self) -> str:
            try:
                from geoai_simkit.mesh.fem_quality import analyze_project_mesh_for_fem
                report = analyze_project_mesh_for_fem(self.current_demo_project)
                self.import_assembly_status.setPlainText(self._mesh_quality_payload_text())
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("refresh_mesh_visualization")
                self._render_scene(reset_camera=False, force=True, reason="refresh_mesh_visualization")
                return f"mesh visualization refreshed; ok={report.ok} bad={len(report.bad_cell_ids)}"
            except Exception as exc:
                msg = f"刷新网格显示失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        def _check_fem_mesh_quality_from_gui(self) -> str:
            try:
                from geoai_simkit.mesh.fem_quality import analyze_project_mesh_for_fem
                report = analyze_project_mesh_for_fem(self.current_demo_project)
                self.import_assembly_status.setPlainText(self._mesh_quality_payload_text())
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("check_fem_mesh_quality")
                self._render_scene(reset_camera=False, force=True, reason="check_fem_mesh_quality")
                return f"mesh quality checked; ok={report.ok} minQ={report.min_quality} aspect={report.max_aspect_ratio} bad={len(report.bad_cell_ids)}"
            except Exception as exc:
                msg = f"网格质量检查失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        def _optimize_fem_mesh_from_gui(self) -> str:
            try:
                from geoai_simkit.mesh.fem_quality import optimize_project_mesh_for_fem
                report = optimize_project_mesh_for_fem(self.current_demo_project)
                self.import_assembly_status.setPlainText(self._mesh_quality_payload_text())
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("optimize_fem_mesh")
                self._render_scene(reset_camera=False, force=True, reason="optimize_fem_mesh")
                return (
                    f"mesh optimized; ok={report.ok} nodes {report.node_count_before}->{report.node_count_after} "
                    f"cells {report.cell_count_before}->{report.cell_count_after} bad={len(report.bad_cell_ids)}"
                )
            except Exception as exc:
                msg = f"网格优化失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise


        def _identify_geology_layers_from_gui(self) -> str:
            try:
                from geoai_simkit.mesh.fem_quality import identify_geological_layers, analyze_project_mesh_for_fem
                mesh = getattr(getattr(self.current_demo_project, "mesh_model", None), "mesh_document", None)
                payload = identify_geological_layers(mesh)
                analyze_project_mesh_for_fem(self.current_demo_project)
                self.import_assembly_status.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("identify_geology_layers")
                self._render_scene(reset_camera=False, force=True, reason="identify_geology_layers")
                return f"geology layers identified; layers={payload.get('layer_count', 0)}"
            except Exception as exc:
                msg = f"地质分层识别失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        def _diagnose_nonmanifold_mesh_from_gui(self) -> str:
            try:
                from geoai_simkit.mesh.fem_quality import diagnose_nonmanifold_mesh
                mesh = getattr(getattr(self.current_demo_project, "mesh_model", None), "mesh_document", None)
                payload = diagnose_nonmanifold_mesh(mesh)
                self.import_assembly_status.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("diagnose_nonmanifold_mesh")
                self._render_scene(reset_camera=False, force=True, reason="diagnose_nonmanifold_mesh")
                return f"nonmanifold checked; nonmanifold_faces={payload.get('nonmanifold_face_count', 0)} duplicate_cells={payload.get('duplicate_cell_count', 0)}"
            except Exception as exc:
                msg = f"非流形检查失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        def _reduce_mesh_weight_from_gui(self) -> str:
            try:
                from geoai_simkit.mesh.fem_quality import reduce_mesh_weight
                mesh = getattr(getattr(self.current_demo_project, "mesh_model", None), "mesh_document", None)
                reduced, payload = reduce_mesh_weight(mesh)
                if reduced is not None:
                    self.current_demo_project.mesh_model.attach_mesh(reduced)
                    self.current_demo_project.metadata["dirty"] = True
                self.import_assembly_status.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("reduce_mesh_weight")
                self._render_scene(reset_camera=False, force=True, reason="reduce_mesh_weight")
                return f"mesh weight reduced; nodes {payload.get('node_count_before')}->{payload.get('node_count_after')} cells {payload.get('cell_count_before')}->{payload.get('cell_count_after')}"
            except Exception as exc:
                msg = f"网格降重失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        # ---------- Import-driven geology/structure assembly ----------

        def _dispatch_import_file_action(self, action_id: str, target: Any, title: str, file_filter: str, on_selected: Callable[[str], Any], *, prefer_existing_path: bool = False) -> str:
            """Run an import action from either an existing path or a file picker.

            Direct import buttons are now deterministic: if the line edit already
            contains a valid path, the action imports it immediately; otherwise it
            opens the retained non-modal file selector.  This gives users a
            working path even when the OS file dialog is suppressed by graphics
            drivers or remote desktop focus rules.
            """
            existing = target.text().strip() if target is not None and hasattr(target, "text") else ""
            if prefer_existing_path and existing and Path(existing).exists():
                self._set_gui_action_status(action_id, f"using existing path {existing}", ok=None)
                try:
                    result = self._set_import_path_then_run(target, existing, on_selected)
                except Exception as exc:
                    self._set_gui_action_status(action_id, f"{type(exc).__name__}: {exc}", ok=False)
                    return str(exc)
                self._set_gui_action_status(action_id, str(result or "done"), ok=True)
                return str(result or "done")
            self._open_import_file_dialog_async(action_id, title, file_filter, lambda path: self._set_import_path_then_run(target, path, on_selected))
            return "file chooser opened"

        def _open_import_file_dialog_async(self, action_id: str, title: str, file_filter: str, on_selected: Callable[[str], Any]) -> None:
            """Open a non-modal file chooser and run ``on_selected`` when a file is chosen.

            1.6.3 deliberately avoids the modal QFileDialog event loop for user-facing
            import buttons.  In several Windows + PyVista/VTK sessions the
            modal file dialog can be hidden behind the OpenGL window; the GUI
            then appears to have a dead button because the action only logs
            ``started`` and waits forever.  A non-modal dialog keeps the Qt event
            loop alive, is retained on ``self._active_file_dialogs``, and reports
            every transition to the action audit table.
            """
            from PySide6 import QtCore

            self._set_gui_action_status(action_id, "opening file chooser", ok=None)
            dialog = QtWidgets.QFileDialog(self, title, str(Path.cwd()), file_filter)
            dialog.setObjectName(f"geoai-file-dialog-{action_id}")
            dialog.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
            dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptOpen)
            dialog.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setWindowModality(QtCore.Qt.WindowModality.NonModal)
            dialog.setModal(False)
            try:
                dialog.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
                dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
            except Exception:
                pass
            self._active_file_dialogs[action_id] = dialog

            def cleanup() -> None:
                self._active_file_dialogs.pop(action_id, None)

            def selected(path: str) -> None:
                cleanup()
                path = str(path or "").strip()
                if not path:
                    self._set_gui_action_status(action_id, "empty file selection", ok=False)
                    return
                self._set_gui_action_status(action_id, f"selected {path}", ok=None)
                try:
                    result = on_selected(path)
                except Exception as exc:
                    self._set_gui_action_status(action_id, f"{type(exc).__name__}: {exc}", ok=False)
                    return
                if result is None:
                    result = "done"
                self._set_gui_action_status(action_id, str(result), ok=True)

            def rejected() -> None:
                cleanup()
                self._set_gui_action_status(action_id, "cancelled", ok=None)

            dialog.fileSelected.connect(selected)
            dialog.rejected.connect(rejected)
            if hasattr(self, "import_assembly_status"):
                self.import_assembly_status.setPlainText(
                    f"已打开文件选择器：{title}\n"
                    "如果没有看到文件框，请检查它是否在主窗口后方、多屏幕之外，"
                    "或直接把完整路径粘贴到路径框后点击自动识别导入。"
                )
            try:
                dialog.show()
                dialog.raise_()
                dialog.activateWindow()
            except Exception:
                pass
            QtCore.QTimer.singleShot(1500, lambda: self._set_gui_action_status(action_id, "file chooser should be visible; paste path manually if it is not", ok=None) if action_id in self._active_file_dialogs else None)

        def _select_import_file_then_run(self, action_id: str, target: Any, title: str, file_filter: str, on_selected: Callable[[str], Any], *, prefer_existing_path: bool = True) -> str:
            return self._dispatch_import_file_action(action_id, target, title, file_filter, on_selected, prefer_existing_path=prefer_existing_path)

        def _set_import_path_then_run(self, target: Any, path: str, on_selected: Callable[[str], Any]) -> Any:
            if target is not None and hasattr(target, "setText"):
                target.setText(str(path))
            return on_selected(str(path))

        def _browse_import_path(self, target: Any, title: str, file_filter: str, *, action_id: str = "browse_import_path") -> str:
            return self._select_import_file_then_run(action_id, target, title, file_filter, lambda path: f"selected {path}")

        def _maybe_get_import_path(self, target: Any, *, title: str, file_filter: str, browse_if_empty: bool = False, browse_mode: str = "if_empty") -> str:
            # Synchronous path resolution is now used only for automatic actions
            # when a path is already present in the line edit.  Direct import
            # buttons use _select_import_file_then_run instead.
            path = target.text().strip() if target is not None and hasattr(target, "text") else ""
            must_browse = browse_mode == "always" or ((not path) and (browse_if_empty or browse_mode == "if_empty"))
            if must_browse:
                raise ValueError("此动作需要先打开文件选择器；请使用对应的导入按钮或粘贴路径后点击自动识别导入。")
            if not path:
                raise ValueError("尚未选择文件路径。请点击浏览或使用对应导入按钮选择文件。")
            if not Path(path).exists():
                raise FileNotFoundError(f"文件不存在: {path}")
            return path

        def _infer_geology_source_type(self, path: str, override: str | None = None) -> str | None:
            if override and override != "native":
                return override
            suffix = Path(path).suffix.lower()
            if suffix == ".csv":
                return "borehole_csv"
            if suffix == ".stl":
                return "stl_geology"
            if suffix == ".msh":
                return "msh_geology"
            if suffix == ".vtu":
                return "vtu_geology"
            if suffix in {".ifc", ".step", ".stp"}:
                return "native"
            return None

        def _import_geology_auto_clicked(self) -> None:
            path = self.import_geology_path.text().strip() if hasattr(self, "import_geology_path") else ""
            if path:
                self._run_gui_action("import_geology_auto", lambda: self._import_geology_source_from_gui())
                return
            self._set_gui_action_status("import_geology_auto", "no path; opening file chooser", ok=None)
            self._select_import_file_then_run(
                "import_geology_auto",
                self.import_geology_path,
                "选择地质源",
                "地质/网格模型 (*.csv *.stl *.msh *.vtu *.ifc *.step *.stp);;钻孔 CSV (*.csv);;表面模型 STL (*.stl);;网格模型 MSH/VTU (*.msh *.vtu);;IFC/STEP (*.ifc *.step *.stp);;All Files (*)",
                lambda selected: self._import_geology_source_from_gui(path_override=selected),
            )

        def _import_structure_auto_clicked(self) -> None:
            path = self.import_structure_path.text().strip() if hasattr(self, "import_structure_path") else ""
            if path:
                self._run_gui_action("import_structure_auto", lambda: self._register_imported_structure_file_from_gui())
                return
            self._set_gui_action_status("import_structure_auto", "no path; opening file chooser", ok=None)
            self._select_import_file_then_run(
                "import_structure_auto",
                self.import_structure_path,
                "选择结构源",
                "结构/围护模型 (*.stl *.ifc *.step *.stp *.msh *.vtu);;STL (*.stl);;IFC/STEP (*.ifc *.step *.stp);;网格模型 MSH/VTU (*.msh *.vtu);;All Files (*)",
                lambda selected: self._register_imported_structure_file_from_gui(path_override=selected),
            )

        def _import_geology_source_from_gui(self, *, source_type_override: str | None = None, browse_if_empty: bool = False, browse_mode: str = "if_empty", file_filter: str = "地质/网格模型 (*.csv *.stl *.msh *.vtu *.ifc *.step *.stp);;钻孔 CSV (*.csv);;表面模型 STL (*.stl);;网格模型 MSH/VTU (*.msh *.vtu);;IFC/STEP (*.ifc *.step *.stp);;All Files (*)", path_override: str | None = None) -> str:
            path = str(path_override or "").strip() or self._maybe_get_import_path(self.import_geology_path if hasattr(self, "import_geology_path") else None, title="选择地质源", file_filter=file_filter, browse_if_empty=browse_if_empty, browse_mode=browse_mode)
            suffix = Path(path).suffix.lower()
            source_type = self._infer_geology_source_type(path, source_type_override)
            if source_type_override == "stl_geology" and suffix != ".stl":
                raise ValueError(f"导入地质 STL 需要 .stl 文件，当前为 {suffix or '<none>'}")
            if source_type_override == "borehole_csv" and suffix != ".csv":
                raise ValueError(f"导入钻孔 CSV 需要 .csv 文件，当前为 {suffix or '<none>'}")
            if source_type_override == "native" and suffix not in {".ifc", ".step", ".stp"}:
                raise ValueError(f"导入地质 IFC/STEP 需要 .ifc/.step/.stp 文件，当前为 {suffix or '<none>'}")
            if suffix in {".msh", ".vtu"} and source_type not in {"msh_geology", "vtu_geology", "meshio_geology", "msh", "vtu"}:
                source_type = "msh_geology" if suffix == ".msh" else "vtu_geology"
            try:
                if suffix in {".ifc", ".step", ".stp"}:
                    from geoai_simkit.services.native_import_assembly import run_native_import_assembly
                    self.current_demo_project, native_report = run_native_import_assembly(
                        geology_sources=[{"id": Path(path).stem, "path": path, "role": "geology"}],
                        options={"remesh": False, "require_native_import": bool(getattr(self, "import_assembly_require_native_import", None) and self.import_assembly_require_native_import.isChecked())},
                        name=Path(path).stem,
                    )
                    self.current_demo_project.metadata.setdefault("native_import_assembly", {})["gui_geology_import_report"] = native_report.to_dict()
                else:
                    from geoai_simkit.services.import_driven_model_assembly import create_geology_project_from_source
                    self.current_demo_project = create_geology_project_from_source(path, source_type=source_type, name=Path(path).stem)
                self.current_demo_project.metadata.update({"startup_empty_scene": False, "template_loaded": False, "scene_source": "imported_geology", "imported_geology_path": path})
                if self.tool_runtime is not None:
                    self.tool_runtime.context.document = self.current_demo_project
                self._setup_interactive_modeling_runtime()
                self.selection_controller.clear()
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("import_geology_source")
                self._render_scene(reset_camera=True, force=True, reason="import_geology_source")
                msg = f"已导入地质源：{path}；volumes={len(self.current_demo_project.geometry_model.volumes)}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                return msg
            except Exception as exc:
                msg = f"导入地质失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        def _parse_structure_bounds_from_gui(self) -> list[float]:
            text = self.structure_bounds_edit.text().strip()
            values = [float(part.strip()) for part in text.replace(";", ",").split(",") if part.strip()]
            if len(values) != 6:
                raise ValueError("Bounds 需要 6 个数字：xmin,xmax,ymin,ymax,zmin,zmax")
            return values

        def _register_structure_box_from_gui(self) -> None:
            try:
                from geoai_simkit.services.import_driven_model_assembly import register_structure_volume
                bounds = self._parse_structure_bounds_from_gui()
                kind = self.structure_kind_combo.currentText().strip()
                material = self.structure_material_edit.text().strip() or "concrete_c30"
                count = len(self.current_demo_project.geometry_model.volumes) + 1
                volume = register_structure_volume(self.current_demo_project, {"id": f"imported_{kind}_{count}", "kind": kind, "bounds": bounds, "material_id": material})
                msg = f"已注册结构：{volume.id}; bounds={list(volume.bounds or [])}; material={volume.material_id}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("register_structure_box")
                self._render_scene(reset_camera=False, force=True, reason="register_structure_box")
                return msg
            except Exception as exc:
                msg = f"注册结构失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise


        def _register_imported_structure_file_from_gui(self, *, source_type_override: str | None = None, browse_if_empty: bool = False, browse_mode: str = "if_empty", file_filter: str = "结构/围护模型 (*.stl *.ifc *.step *.stp *.msh *.vtu);;STL (*.stl);;IFC/STEP (*.ifc *.step *.stp);;网格模型 MSH/VTU (*.msh *.vtu);;All Files (*)", path_override: str | None = None) -> str:
            path = str(path_override or "").strip() or self._maybe_get_import_path(self.import_structure_path if hasattr(self, "import_structure_path") else None, title="选择结构源", file_filter=file_filter, browse_if_empty=browse_if_empty, browse_mode=browse_mode)
            suffix = Path(path).suffix.lower()
            if source_type_override == "stl" and suffix != ".stl":
                raise ValueError(f"导入结构 STL 需要 .stl 文件，当前为 {suffix or '<none>'}")
            if source_type_override == "native" and suffix not in {".ifc", ".step", ".stp"}:
                raise ValueError(f"导入结构 IFC/STEP 需要 .ifc/.step/.stp 文件，当前为 {suffix or '<none>'}")
            try:
                from geoai_simkit.services.native_import_assembly import run_native_import_assembly
                kind = self.import_structure_kind_combo.currentText().strip() if hasattr(self, "import_structure_kind_combo") else "diaphragm_wall"
                material = self.import_structure_material_edit.text().strip() if hasattr(self, "import_structure_material_edit") else "concrete_c30"
                source_type = "auto"
                if source_type_override == "stl":
                    source_type = "stl"
                elif source_type_override == "native":
                    source_type = "step" if suffix in {".step", ".stp"} else "ifc"
                self.current_demo_project, report = run_native_import_assembly(
                    project=self.current_demo_project,
                    structure_sources=[{"id": Path(path).stem, "path": path, "source_type": source_type, "role": "structure", "kind": kind, "material_id": material}],
                    options={"remesh": False, "require_native_import": bool(self.import_assembly_require_native_import.isChecked()) if hasattr(self, "import_assembly_require_native_import") else False},
                )
                payload = report.to_dict()
                import json
                self.import_assembly_status.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
                msg = f"已导入结构 cutter：{path}; volumes={payload.get('structure_volume_ids')}"
                self.messages.appendPlainText(msg)
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("register_imported_structure_file")
                self._render_scene(reset_camera=False, force=True, reason="register_imported_structure_file")
                return msg
            except Exception as exc:
                msg = f"导入结构失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        def _run_native_import_assembly_from_gui(self) -> None:
            try:
                from geoai_simkit.services.native_import_assembly import run_native_import_assembly
                self.current_demo_project, report = run_native_import_assembly(
                    project=self.current_demo_project,
                    options={
                        "element_size": float(self.import_assembly_element_size.value()),
                        "preserve_original_geology": bool(self.import_assembly_preserve_original.isChecked()),
                        "require_native_import": bool(self.import_assembly_require_native_import.isChecked()),
                        "require_native_boolean": bool(self.import_assembly_require_native_boolean.isChecked()),
                        "remesh": True,
                    },
                )
                payload = report.to_dict()
                import json
                self.import_assembly_status.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
                msg = f"1.6 Native Import Assembly 完成：ok={payload.get('ok')} fallback={payload.get('fallback_used')} native_import={payload.get('native_import_used')}"
                self.messages.appendPlainText(msg)
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("native_import_assembly")
                self._render_scene(reset_camera=False, force=True, reason="native_import_assembly")
                return msg
            except Exception as exc:
                msg = f"1.6 Native Import Assembly 失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        def _run_import_driven_assembly_from_gui(self) -> None:
            try:
                from geoai_simkit.services.import_driven_model_assembly import subtract_structure_overlaps_from_geology
                report = subtract_structure_overlaps_from_geology(
                    self.current_demo_project,
                    options={
                        "element_size": float(self.import_assembly_element_size.value()),
                        "preserve_original_geology": bool(self.import_assembly_preserve_original.isChecked()),
                        "require_native_boolean": bool(getattr(self, "import_assembly_require_native_boolean", None) and self.import_assembly_require_native_boolean.isChecked()),
                        "boolean_mode": "native_gmsh_occ_if_available" if bool(getattr(self, "import_assembly_require_native_boolean", None) and self.import_assembly_require_native_boolean.isChecked()) else "aabb_fallback",
                        "remesh": True,
                    },
                )
                payload = report.to_dict()
                import json
                self.import_assembly_status.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
                msg = f"导入拼接完成：ok={payload.get('ok')} generated={payload.get('generated_soil_volume_count')} mesh_cells={payload.get('mesh_report', {}).get('cell_count')}"
                self.messages.appendPlainText(msg)
                self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
                self._mark_scene_dirty("import_driven_assembly")
                self._render_scene(reset_camera=False, force=True, reason="import_driven_assembly")
                return msg
            except Exception as exc:
                msg = f"导入拼接失败: {type(exc).__name__}: {exc}"
                self.import_assembly_status.setPlainText(msg)
                self.messages.appendPlainText(msg)
                raise

        # ---------- Demo/background ----------
        def _select_demo_template(self) -> None:
            data = self.demo_selector.currentData()
            if data:
                self.selected_demo_id = str(data)
                self._refresh_demo_status()

        def _load_demo_project(self) -> None:
            self.current_demo_project = load_demo_project(self.selected_demo_id)
            self.current_demo_project.metadata.update({"startup_empty_scene": False, "template_loaded": True, "scene_source": "template", "template_id": self.selected_demo_id})
            if self.tool_runtime is not None:
                self.tool_runtime.context.document = self.current_demo_project
            self._scene_revision = 0
            self._last_render_revision = -1
            self.selection_controller.clear()
            self._setup_interactive_modeling_runtime()
            self._populate_panels(phase_workbench_ui_state(self.active_phase), render=False)
            self._render_scene(reset_camera=True, force=True, reason="load_demo")
            self.messages.appendPlainText(f"Loaded demo template: {self.selected_demo_id}")

        def _set_demo_buttons_enabled(self, enabled: bool) -> None:
            for button in (self.load_demo_button, self.run_demo_button, self.export_demo_button, self.run_all_demo_button):
                button.setEnabled(bool(enabled))

        def _start_background_operation(self, label: str, fn: Callable[[], Any], on_success: Callable[[Any], None]) -> None:
            if self._operation_running:
                self.messages.appendPlainText(f"Operation already running; ignored: {label}")
                return
            self._operation_running = True
            self._set_demo_buttons_enabled(False)
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            self.messages.appendPlainText(f"Started: {label}")
            future = self._executor.submit(fn)
            self._active_future = future
            timer = QtCore.QTimer(self); timer.setInterval(120); self._active_timer = timer
            def cleanup() -> None:
                try: QtWidgets.QApplication.restoreOverrideCursor()
                except Exception: pass
                self._operation_running = False
                self._set_demo_buttons_enabled(True)
                timer.stop(); timer.deleteLater(); self._active_timer = None; self._active_future = None
                self._refresh_demo_status()
            def poll() -> None:
                try:
                    self._drain_analysis_progress_events()
                except Exception:
                    pass
                if not future.done(): return
                try:
                    result = future.result(); on_success(result); self.messages.appendPlainText(f"Finished: {label}")
                except Exception as exc:
                    self.messages.appendPlainText(f"{label} failed: {type(exc).__name__}: {exc}")
                    QtWidgets.QMessageBox.warning(self, "Operation failed", f"{type(exc).__name__}: {exc}")
                finally:
                    cleanup()
            timer.timeout.connect(poll); timer.start()

        def _run_demo_complete_calculation(self) -> None:
            demo_id = str(self.selected_demo_id)
            target = Path.cwd() / "exports" / "release_1_4_6_gui_demo_run" / demo_id
            def work(): return run_demo_complete_calculation(demo_id, output_dir=target)
            def success(result) -> None:
                self.last_demo_run = result.to_dict(include_project=False) if hasattr(result, "to_dict") else dict(result)
                # Keep the current edited project by default. The calculation bundle is external.
                self.messages.appendPlainText(f"Complete calculation finished externally: demo={demo_id}, ok={self.last_demo_run.get('ok')}")
                self._refresh_demo_status()
            self._start_background_operation(f"运行模板完整流程：{demo_id}", work, success)

        def _run_all_demo_templates(self) -> None:
            target = Path.cwd() / "exports" / "release_1_4_6_gui_all_templates"
            self._start_background_operation("运行全部模板", lambda: run_all_demo_calculations(output_dir=target), lambda result: setattr(self, "last_demo_run", {"ok": result.get("ok"), "workflow": result, "artifacts": result.get("artifacts", {})}))

        def _export_demo_bundle(self) -> None:
            if self.last_demo_run is None:
                self.messages.appendPlainText("No review bundle exists; run calculation first.")
                return
            self.messages.appendPlainText(f"Review bundle: {(self.last_demo_run or {}).get('artifacts', {})}")

        def _reset_camera(self) -> None:
            try:
                self.viewport_widget.reset_camera(); self.viewport_adapter.safe_render(reason="reset_camera")
            except Exception:
                pass

        def closeEvent(self, event) -> None:  # type: ignore[override]
            self._closing = True
            try:
                if hasattr(self, "viewport_widget"):
                    setattr(self.viewport_widget, "_geoai_closing", True)
                if hasattr(self, "viewport_adapter"):
                    self.viewport_adapter.suspend_rendering("window_closing")
                if self._active_timer is not None:
                    self._active_timer.stop()
                self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            super().closeEvent(event)

    window = PhaseWorkbenchWindow()
    window.show()
    app.exec()


__all__ = ["build_phase_workbench_qt_payload", "launch_phase_workbench_qt"]
