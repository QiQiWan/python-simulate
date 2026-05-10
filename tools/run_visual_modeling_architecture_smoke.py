from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit.examples.visual_modeling_architecture import build_visual_modeling_demo


def main() -> int:
    payload = build_visual_modeling_demo(dimension="3d")
    checks = {
        "viewport_primitives": payload["viewport"]["primitive_count"] > 0,
        "stable_selection": bool(payload.get("selection", {}).get("entity_id")),
        "command_undo_stack": payload["command_stack"]["undo_count"] >= 2,
        "geometry_blocks": payload["document"]["blocks"] > 0,
        "topology_contacts": payload["document"]["contacts"] > 0,
        "mesh_block_tags": "block_id" in payload["document"]["mesh_tags"],
        "stage_activation": payload["activation_result"]["ok"] is True,
        "result_package_present": payload["document"]["stages"] > 0,
    }
    payload["checks"] = checks
    payload["ok"] = all(checks.values())
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "visual_modeling_architecture_smoke.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "checks": checks, "path": str(out_path)}, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
