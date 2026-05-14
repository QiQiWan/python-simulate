from __future__ import annotations

"""One-click demo catalog and runner for the phase workbench."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.services.demo_templates import build_engineering_template_catalog, get_engineering_template_spec


@dataclass(slots=True)
class DemoProjectSpec:
    demo_id: str
    label: str
    release: str
    description: str
    phases: list[str] = field(default_factory=list)
    one_click_load: bool = True
    complete_calculation: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "demo_id": self.demo_id,
            "label": self.label,
            "release": self.release,
            "description": self.description,
            "phases": list(self.phases),
            "one_click_load": bool(self.one_click_load),
            "complete_calculation": bool(self.complete_calculation),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class DemoRunResult:
    contract: str = "geoai_simkit_demo_run_result_v1"
    ok: bool = False
    demo_id: str = "foundation_pit_3d_beta"
    project: Any | None = None
    workflow: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self, *, include_project: bool = False) -> dict[str, Any]:
        payload = {
            "contract": self.contract,
            "ok": bool(self.ok),
            "demo_id": self.demo_id,
            "workflow": {k: v for k, v in self.workflow.items() if k != "project"},
            "artifacts": dict(self.artifacts),
            "message": self.message,
        }
        if include_project:
            payload["project"] = self.project
        return payload


def build_demo_catalog() -> dict[str, Any]:
    """Return the 1.4.0 multi-template catalog while preserving the old contract."""

    catalog = build_engineering_template_catalog()
    return {
        "contract": "geoai_simkit_demo_catalog_v1",
        "release": "1.4.2a-cad-facade",
        "default_demo_id": catalog["default_demo_id"],
        "template_count": catalog["template_count"],
        "demos": catalog["templates"],
        "templates": catalog["templates"],
        "actions": catalog["actions"],
        "quality_gate": catalog["quality_gate"],
    }


def load_demo_project(demo_id: str = "foundation_pit_3d_beta") -> Any:
    get_engineering_template_spec(demo_id)
    from geoai_simkit.examples.release_1_4_0_workflow import build_release_1_4_0_project

    project, _ = build_release_1_4_0_project(demo_id)
    project.metadata["loaded_from_demo_center"] = True
    return project


def run_demo_complete_calculation(demo_id: str = "foundation_pit_3d_beta", *, output_dir: str | Path | None = None) -> DemoRunResult:
    get_engineering_template_spec(demo_id)
    from geoai_simkit.examples.release_1_4_0_workflow import run_release_1_4_0_template_workflow

    workflow = run_release_1_4_0_template_workflow(demo_id, output_dir=output_dir)
    artifacts = dict(workflow.get("artifacts", {}) or {})
    return DemoRunResult(
        ok=bool(workflow.get("ok", False)),
        demo_id=demo_id,
        project=workflow.get("project"),
        workflow=workflow,
        artifacts=artifacts,
        message="Complete calculation workflow finished." if workflow.get("ok", False) else "Complete calculation workflow was blocked.",
    )


def run_all_demo_calculations(*, output_dir: str | Path | None = None) -> dict[str, Any]:
    from geoai_simkit.examples.release_1_4_0_workflow import run_release_1_4_0_workflow

    return run_release_1_4_0_workflow(output_dir=output_dir)


__all__ = [
    "DemoProjectSpec",
    "DemoRunResult",
    "build_demo_catalog",
    "load_demo_project",
    "run_demo_complete_calculation",
    "run_all_demo_calculations",
]
