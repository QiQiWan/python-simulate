from __future__ import annotations

"""1.4.2a CAD Facade geometry integration review workflow."""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.commands.cad_kernel_commands import BuildCadTopologyIndexCommand, ExecuteCadFeaturesCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.interactive_geometry_commands import BooleanGeometryCommand
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.cad_facade_kernel import probe_cad_facade_kernel
from geoai_simkit.services.release_acceptance_142 import audit_release_1_4_2


@dataclass(slots=True)
class Release142Artifacts:
    project_path: str = ""
    capability_path: str = ""
    topology_path: str = ""
    feature_execution_path: str = ""
    acceptance_path: str = ""
    tutorial_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "capability_path": self.capability_path,
            "topology_path": self.topology_path,
            "feature_execution_path": self.feature_execution_path,
            "acceptance_path": self.acceptance_path,
            "tutorial_path": self.tutorial_path,
            "metadata": dict(self.metadata),
        }


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _write_tutorial(path: Path) -> str:
    text = "\n".join([
        "# GeoAI SimKit 1.4.2a CAD Facade Geometry Kernel Integration",
        "",
        "This review bundle demonstrates the 1.4.2a CAD facade bridge.",
        "It records CAD/OCC capability, builds persistent topology names for solids/faces/edges/vertices,",
        "executes deferred boolean features through a clearly labelled CAD facade. Native-like gmsh/OCC may be used when available, but fallback/native state is always explicit and 1.4.2a does not claim certified BRep output.",
        "",
        "Recommended GUI flow:",
        "1. Start the six-phase workbench.",
        "2. Load `foundation_pit_3d_beta`.",
        "3. Select two volume primitives.",
        "4. Click `Union` or `Subtract` to record a boolean feature.",
        "5. Click `执行 CAD Facade` to execute the feature and refresh the 3D viewport.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def run_release_1_4_2_workflow(output_dir: str | Path = "docs/release/release_1_4_2a_cad_facade_review_bundle") -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    project = load_demo_project("foundation_pit_3d_beta")
    project.metadata["release"] = __version__
    stack = CommandStack()
    volume_ids = list(project.geometry_model.volumes)[:2]
    if len(volume_ids) < 2:
        raise RuntimeError("The 1.4.2 CAD workflow requires at least two demo volumes.")
    stack.execute(BuildCadTopologyIndexCommand(), project)
    bool_result = stack.execute(BooleanGeometryCommand(operation="union", target_ids=tuple(volume_ids)), project)
    if not bool_result.ok:
        raise RuntimeError(bool_result.message or "Failed to record boolean feature")
    exec_result = stack.execute(ExecuteCadFeaturesCommand(require_native=False, allow_fallback=True), project)
    if not exec_result.ok:
        raise RuntimeError(exec_result.message or "Failed to execute CAD feature")
    acceptance = audit_release_1_4_2(project)
    capability = probe_cad_facade_kernel().to_dict()
    topology = dict(project.geometry_model.metadata.get("cad_occ_topology_index", {}) or {})
    feature_execution = dict(project.geometry_model.metadata.get("last_cad_occ_feature_execution", {}) or {})
    artifacts = Release142Artifacts(
        project_path=str(project.save_json(root / "release_1_4_2a_project.geoproject.json")),
        capability_path=_write_json(root / "release_1_4_2a_cad_facade_capability.json", capability),
        topology_path=_write_json(root / "release_1_4_2a_cad_facade_topology_index.json", topology),
        feature_execution_path=_write_json(root / "release_1_4_2a_cad_facade_feature_execution.json", feature_execution),
        acceptance_path=_write_json(root / "release_1_4_2a_acceptance.json", acceptance.to_dict()),
        tutorial_path=_write_tutorial(root / "release_1_4_2a_tutorial.md"),
        metadata={"release": __version__, "boolean_target_ids": volume_ids},
    )
    return {
        "contract": "geoai_simkit_release_1_4_2a_cad_facade_workflow_v1",
        "ok": bool(acceptance.accepted),
        "project": project,
        "capability": capability,
        "topology": topology,
        "feature_execution": feature_execution,
        "acceptance": acceptance.to_dict(),
        "artifacts": artifacts.to_dict(),
    }


__all__ = ["Release142Artifacts", "run_release_1_4_2_workflow"]
