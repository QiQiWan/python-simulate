from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit.app.geometry_mouse_interaction import GeometryMouseController
from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def main() -> int:
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    controller = GeometryMouseController(system)

    initial_points = len(system.document.geometry.points)
    initial_edges = len(system.document.geometry.edges)
    initial_surfaces = len(system.document.geometry.surfaces)
    initial_blocks = len(system.document.geometry.blocks)

    # Click-to-create point.
    controller.set_mode("point")
    point_result = controller.click(1.2, -1.8)
    created_point_ids = [eid for eid in point_result.entity_ids if eid in system.document.geometry.points]
    point_id = created_point_ids[0] if created_point_ids else next(reversed(system.document.geometry.points))

    # Continuous line drawing: first click sets anchor, next two clicks create two connected segments.
    controller.set_mode("line")
    controller.click(0.0, 0.0)
    line_1 = controller.click(4.0, -2.0)
    line_2 = controller.click(8.0, -3.0)
    controller.finish_line()

    # Surface drawing and explicit closure.
    controller.set_mode("surface")
    controller.click(-3.0, -1.0)
    controller.click(-1.0, -1.0)
    controller.click(-1.0, -3.0)
    surface_result = controller.close_surface()

    # Box block by two mouse corners.
    controller.set_mode("block")
    controller.click(10.0, 0.0)
    block_result = controller.click(14.0, -4.0)
    created_block_ids = [eid for eid in block_result.entity_ids if eid in system.document.geometry.blocks]
    block_id = created_block_ids[0] if created_block_ids else next(reversed(system.document.geometry.blocks))

    # Drag the created point to a new location.
    controller.set_mode("move_point")
    controller.start_drag(point_id, "point")
    controller.drag_to(2.0, -2.0)
    controller.end_drag(2.0, -2.0)
    moved_point = system.document.geometry.points[point_id]

    # Select single, multi-select with add, then rubber-band select.
    controller.set_mode("select")
    controller.click(0.0, 0.0, entity_id=point_id, entity_type="point")
    controller.click(0.0, 0.0, entity_id=block_id, entity_type="block", selection_modifier="add")
    multi_count_after_add = len(system.document.selection.items)
    box_result = controller.box_select(-10.0, 1.0, 20.0, -10.0, modifier="replace")

    # Context menu action on selected blocks.
    context_actions = controller.context_actions()
    deactivate_result = controller.invoke_context_action("deactivate_selected", stage_id=system.document.stages.active_stage_id)
    hide_result = controller.invoke_context_action("hide_selected")
    show_result = controller.invoke_context_action("show_selected")

    checks = {
        "point_click_created": len(system.document.geometry.points) > initial_points,
        "continuous_lines_created": len(system.document.geometry.edges) >= initial_edges + 2 and line_1.ok and line_2.ok,
        "surface_closed": len(system.document.geometry.surfaces) > initial_surfaces and surface_result.ok,
        "block_box_created": len(system.document.geometry.blocks) > initial_blocks and block_result.ok,
        "point_dragged": abs(moved_point.x - 2.0) < 1e-9 and abs(moved_point.z + 2.0) < 1e-9,
        "multi_select_add": multi_count_after_add >= 2,
        "box_select": len(box_result.entity_ids) >= 1 and len(system.document.selection.items) >= 1,
        "context_menu_actions": any(row.get("id") == "delete_selected" for row in context_actions),
        "context_activation_action": deactivate_result.ok,
        "context_visibility_actions": hide_result.ok and show_result.ok,
        "viewport_contract": any(p.get("kind") == "point" for p in system.refresh_viewport().get("primitives", [])),
        "selection_contract": system.document.selection.to_dict()["count"] >= 1,
    }

    report = {
        "ok": all(checks.values()),
        "checks": checks,
        "summary": {
            "points": len(system.document.geometry.points),
            "edges": len(system.document.geometry.edges),
            "surfaces": len(system.document.geometry.surfaces),
            "blocks": len(system.document.geometry.blocks),
            "selected": len(system.document.selection.items),
            "mouse_preview": controller.preview_state(),
        },
    }
    out = Path("reports/mouse_geometry_interaction_smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
