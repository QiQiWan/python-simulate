from __future__ import annotations

"""1.4.2c native Gmsh/OCC boolean + physical group mesh roundtrip workflow."""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.interactive_geometry_commands import BooleanGeometryCommand
from geoai_simkit.commands.cad_kernel_commands import BuildCadTopologyIndexCommand, ExecuteGmshOccBooleanMeshRoundtripCommand
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.gmsh_occ_boolean_roundtrip import probe_gmsh_occ_boolean_roundtrip
from geoai_simkit.services.release_acceptance_142c import audit_release_1_4_2c


@dataclass(slots=True)
class Release142cArtifacts:
    project_path: str = ""
    capability_path: str = ""
    roundtrip_path: str = ""
    acceptance_path: str = ""
    tutorial_path: str = ""
    manifest_path: str = ""
    mesh_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "capability_path": self.capability_path,
            "roundtrip_path": self.roundtrip_path,
            "acceptance_path": self.acceptance_path,
            "tutorial_path": self.tutorial_path,
            "manifest_path": self.manifest_path,
            "mesh_path": self.mesh_path,
            "metadata": dict(self.metadata),
        }


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _write_tutorial(path: Path, *, native_possible: bool) -> str:
    text = "\n".join([
        "# GeoAI SimKit 1.4.2c Native Gmsh/OCC Boolean + Physical Group Mesh Roundtrip",
        "",
        "This bundle executes deferred boolean CAD features and then performs a Tet4 mesh roundtrip with physical_volume/material_id tags.",
        "Native-certified mode requires an importable `gmsh.model.occ` runtime. If unavailable, the workflow produces a clearly labelled deterministic contract artifact and is not reported as native-certified.",
        "",
        f"Native gmsh/OCC available in this run: `{native_possible}`",
        "",
        "Recommended GUI flow:",
        "1. Start the six-phase workbench.",
        "2. Load the foundation pit template.",
        "3. Record Union/Subtract features on selected volumes.",
        "4. Execute Gmsh/OCC roundtrip.",
        "5. Inspect physical groups and mesh tags before solve.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def run_release_1_4_2c_workflow(
    output_dir: str | Path = "docs/release/release_1_4_2c_native_roundtrip_review_bundle",
    *,
    require_native_certified: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    project = load_demo_project("foundation_pit_3d_beta")
    project.metadata["release"] = __version__
    stack = CommandStack()
    volume_ids = list(project.geometry_model.volumes)[:2]
    if len(volume_ids) < 2:
        raise RuntimeError("1.4.2c workflow requires at least two demo volumes.")
    stack.execute(BuildCadTopologyIndexCommand(), project)
    bool_result = stack.execute(BooleanGeometryCommand(operation="union", target_ids=tuple(volume_ids)), project)
    if not bool_result.ok:
        raise RuntimeError(bool_result.message or "Failed to record boolean feature")
    roundtrip_cmd = ExecuteGmshOccBooleanMeshRoundtripCommand(
        output_dir=str(root),
        stem="release_1_4_2c_gmsh_occ",
        element_size=2.0,
        require_native=require_native_certified,
        allow_contract_fallback=not require_native_certified,
    )
    roundtrip_result = stack.execute(roundtrip_cmd, project)
    if not roundtrip_result.ok:
        raise RuntimeError(roundtrip_result.message or "Gmsh/OCC boolean mesh roundtrip failed")
    capability = probe_gmsh_occ_boolean_roundtrip().to_dict()
    roundtrip = dict(roundtrip_result.metadata or {})
    acceptance = audit_release_1_4_2c(project, require_native_certified=require_native_certified)
    artifacts = Release142cArtifacts(
        project_path=str(project.save_json(root / "release_1_4_2c_project.geoproject.json")),
        capability_path=_write_json(root / "release_1_4_2c_capability.json", capability),
        roundtrip_path=_write_json(root / "release_1_4_2c_roundtrip.json", roundtrip),
        acceptance_path=_write_json(root / "release_1_4_2c_acceptance.json", acceptance.to_dict()),
        tutorial_path=_write_tutorial(root / "release_1_4_2c_tutorial.md", native_possible=bool(capability.get("native_roundtrip_possible"))),
        manifest_path=str(roundtrip.get("manifest_path", "")),
        mesh_path=str(roundtrip.get("msh_path", "")),
        metadata={"release": __version__, "boolean_target_ids": volume_ids, "require_native_certified": require_native_certified},
    )
    return {
        "contract": "geoai_simkit_release_1_4_2c_native_roundtrip_workflow_v1",
        "ok": bool(acceptance.accepted),
        "project": project,
        "capability": capability,
        "roundtrip": roundtrip,
        "acceptance": acceptance.to_dict(),
        "artifacts": artifacts.to_dict(),
    }


__all__ = ["Release142cArtifacts", "run_release_1_4_2c_workflow"]
