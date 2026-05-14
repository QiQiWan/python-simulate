from __future__ import annotations

"""GUI payload helpers for the 1.4.0 multi-template Beta-2 demo center."""

from pathlib import Path
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.examples.release_1_4_0_workflow import build_release_1_4_0_gui_payload, run_release_1_4_0_template_workflow, run_release_1_4_0_workflow
from geoai_simkit.services.demo_project_runner import build_demo_catalog, load_demo_project, run_demo_complete_calculation
from geoai_simkit.services.demo_templates import build_engineering_template_catalog, get_engineering_template_spec


def build_release_1_4_0_showcase_payload(project: Any | None = None, *, active_demo_id: str = "foundation_pit_3d_beta") -> dict[str, Any]:
    catalog = build_engineering_template_catalog()
    gui_payload = build_release_1_4_0_gui_payload(active_demo_id)
    project_demo = {} if project is None else dict(getattr(project, "metadata", {}).get("release_1_4_0_demo", {}) or {})
    return {
        "contract": "release_1_4_0_showcase_panel_v1",
        "version": __version__,
        "release": "1.4.2a-cad-facade",
        "active_demo_id": active_demo_id,
        "catalog": catalog,
        "demo_center": gui_payload["demo_center"],
        "project_demo": project_demo,
        "actions": ["load_demo_project", "run_complete_calculation", "export_demo_bundle", "run_all_templates"],
        "button_labels": gui_payload["demo_center"]["button_labels"],
        "quality_gate": catalog["quality_gate"],
    }


def create_release_1_4_0_showcase_project(demo_id: str = "foundation_pit_3d_beta") -> Any:
    get_engineering_template_spec(demo_id)
    return load_demo_project(demo_id)


def run_release_1_4_0_showcase(demo_id: str = "foundation_pit_3d_beta", *, output_dir: str | Path | None = None) -> dict[str, Any]:
    return run_demo_complete_calculation(demo_id, output_dir=output_dir).to_dict(include_project=False)


def run_release_1_4_0_all_showcases(*, output_dir: str | Path | None = None) -> dict[str, Any]:
    return run_release_1_4_0_workflow(output_dir=output_dir)


__all__ = [
    "build_release_1_4_0_showcase_payload",
    "create_release_1_4_0_showcase_project",
    "run_release_1_4_0_showcase",
    "run_release_1_4_0_all_showcases",
]
