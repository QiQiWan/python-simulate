from __future__ import annotations

"""GUI workflow module contracts for CAD-to-FEM preprocessing.

The desktop GUI is easier to keep usable when each workbench module has an
explicit element contract.  These contracts are headless: tests and payload
builders can validate the required controls without importing Qt, VTK, OCP, or
Gmsh.  The module matrix is also used by the bottom "模块界面" tab so that the
running GUI exposes the same workflow structure that tests validate.
"""

from dataclasses import dataclass, field
from typing import Any

GUI_WORKFLOW_MODULE_SPEC_CONTRACT = "geoai_simkit_gui_workflow_module_spec_v2"


@dataclass(frozen=True, slots=True)
class GuiElementSpec:
    key: str
    label: str
    element_type: str
    purpose: str
    required: bool = True
    actions: tuple[str, ...] = ()
    binds_to: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "element_type": self.element_type,
            "purpose": self.purpose,
            "required": bool(self.required),
            "actions": list(self.actions),
            "binds_to": list(self.binds_to),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class GuiWorkflowModuleSpec:
    key: str
    label: str
    workflow_stage: str
    purpose: str
    primary_entities: tuple[str, ...]
    required_elements: tuple[GuiElementSpec, ...]
    outputs: tuple[str, ...]
    readiness_checks: tuple[str, ...] = ()
    panel_region: str = "bottom_tab"
    lifecycle_position: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "workflow_stage": self.workflow_stage,
            "purpose": self.purpose,
            "primary_entities": list(self.primary_entities),
            "required_elements": [item.to_dict() for item in self.required_elements],
            "outputs": list(self.outputs),
            "readiness_checks": list(self.readiness_checks),
            "panel_region": self.panel_region,
            "lifecycle_position": int(self.lifecycle_position),
        }


def _element(
    key: str,
    label: str,
    element_type: str,
    purpose: str,
    *,
    actions: tuple[str, ...] = (),
    binds_to: tuple[str, ...] = (),
    required: bool = True,
    metadata: dict[str, Any] | None = None,
) -> GuiElementSpec:
    return GuiElementSpec(
        key=key,
        label=label,
        element_type=element_type,
        purpose=purpose,
        required=required,
        actions=actions,
        binds_to=binds_to,
        metadata=dict(metadata or {}),
    )


