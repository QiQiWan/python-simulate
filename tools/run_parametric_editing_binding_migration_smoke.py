from __future__ import annotations

import json
from pathlib import Path

from tools._no_install_bootstrap import bootstrap


def main() -> int:
    bootstrap()
    from geoai_simkit.app.visual_modeling_system import VisualModelingSystem

    system = VisualModelingSystem.create_default({"dimension": "3d"})
    layer_result = system.split_soil_layer_at(-6.0)
    excavation_result = system.split_excavation_polygon(
        [(-2.0, 0.0, -2.0), (2.0, 0.0, -2.0), (2.0, 0.0, -5.0), (-2.0, 0.0, -5.0)]
    )
    payload = system.to_payload()
    checks = {
        "layer_split": bool(layer_result.get("ok", True)),
        "excavation_split": bool(excavation_result.get("ok", True)),
        "parametric_panel": payload.get("operation_pages", {}).get("modeling", {}).get("parametric_editing") is not None,
        "feature_count": len(payload.get("operation_pages", {}).get("modeling", {}).get("parametric_editing", {}).get("features", [])) >= 1,
    }
    report = {"ok": all(checks.values()), "checks": checks}
    out = Path("reports") / "parametric_editing_binding_migration_smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
