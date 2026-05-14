from __future__ import annotations

"""Headless six-phase workbench definitions for the GUI shell."""

from geoai_simkit.contracts.gui_workflow import (
    PhaseCommandSpec,
    PhasePanelSpec,
    PhaseToolbarSpec,
    PhaseToolSpec,
    WorkbenchPhase,
    WorkbenchPhaseKey,
    WorkbenchPhaseState,
)


def _runtime_tool_for(key: str, mode: str) -> str:
    explicit = {
        "select": "select",
        "point": "point",
        "line": "line",
        "surface": "surface",
        "create_geology_point": "point",
        "create_soil_surface": "surface",
        "create_strata": "block_box",
        "block_box": "block_box",
    }
    if key in explicit:
        return explicit[key]
    return {
        "create_point": "point",
        "create_line": "line",
        "create_surface": "surface",
        "create_volume": "block_box",
    }.get(mode, "select")


def _tool(key: str, label: str, group: str, mode: str = "select", command: str = "", tooltip: str = "") -> PhaseToolSpec:
    runtime_tool = _runtime_tool_for(key, mode)
    return PhaseToolSpec(
        key=key,
        label=label,
        group=group,
        interaction_mode=mode,
        command=command or key,
        tooltip=tooltip,
        metadata={"runtime_tool": runtime_tool, "phase_toolbar_contract": "plaxis_like_phase_toolbar_v1"},
    )


def _panel(key: str, label: str, position: str = "left", component: str = "") -> PhasePanelSpec:
    return PhasePanelSpec(key=key, label=label, position=position, component=component or key)


def _command(key: str, label: str, controller: str, method: str) -> PhaseCommandSpec:
    return PhaseCommandSpec(key=key, label=label, controller=controller, method=method)


def build_workbench_phases() -> tuple[WorkbenchPhase, ...]:
    geology_tools = (
        _tool("select", "Select", "selection", "select"),
        _tool("import_stl", "Import STL", "import", "repair_geometry", "import_stl"),
        _tool("optimize_stl", "Optimize STL", "repair", "repair_geometry", "optimize_project_complex_stl_surface"),
        _tool("repair_holes", "Repair Holes", "repair", "repair_geometry"),
        _tool("reorient_normals", "Reorient Normals", "repair", "repair_geometry"),
        _tool("create_geology_point", "Create Point", "create", "create_point"),
        _tool("create_soil_surface", "Create Surface", "create", "create_surface"),
        _tool("create_strata", "Create Soil Volume", "create", "create_volume"),
        _tool("assign_geology_material", "Assign Material", "assign", "assign_semantics"),
    )
    structures_tools = (
        _tool("select", "Select", "selection", "select"),
        _tool("point", "Point", "sketch", "create_point"),
        _tool("line", "Line", "sketch", "create_line"),
        _tool("surface", "Surface", "sketch", "create_surface"),
        _tool("wall", "Wall", "structure", "assign_semantics"),
        _tool("plate", "Plate", "structure", "assign_semantics"),
        _tool("beam", "Beam", "structure", "create_line"),
        _tool("anchor", "Anchor", "structure", "create_line"),
        _tool("pile", "Pile", "structure", "create_line"),
        _tool("interface", "Interface", "structure", "assign_semantics"),
    )
    mesh_tools = (
        _tool("select", "Select", "selection", "select"),
        _tool("generate_tet4", "Generate Tet4", "generate", "mesh_edit", "gmsh_occ_fragment_tet4_from_stl"),
        _tool("generate_hex8", "Generate Hex8", "generate", "mesh_edit", "structured_hex8_box"),
        _tool("check_quality", "Check Quality", "quality", "mesh_edit"),
        _tool("show_bad_cells", "Show Bad Cells", "quality", "mesh_edit"),
        _tool("local_remesh", "Local Remesh", "quality", "mesh_edit"),
        _tool("boundary_faces", "Boundary Faces", "inspect", "mesh_edit"),
        _tool("physical_groups", "Physical Groups", "inspect", "mesh_edit"),
    )
    staging_tools = (
        _tool("select", "Select", "selection", "select"),
        _tool("add_stage", "Add Stage", "stage", "stage_edit"),
        _tool("clone_stage", "Clone Stage", "stage", "stage_edit"),
        _tool("activate_region", "Activate Region", "activation", "stage_edit"),
        _tool("deactivate_region", "Deactivate Region", "activation", "stage_edit"),
        _tool("boundary_condition", "Boundary Condition", "loads", "stage_edit"),
        _tool("surface_load", "Surface Load", "loads", "stage_edit"),
        _tool("interface_activation", "Interface", "contact", "stage_edit"),
        _tool("validate_stage", "Validate Stage", "check", "stage_edit"),
    )
    solve_tools = (
        _tool("run_check", "Run Check", "validate", "select"),
        _tool("run_linear", "Run Linear Static", "solve", "select", "solid_linear_static_cpu"),
        _tool("run_staged_mc", "Run Staged MC", "solve", "select", "staged_mohr_coulomb_cpu"),
        _tool("run_contact", "Run Contact", "solve", "select", "contact_interface_cpu"),
        _tool("stop", "Stop", "solve", "select"),
        _tool("open_log", "Open Debug Log", "diagnostics", "select"),
        _tool("runtime_bundle", "Export Runtime Bundle", "export", "select"),
    )
    results_tools = (
        _tool("select", "Select", "selection", "result_probe"),
        _tool("displacement", "Displacement", "field", "result_probe"),
        _tool("stress", "Stress", "field", "result_probe"),
        _tool("strain", "Strain", "field", "result_probe"),
        _tool("plastic", "Plastic Points", "field", "result_probe"),
        _tool("contact_status", "Contact Status", "field", "result_probe"),
        _tool("section_cut", "Section Cut", "inspect", "result_probe"),
        _tool("probe", "Probe", "inspect", "result_probe"),
        _tool("export_vtk", "Export VTK", "export", "select"),
    )
    return (
        WorkbenchPhase(
            key="geology",
            label="地质",
            order=1,
            toolbar=PhaseToolbarSpec("geology", ("selection", "import", "repair", "create", "assign"), geology_tools),
            panels=(_panel("model_tree", "模型树"), _panel("geology_properties", "地质属性", "right")),
            default_tool="select",
            allowed_selection_kinds=("point", "surface", "volume", "boundary_face"),
            commands=(_command("optimize_stl", "Optimize STL", "GeometryKernelActionController", "optimize_complex_stl"),),
        ),
        WorkbenchPhase(
            key="structures",
            label="结构",
            order=2,
            toolbar=PhaseToolbarSpec("structures", ("selection", "sketch", "structure"), structures_tools),
            panels=(_panel("model_tree", "模型树"), _panel("structure_properties", "结构属性", "right")),
            default_tool="select",
            allowed_selection_kinds=("point", "line", "edge", "surface", "volume"),
        ),
        WorkbenchPhase(
            key="mesh",
            label="网格",
            order=3,
            toolbar=PhaseToolbarSpec("mesh", ("selection", "generate", "quality", "inspect"), mesh_tools),
            panels=(_panel("mesh_tree", "网格树"), _panel("mesh_quality", "网格质量", "right")),
            default_tool="select",
            allowed_selection_kinds=("volume", "mesh_cell", "boundary_face", "interface_pair"),
        ),
        WorkbenchPhase(
            key="staging",
            label="阶段配置",
            order=4,
            toolbar=PhaseToolbarSpec("staging", ("selection", "stage", "activation", "loads", "contact", "check"), staging_tools),
            panels=(_panel("stage_timeline", "阶段时间线"), _panel("stage_properties", "阶段属性", "right")),
            default_tool="select",
            allowed_selection_kinds=("volume", "boundary_face", "surface", "interface_pair"),
        ),
        WorkbenchPhase(
            key="solve",
            label="求解",
            order=5,
            toolbar=PhaseToolbarSpec("solve", ("validate", "solve", "diagnostics", "export"), solve_tools),
            panels=(_panel("solver_status", "求解状态"), _panel("solver_settings", "求解设置", "right")),
            default_tool="run_check",
            allowed_selection_kinds=("volume", "boundary_face", "interface_pair"),
        ),
        WorkbenchPhase(
            key="results",
            label="结果查看",
            order=6,
            toolbar=PhaseToolbarSpec("results", ("selection", "field", "inspect", "export"), results_tools),
            panels=(_panel("result_tree", "结果树"), _panel("result_properties", "结果属性", "right")),
            default_tool="select",
            allowed_selection_kinds=("result_node", "result_cell", "mesh_cell", "boundary_face"),
        ),
    )