def build_gui_workflow_module_specs() -> list[GuiWorkflowModuleSpec]:
    return [
        GuiWorkflowModuleSpec(
            key="project_data_intake",
            label="项目 / 数据导入",
            workflow_stage="project_setup",
            purpose="管理工程模板、坐标单位、STEP/IFC/STL/地层数据导入、依赖自检和数据完整性。",
            primary_entities=("project", "template", "cad_file", "ifc_file", "geology_file", "dependency_report"),
            panel_region="left_browser_and_bottom_tabs",
            lifecycle_position=10,
            required_elements=(
                _element("template_selector", "模板选择器", "combo", "选择基坑、隧道、边坡、基础等工程模板。", actions=("select_template",), binds_to=("demo_catalog", "project_lifecycle")),
                _element("import_buttons", "导入按钮组", "button_group", "导入 STEP/STP/IFC/STL/CSV/JSON 工程数据。", actions=("import_step", "import_ifc", "import_stl", "import_geology_csv"), binds_to=("cad_shape_store", "geology_model", "mesh_model")),
                _element("unit_coordinate_panel", "单位与坐标面板", "form", "设置长度单位、重力方向、工程坐标基准。", actions=("set_units", "set_gravity", "set_project_origin"), binds_to=("project.metadata", "solver_model")),
                _element("dependency_preflight_table", "依赖自检表", "table", "显示 OCP、IfcOpenShell、Gmsh、VTK、PyVistaQt 等桌面依赖状态。", actions=("refresh_dependency_preflight",), binds_to=("startup_dependency_screen",)),
            ),
            outputs=("project_document", "source_file_registry", "dependency_status", "native_runtime_status"),
            readiness_checks=("required_dependencies_available", "project_units_defined", "at_least_one_geometry_source"),
        ),
        GuiWorkflowModuleSpec(
            key="structure_modeling",
            label="结构 / 几何建模",
            workflow_stage="cad_authoring",
            purpose="通过鼠标创建点、线、面、体，并把选中几何提升为墙、梁、锚杆、板、界面、土体或开挖对象。",
            primary_entities=("point", "curve", "surface", "volume", "structure"),
            panel_region="top_toolbar_and_viewport",
            lifecycle_position=20,
            required_elements=(
                _element("workplane_selector", "工作面切换", "toolbar_action_group", "在 XZ、XY、YZ 工作面之间切换。", actions=("set_workplane_xz", "set_workplane_xy", "set_workplane_yz"), binds_to=("viewport.workplane",)),
                _element("create_point", "创建点", "toolbar_action", "在当前工作面或拾取点创建控制点。", actions=("activate_point_tool",), binds_to=("geometry_model.points",)),
                _element("create_line", "创建线", "toolbar_action", "两次点击创建梁、锚杆、支撑轴线或几何边。", actions=("activate_line_tool",), binds_to=("geometry_model.curves",)),
                _element("create_surface", "创建面", "toolbar_action", "多点创建墙、板、界面或边界面，右键完成。", actions=("activate_surface_tool",), binds_to=("geometry_model.surfaces",)),
                _element("create_volume", "创建体", "toolbar_action", "两点创建轴对齐体，用于土层、开挖区或结构体。", actions=("activate_block_box_tool",), binds_to=("geometry_model.volumes",)),
                _element("transform_gizmo", "三轴编辑手柄", "viewport_overlay", "对选中对象执行移动、复制、旋转、缩放和轴向约束拖拽。", actions=("move", "copy", "rotate", "scale", "axis_constrained_drag"), binds_to=("selection_state", "command_stack")),
                _element("viewport_context_menu", "三维右键菜单", "context_menu", "对选中的点/线/面/体直接创建工程结构或赋材料。", actions=("promote_to_soil", "promote_to_wall", "promote_to_beam", "promote_to_anchor", "assign_material"), binds_to=("selection_state", "structure_model", "material_library")),
                _element("selection_filter", "选择过滤器", "combo", "限定拾取对象类型，减少误选。", actions=("set_pick_filter",), binds_to=("viewport_selection",)),
            ),
            outputs=("editable_geometry", "structure_records", "topology_selection", "operation_history"),
            readiness_checks=("mouse_event_bound", "active_tool_visible", "right_click_actions_available", "selection_to_property_panel", "undo_redo_available"),
        ),
        GuiWorkflowModuleSpec(
            key="native_cad_topology",
            label="Native CAD / 拓扑身份",
            workflow_stage="native_geometry_certification",
            purpose="把 STEP/IFC/OCC 子形状映射为稳定的 solid/face/edge identity，并追踪布尔 split/merge lineage。",
            primary_entities=("TopoDS_Shape", "IfcProduct", "solid", "face", "edge", "operation_lineage"),
            panel_region="right_inspector_and_bottom_benchmark",
            lifecycle_position=30,
            required_elements=(
                _element("cad_shape_store_view", "CadShapeStore 视图", "table", "显示 shape record、source GUID、BRep reference 和 topology counts。", actions=("inspect_shape_store",), binds_to=("cad_shape_store",)),
                _element("face_edge_pick_status", "Face/Edge 拾取状态", "status_panel", "显示当前 cell-aware picking 的 cell_id、face_id、edge_id、shape_id。", actions=("inspect_pick",), binds_to=("viewport_selection", "topology_identity_index")),
                _element("lineage_view", "布尔 lineage 视图", "table", "展示 preserved、split、merge、generated、deleted 的映射和置信度。", actions=("inspect_lineage",), binds_to=("operation_lineage",)),
                _element("persistent_naming_check", "Persistent naming 检查", "button", "重复导入或重复操作后检查 topology identity 是否稳定。", actions=("run_persistent_naming_check",), binds_to=("benchmark_report", "topology_identity_index")),
            ),
            outputs=("topology_identity_index", "stable_selection_keys", "lineage_report", "native_certification_status"),
            readiness_checks=("native_loader_available", "solid_face_edge_topology_present", "persistent_naming_not_duplicate", "lineage_confidence_reported"),
        ),
        GuiWorkflowModuleSpec(
            key="material_library",
            label="材料库 / 快速赋值",
            workflow_stage="property_assignment",
            purpose="统一管理土体、板墙、梁锚杆和界面材料，并支持按选择对象、土层或结构类型快速赋值。",
            primary_entities=("soil_material", "plate_material", "beam_material", "interface_material"),
            panel_region="right_inspector",
            lifecycle_position=40,
            required_elements=(
                _element("material_category", "材料类别", "combo", "在土体、板墙、梁/锚杆、界面之间切换。", actions=("filter_materials",), binds_to=("material_library",)),
                _element("material_table", "材料表", "table", "显示所有材料 ID、名称、模型、排水类型和主要参数。", actions=("select_material",), binds_to=("material_library",)),
                _element("material_form", "材料编辑表单", "form", "创建或更新材料参数。", actions=("upsert_material",), binds_to=("material_library",)),
                _element("assign_selected", "赋给选中对象", "button", "把当前材料赋给已选土层、体、墙、梁、锚杆或界面。", actions=("assign_material_to_selection",), binds_to=("selection_state", "geometry_model", "structure_model")),
                _element("auto_assign_layers", "按地层快速赋值", "button", "根据 soil cluster / layer / volume role 将土层批量绑定材料。", actions=("auto_assign_soil_layers",), binds_to=("soil_model", "geometry_model.volumes")),
            ),
            outputs=("material_library", "material_assignments", "solver_region_material_map"),
            readiness_checks=("volume_materials_present", "structure_materials_present", "no_unknown_material_ids"),
        ),
        GuiWorkflowModuleSpec(
            key="stage_and_construction_sequence",
            label="施工阶段 / 激活失活",
            workflow_stage="phase_assignment",
            purpose="定义开挖、支护、回填、加载、降水等阶段，并把实体、材料、边界条件绑定到阶段。",
            primary_entities=("stage", "activation", "deactivation", "construction_event"),
            panel_region="right_inspector_and_bottom_workflow",
            lifecycle_position=50,
            required_elements=(
                _element("stage_timeline", "阶段时间线", "timeline", "显示阶段顺序、当前阶段、激活/失活对象。", actions=("select_stage", "reorder_stage"), binds_to=("construction_stage_model",)),
                _element("activation_buttons", "激活/失活按钮", "button_group", "把当前选中的 soil/structure/support 在阶段中激活或失活。", actions=("activate_selection", "deactivate_selection"), binds_to=("selection_state", "stage_model")),
                _element("stage_property_table", "阶段属性表", "table", "显示阶段边界条件、荷载、材料变化和计算设置。", actions=("edit_stage_property",), binds_to=("stage_model", "solver_model")),
            ),
            outputs=("stage_sequence", "activation_map", "phase_solver_steps"),
            readiness_checks=("stage_order_valid", "active_regions_exist", "stage_boundary_conditions_defined"),
        ),
        GuiWorkflowModuleSpec(
            key="topology_preprocess",
            label="拓扑 / 前处理",
            workflow_stage="cad_fem_bridge",
            purpose="把 solid/face/edge 选择转为 physical group、边界候选、局部网格控制和求解前检查项。",
            primary_entities=("solid", "face", "edge", "physical_group", "boundary_candidate"),
            panel_region="right_inspector_and_bottom_readiness",
            lifecycle_position=60,
            required_elements=(
                _element("topology_identity_table", "拓扑 ID 表", "table", "列出选中对象的 shape/topology/phase/material identity。", actions=("inspect_topology_identity",), binds_to=("topology_identity_index",)),
                _element("bc_load_buttons", "边界/荷载按钮", "button_group", "从 face/edge 快速创建约束、面荷载、线荷载和界面。", actions=("create_bc", "create_surface_load", "create_line_load", "create_interface"), binds_to=("selection_state", "solver_model")),
                _element("mesh_control_editor", "局部网格控制", "form", "对选中 solid/face/edge 设置目标单元尺寸。", actions=("set_local_mesh_size",), binds_to=("mesh_model.mesh_settings.local_size_fields",)),
                _element("physical_group_table", "Physical group 表", "table", "显示 volume/surface/curve 的 Gmsh physical group 计划。", actions=("refresh_physical_groups",), binds_to=("cad_fem_preprocessor.physical_groups",)),
            ),
            outputs=("physical_groups", "boundary_conditions", "mesh_controls", "solver_precheck"),
            readiness_checks=("topology_identity_available", "physical_groups_generated", "boundary_candidates_available"),
        ),
        GuiWorkflowModuleSpec(
            key="meshing_workbench",
            label="网格划分 / 质量检查",
            workflow_stage="meshing",
            purpose="把 CAD physical groups 写入 Gmsh/meshio，生成体网格、局部加密、质量指标和实体映射。",
            primary_entities=("mesh", "physical_volume", "physical_surface", "size_field", "mesh_quality"),
            panel_region="bottom_readiness_and_viewport",
            lifecycle_position=70,
            required_elements=(
                _element("mesher_backend_selector", "网格后端选择", "combo", "选择 Gmsh OCC、fallback mesher 或导入 meshio 网格。", actions=("select_mesher_backend",), binds_to=("mesh_model.backend",)),
                _element("global_mesh_size", "全局单元尺寸", "numeric_input", "设置默认 tet4/tet10 单元尺寸。", actions=("set_global_mesh_size",), binds_to=("mesh_model.mesh_settings.global_size",)),
                _element("local_size_table", "局部尺寸表", "table", "显示 face/edge/solid 级网格加密控制。", actions=("edit_local_mesh_size",), binds_to=("mesh_model.mesh_settings.local_size_fields",)),
                _element("mesh_quality_table", "网格质量表", "table", "检查 skewness、aspect ratio、Jacobian、孤立单元和未赋材料单元。", actions=("refresh_mesh_quality",), binds_to=("mesh_quality_report",)),
                _element("mesh_entity_map_view", "网格实体映射", "table", "检查 cell/face tags 是否能回溯 physical group 与 topology key。", actions=("inspect_mesh_entity_map",), binds_to=("planned_mesh_entity_map", "meshio_tags")),
            ),
            outputs=("volume_mesh", "mesh_quality_report", "mesh_entity_map", "physical_tag_map"),
            readiness_checks=("volume_cells_exist", "mesh_tags_complete", "mesh_quality_above_threshold", "no_orphan_cells"),
        ),
        GuiWorkflowModuleSpec(
            key="solver_setup_and_run",
            label="求解设置 / 运行",
            workflow_stage="solver_setup",
            purpose="完成材料区域、边界条件、荷载、阶段步、线性/非线性设置和求解运行控制。",
            primary_entities=("solver_case", "dof", "load", "boundary_condition", "solve_job"),
            panel_region="bottom_workflow_and_statusbar",
            lifecycle_position=80,
            required_elements=(
                _element("solver_backend_selector", "求解器后端", "combo", "选择 CPU sparse、GPU experimental 或外部求解器。", actions=("select_solver_backend",), binds_to=("solver_model.backend",)),
                _element("bc_load_table", "边界/荷载表", "table", "显示约束、面荷载、线荷载、体力、孔压和阶段归属。", actions=("edit_bc_load",), binds_to=("solver_model.boundary_conditions", "solver_model.loads")),
                _element("solve_precheck_table", "求解前检查表", "table", "阻止缺材料、缺约束、无体网格、刚体模态风险的模型进入求解。", actions=("refresh_solve_precheck",), binds_to=("cad_fem_preprocessor", "solver_model", "mesh_model")),
                _element("run_cancel_buttons", "运行/取消按钮", "button_group", "启动或取消求解任务，状态写入底部日志。", actions=("run_solver", "cancel_solver"), binds_to=("job_service", "solver_model")),
            ),
            outputs=("solve_job", "solver_log", "result_dataset", "convergence_report"),
            readiness_checks=("solver_region_map_complete", "boundary_conditions_present", "loads_or_initial_conditions_present", "job_can_start"),
        ),
        GuiWorkflowModuleSpec(
            key="results_and_reporting",
            label="结果 / 报告",
            workflow_stage="postprocess",
            purpose="查看位移、应力、塑性区、安全系数、阶段曲线和工程报告导出。",
            primary_entities=("result_field", "stage_curve", "safety_factor", "report"),
            panel_region="viewport_and_bottom_results",
            lifecycle_position=90,
            required_elements=(
                _element("result_field_selector", "结果场选择", "combo", "选择 displacement、stress、strain、plasticity、pore pressure 等结果场。", actions=("select_result_field",), binds_to=("result_dataset",)),
                _element("legend_colorbar", "图例 / 色标", "viewport_overlay", "显示结果云图范围、单位和颜色标尺。", actions=("set_result_range",), binds_to=("viewport.result_overlay",)),
                _element("probe_tool", "结果探针", "viewport_tool", "点选节点/单元查看数值。", actions=("probe_result",), binds_to=("result_dataset", "mesh_entity_map")),
                _element("report_export_buttons", "报告导出", "button_group", "导出 JSON、CSV、PNG、工程审查包。", actions=("export_report", "export_screenshots", "export_result_tables"), binds_to=("result_dataset", "report_service")),
            ),
            outputs=("visual_result_layers", "result_tables", "engineering_report_bundle"),
            readiness_checks=("result_dataset_available", "selected_field_exists", "report_artifacts_writable"),
        ),
        GuiWorkflowModuleSpec(
            key="benchmark_readiness",
            label="Benchmark / Readiness / 修复建议",
            workflow_stage="verification_and_repair",
            purpose="加载 STEP/IFC native benchmark report、GUI readiness report 和失败 case blockers，并把 blocker 映射为可点击修复建议。",
            primary_entities=("benchmark_case", "blocker", "warning", "fix_suggestion"),
            panel_region="bottom_tabs_and_floating_help",
            lifecycle_position=100,
            required_elements=(
                _element("readiness_table", "Readiness 表", "table", "汇总缺失材料、缺失约束、网格质量和 benchmark 状态。", actions=("refresh_readiness",), binds_to=("cad_fem_preprocessor", "benchmark_report")),
                _element("benchmark_table", "Benchmark 表", "table", "显示 STEP/IFC native benchmark case 结果。", actions=("open_case",), binds_to=("step_ifc_native_benchmark_report",)),
                _element("fix_suggestion_table", "修复建议", "table", "把 blockers 映射为可点击修复动作。", actions=("show_fix_detail",), binds_to=("benchmark_blockers", "precheck_blockers")),
                _element("floating_help_window", "可浮动说明工具窗", "dock_widget", "点击 case 或修复建议时显示上下文说明、命令和 artifact 路径。", actions=("show_case_detail", "show_fix_detail"), binds_to=("fix_suggestions", "case_rows")),
            ),
            outputs=("ready_for_meshing", "ready_for_solve", "blockers", "fix_suggestions", "native_certification_evidence"),
            readiness_checks=("mesh_exists", "mesh_quality_ok", "solver_material_map_complete", "benchmark_failures_reviewed", "fix_suggestions_available_for_blockers"),
        ),
        GuiWorkflowModuleSpec(
            key="runtime_diagnostics",
            label="运行诊断 / 日志",
            workflow_stage="runtime_observability",
            purpose="统一显示日志、3D 诊断、依赖自检、OpenGL/VTK 状态和后台任务状态，避免日志框散落在界面各处。",
            primary_entities=("log", "diagnostic", "vtk_context", "background_job"),
            panel_region="bottom_tabs",
            lifecycle_position=110,
            required_elements=(
                _element("unified_log_tab", "统一日志 Tab", "plain_text", "所有运行消息、后台任务消息和用户操作日志进入底部日志。", actions=("append_log", "clear_log"), binds_to=("runtime_log",)),
                _element("viewport_diagnostic_tab", "3D 诊断 Tab", "plain_text", "显示 VTK/PyVista 渲染状态、primitive 数量、bounds、OpenGL 错误降级状态。", actions=("refresh_3d_diagnostic",), binds_to=("viewport_adapter.metadata",)),
                _element("opengl_guard_status", "OpenGL 上下文保护状态", "status_panel", "当 wglMakeCurrent 或上下文失效时暂停渲染、记录提示并允许 Qt-only 降级。", actions=("suspend_render", "enable_qt_only_fallback"), binds_to=("vtk_opengl_runtime_policy", "viewport_adapter")),
                _element("dependency_tab", "依赖自检 Tab", "table", "集中显示依赖状态，替代分散说明。", actions=("refresh_dependency_table",), binds_to=("dependency_preflight",)),
            ),
            outputs=("runtime_diagnostics", "render_guard_state", "dependency_report", "support_bundle"),
            readiness_checks=("logs_are_centralized", "render_context_guard_enabled", "diagnostic_tabs_present"),
        ),
    ]


