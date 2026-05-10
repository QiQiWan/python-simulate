
import json
from pathlib import Path

from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def main() -> int:
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    first_block = next(iter(system.document.geometry.blocks))
    first_stage = system.document.stages.order[min(1, len(system.document.stages.order) - 1)]
    system.select_entity(first_block, "block")
    system.assign_material(first_block, "smoke_material")
    system.set_selected_block_activation(first_stage, False)
    system.generate_mesh()
    system.run_results()
    undo_result = system.undo()
    redo_result = system.redo()
    payload = system.to_payload()
    checks = {
        "contract": payload.get("contract") == "integrated_visual_modeling_system_v1",
        "object_tree": len(payload.get("object_tree", {}).get("rows", [])) > 10,
        "property_panel": bool(payload.get("property_panel", {}).get("sections")),
        "stage_timeline": payload.get("stage_timeline", {}).get("count", 0) >= 2,
        "viewport_blocks": len(payload.get("viewport", {}).get("primitives", [])) == len(system.document.geometry.blocks),
        "selection": payload.get("selection", {}).get("active") is not None,
        "command_undo_redo": undo_result.get("ok") and redo_result.get("ok"),
        "mesh_tags": payload.get("mesh_panel", {}).get("available") and "block_id" in payload.get("mesh_panel", {}).get("cell_tags", []),
        "result_curves": bool(payload.get("result_panel", {}).get("curves", {}).get("max_wall_horizontal_displacement")),
        "validation": isinstance(payload.get("validation"), list),
    }
    out = {"ok": all(checks.values()), "checks": checks, "summary": payload.get("document"), "command_stack": payload.get("command_stack")}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/visual_modeling_system_smoke.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    import os
    code = main()
    os._exit(code)
