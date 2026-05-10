from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def main() -> int:
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    initial_blocks = len(system.document.geometry.blocks)

    point_result = system.create_point(1.2, 0.0, -3.4)
    point_id = point_result["affected_entities"][0]
    line_result = system.create_line((0.0, 0.0, 0.0), (4.0, 0.0, -4.0))
    edge_id = line_result["affected_entities"][0]
    surface_result = system.create_surface([(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, -4.0), (0.0, 0.0, -4.0)])
    surface_id = surface_result["affected_entities"][0]
    block_result = system.create_block((-2.0, -1.0, -0.5, 0.5, -2.0, -1.0), role="structure")
    block_id = block_result["affected_entities"][0]

    system.select_entity(point_id, "point")
    move_result = system.move_selected_point(2.0, 0.0, -4.0)
    moved = system.document.geometry.points[point_id].to_tuple() == (2.0, 0.0, -4.0)

    payload = system.to_payload()
    primitive_kinds = {item["kind"] for item in payload["viewport"]["primitives"]}
    object_types = {row["type"] for row in payload["object_tree"]["rows"]}
    checks = {
        "point_created": point_id in system.document.geometry.points,
        "line_created": edge_id in system.document.geometry.edges,
        "surface_created": surface_id in system.document.geometry.surfaces,
        "block_created": block_id in system.document.geometry.blocks and len(system.document.geometry.blocks) == initial_blocks + 1,
        "move_point": bool(moved and move_result and move_result.get("ok")),
        "viewport_primitives": {"point", "edge", "surface", "block"}.issubset(primitive_kinds),
        "object_tree_types": {"point", "edge", "surface", "block"}.issubset(object_types),
        "property_panel_point": system.property_panel()["title"].startswith("Point:"),
        "command_undo_redo": payload["command_stack"]["undo_count"] >= 5,
    }
    report = {
        "ok": all(checks.values()),
        "checks": checks,
        "summary": {
            "points": len(system.document.geometry.points),
            "edges": len(system.document.geometry.edges),
            "surfaces": len(system.document.geometry.surfaces),
            "blocks": len(system.document.geometry.blocks),
            "faces": len(system.document.geometry.faces),
            "selection": system.document.selection.to_dict(),
        },
        "geometry_editor": payload["geometry_editor"],
    }
    out = Path("reports/geometry_editor_smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