def build_workbench_phase_state(active_phase: str = "geology", active_tool: str | None = None) -> WorkbenchPhaseState:
    phases = build_workbench_phases()
    keys = {phase.key for phase in phases}
    phase_key: WorkbenchPhaseKey = active_phase if active_phase in keys else "geology"  # type: ignore[assignment]
    phase = next(item for item in phases if item.key == phase_key)
    return WorkbenchPhaseState(
        active_phase=phase_key,
        phases=phases,
        active_tool=active_tool or phase.default_tool,
        selection_filter=phase.allowed_selection_kinds,
        metadata={"contract": "workbench_phase_state_v1", "phase_count": len(phases)},
    )


def phase_workbench_ui_state(active_phase: str = "geology", active_tool: str | None = None) -> dict[str, object]:
    """Return a GUI-oriented six-phase state for shell windows.

    This is the P0 contract used by Qt/PyVista shells: one phase tab strip, one
    contextual ribbon, phase-specific panels, and the viewport runtime tool that
    should be activated for the selected ribbon item.
    """

    state = build_workbench_phase_state(active_phase, active_tool)
    active_phase_spec = state.active_phase_spec()
    selected_tool = None
    for tool in active_phase_spec.toolbar.tools:
        if tool.key == state.active_tool:
            selected_tool = tool
            break
    if selected_tool is None:
        selected_tool = next(iter(active_phase_spec.toolbar.tools), None)
    runtime_tool = "select" if selected_tool is None else str(dict(selected_tool.metadata).get("runtime_tool") or "select")
    return {
        "contract": "phase_workbench_ui_state_v1",
        "active_phase": state.active_phase,
        "active_phase_label": active_phase_spec.label,
        "active_tool": state.active_tool,
        "runtime_tool": runtime_tool,
        "phase_tabs": [
            {"key": phase.key, "label": phase.label, "order": phase.order, "active": phase.key == state.active_phase}
            for phase in state.phases
        ],
        "toolbar_groups": active_phase_spec.toolbar.tools_by_group(),
        "left_panels": [panel.to_dict() for panel in active_phase_spec.panels if panel.position == "left"],
        "right_panels": [panel.to_dict() for panel in active_phase_spec.panels if panel.position == "right"],
        "selection_filter": list(state.selection_filter),
    }


def phase_toolbar_rows(active_phase: str = "geology") -> list[dict[str, object]]:
    state = build_workbench_phase_state(active_phase)
    toolbar = state.active_phase_spec().toolbar
    return [tool.to_dict() for tool in toolbar.tools]


__all__ = ["build_workbench_phase_state", "build_workbench_phases", "phase_toolbar_rows", "phase_workbench_ui_state"]
