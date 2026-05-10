from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit.app.geometry_mouse_interaction import GeometryMouseController
from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def main() -> int:
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    controller = GeometryMouseController(system)

    initial_blocks = len(system.document.geometry.blocks)
    initial_contacts = len(system.document.topology.contact_edges())

    controller.set_mode("point")
    controller.click(0.18, -0.12)
    snap = system.locate_with_snap(0.2, 0.0, -0.1)

    controller.set_mode("strut")
    controller.click(-12.0, -2.0)
    support_result = controller.click(12.0, -2.0)

    controller.set_mode("wall")
    controller.click(-16.0, 0.0)
    wall_result = controller.click(-16.0, -16.0)

    controller.set_mode("soil_layer")
    controller.click(-30.0, -6.0)
    layer_result = controller.end_soil_layer_drag(30.0, -6.0)

    controller.set_mode("excavation")
    for x, z in [(-5.0, 0.0), (5.0, 0.0), (5.0, -4.0), (-5.0, -4.0)]:
        controller.click(x, z)
    excavation_result = controller.close_excavation_polygon()

    contact_review = system.rebuild_interface_candidates()
    accepted = system.accept_first_interface_candidate()
    payload = system.to_payload()

    checks = {
        "snap_grid_endpoint_contract": bool(payload.get("snap", {}).get("enabled")) and snap.get("snap_mode") in {"grid", "endpoint", "free"},
        "endpoint_snap_visible": len(payload.get("viewport", {}).get("overlays", [])) > 0,
        "support_creation": len(system.document.supports) >= 2 and support_result.ok and wall_result.ok,
        "soil_layer_split": layer_result.ok and len(system.document.geometry.blocks) > initial_blocks,
        "excavation_polygon_split": excavation_result.ok and any(b.role == "excavation" for b in system.document.geometry.blocks.values()),
        "contact_review_candidates": contact_review.get("summary", {}).get("candidate_count", 0) > 0,
        "interface_acceptance": accepted is not None and len(system.document.interfaces) > 0,
        "viewport_support_primitives": any(p.get("kind") == "support" for p in payload.get("viewport", {}).get("primitives", [])),
        "viewport_contact_primitives": any(p.get("kind") == "contact_pair" for p in payload.get("viewport", {}).get("primitives", [])),
        "operation_page_contract": "interface_review" in payload.get("operation_pages", {}).get("modeling", {}),
    }
    report = {
        "ok": all(checks.values()),
        "checks": checks,
        "summary": {
            "initial_blocks": initial_blocks,
            "final_blocks": len(system.document.geometry.blocks),
            "initial_contacts": initial_contacts,
            "final_contacts": len(system.document.topology.contact_edges()),
            "supports": len(system.document.supports),
            "interfaces": len(system.document.interfaces),
            "overlays": len(payload.get("viewport", {}).get("overlays", [])),
        },
    }
    path = Path("reports/engineering_modeling_tools_smoke.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