def build_gui_workflow_module_payload() -> dict[str, Any]:
    modules = build_gui_workflow_module_specs()
    missing_required = []
    duplicate_keys: set[str] = set()
    seen_keys: set[str] = set()
    for module in modules:
        if module.key in seen_keys:
            duplicate_keys.add(module.key)
        seen_keys.add(module.key)
        for element in module.required_elements:
            if element.required and not element.key:
                missing_required.append({"module": module.key, "element": element.label})
    lifecycle = [module.lifecycle_position for module in modules]
    return {
        "contract": GUI_WORKFLOW_MODULE_SPEC_CONTRACT,
        "module_count": len(modules),
        "modules": [module.to_dict() for module in modules],
        "missing_required_elements": missing_required,
        "duplicate_module_keys": sorted(duplicate_keys),
        "lifecycle_order": [module.key for module in sorted(modules, key=lambda row: row.lifecycle_position)],
        "panel_regions": sorted({module.panel_region for module in modules}),
        "ok": not missing_required and not duplicate_keys and lifecycle == sorted(lifecycle),
    }


__all__ = [
    "GUI_WORKFLOW_MODULE_SPEC_CONTRACT",
    "GuiElementSpec",
    "GuiWorkflowModuleSpec",
    "build_gui_workflow_module_specs",
    "build_gui_workflow_module_payload",
]
