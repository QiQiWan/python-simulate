from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.app.geoproject_source import geoproject_summary
from geoai_simkit.app.panels import (
    build_material_editor,
    build_object_tree,
    build_property_payload,
    build_solver_compiler,
    build_stage_editor,
    build_stage_timeline,
    object_tree_to_rows,
)
from geoai_simkit.document.selection import SelectionRef


def main() -> int:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d", "depth": 9.0}, name="geoproject-gui-smoke")
    project.populate_default_framework_content()
    project.compile_phase_models()

    first_volume = next(iter(project.geometry_model.volumes))
    first_phase = project.phase_manager.initial_phase.id
    first_material = next(iter(project.material_library.soil_materials))

    object_tree = build_object_tree(project)
    rows = object_tree_to_rows(object_tree)
    volume_property = build_property_payload(project, SelectionRef(entity_id=first_volume, entity_type="volume", source="geoproject"))
    phase_property = build_property_payload(project, SelectionRef(entity_id=first_phase, entity_type="phase", source="geoproject"))
    material_property = build_property_payload(project, SelectionRef(entity_id=first_material, entity_type="material", source="geoproject", metadata={"category": "soil"}))
    timeline = build_stage_timeline(project)
    stage_editor = build_stage_editor(project)
    material_editor = build_material_editor(project)
    solver_compiler = build_solver_compiler(project, compile_now=True)
    validation = project.validate_framework()

    report = {
        "accepted": bool(validation["ok"]),
        "summary": geoproject_summary(project),
        "object_tree_rows": len(rows),
        "property_titles": [volume_property["title"], phase_property["title"], material_property["title"]],
        "timeline_count": timeline["count"],
        "stage_editor_phases": len(stage_editor["phases"]),
        "material_editor_categories": len(material_editor["categories"]),
        "material_assignment_count": len(material_editor["assignments"]),
        "compiled_phase_models": len(solver_compiler["compiled_phase_models"]),
        "compile_ready": solver_compiler["compile_readiness"],
        "validation": validation,
    }
    out_dir = Path(__file__).resolve().parents[1] / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "geoproject_gui_datasource_smoke.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    preview = Path(__file__).resolve().parents[1] / "exports" / "geoproject_gui_datasource_preview.geojson"
    project.save_json(preview)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["accepted"] and report["compiled_phase_models"] == timeline["count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
