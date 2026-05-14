from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.native_brep_serialization import probe_native_brep_capability
from geoai_simkit.services.step_ifc_shape_import import (
    probe_step_ifc_import_capability,
    import_step_ifc_solid_topology,
    validate_step_ifc_shape_bindings,
)
from geoai_simkit.services.topology_material_phase_binding import (
    bind_topology_material_phase,
    validate_topology_material_phase_bindings,
)
from geoai_simkit.services.release_acceptance_144 import audit_release_1_4_4


@dataclass(slots=True)
class Release144Artifacts:
    project_path: str = ""
    native_brep_capability_path: str = ""
    step_ifc_capability_path: str = ""
    import_path: str = ""
    binding_path: str = ""
    validation_path: str = ""
    acceptance_path: str = ""
    tutorial_path: str = ""
    source_path: str = ""
    reference_dir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self):
        return {
            "project_path": self.project_path,
            "native_brep_capability_path": self.native_brep_capability_path,
            "step_ifc_capability_path": self.step_ifc_capability_path,
            "import_path": self.import_path,
            "binding_path": self.binding_path,
            "validation_path": self.validation_path,
            "acceptance_path": self.acceptance_path,
            "tutorial_path": self.tutorial_path,
            "source_path": self.source_path,
            "reference_dir": self.reference_dir,
            "metadata": dict(self.metadata),
        }


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _write_sample_step(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "solids": [
            {"id": "step_demo_wall", "name": "STEP Demo Retaining Wall", "bounds": [-8.0, -7.2, -5.0, 5.0, -8.0, 0.0], "role": "imported_wall", "material_id": "concrete"},
            {"id": "step_demo_slab", "name": "STEP Demo Base Slab", "bounds": [-8.0, 8.0, -5.0, 5.0, -8.4, -8.0], "role": "imported_slab", "material_id": "concrete"},
        ]
    }
    text = "ISO-10303-21;\nHEADER;FILE_DESCRIPTION(('GeoAI SimKit 1.4.4 sample'),'2;1');ENDSEC;\nDATA;\n#1=CARTESIAN_POINT('',(-8.0,-5.0,-8.4));\n#2=CARTESIAN_POINT('',(8.0,5.0,0.0));\n/* GEOAI_SIMKIT_SOLIDS: " + json.dumps(payload) + " */\nENDSEC;\nEND-ISO-10303-21;\n"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _write_tutorial(path: Path, *, accepted: bool, native: bool) -> str:
    text = "\n".join([
        "# GeoAI SimKit 1.4.4 Topology Material/Phase Binding",
        "",
        f"Accepted: `{accepted}`",
        f"Native BRep certified in this run: `{native}`",
        "",
        "This release adds native BRep serialization capability probing, STEP/IFC imported shape binding, and face/edge/solid-level material and phase bindings after import or boolean history.",
        "",
        "Acceptance has two levels:",
        "- `accepted_1_4_4_topology_binding`: serialized topology binding is complete; native BRep may be false.",
        "- `accepted_1_4_4_native_brep_topology_binding`: at least one imported shape is native BRep-certified.",
        "",
        "Recommended flow:",
        "1. Import STEP/IFC solids.",
        "2. Inspect CadShapeStore shape references and native BRep certification state.",
        "3. Run face/edge/material/phase binding.",
        "4. Continue to Gmsh/OCC physical-group mesh roundtrip and solve.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def run_release_1_4_4_workflow(
    output_dir: str | Path = "docs/release/release_1_4_4_topology_binding_review_bundle",
    *,
    source_path: str | Path | None = None,
    require_native_brep: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    project = load_demo_project("foundation_pit_3d_beta")
    project.metadata["release"] = __version__
    src = Path(source_path) if source_path is not None else root / "sample_step_import_1_4_4.step"
    if source_path is None:
        _write_sample_step(src)
    native_cap = probe_native_brep_capability().to_dict()
    step_cap = probe_step_ifc_import_capability().to_dict()
    import_report = import_step_ifc_solid_topology(project, src, output_dir=root, attach=True, require_native=require_native_brep, export_references=True)
    if not import_report.ok:
        raise RuntimeError("STEP/IFC import failed: " + str(import_report.to_dict()))
    binding_report = bind_topology_material_phase(project)
    validation = {
        "step_ifc": validate_step_ifc_shape_bindings(project),
        "topology_material_phase": validate_topology_material_phase_bindings(project),
    }
    acceptance = audit_release_1_4_4(project, require_native_brep=require_native_brep)
    artifacts = Release144Artifacts(
        project_path=str(project.save_json(root / "release_1_4_4_project.geoproject.json")),
        native_brep_capability_path=_write_json(root / "release_1_4_4_native_brep_capability.json", native_cap),
        step_ifc_capability_path=_write_json(root / "release_1_4_4_step_ifc_capability.json", step_cap),
        import_path=_write_json(root / "release_1_4_4_step_ifc_import.json", import_report.to_dict()),
        binding_path=_write_json(root / "release_1_4_4_topology_material_phase_binding.json", binding_report.to_dict()),
        validation_path=_write_json(root / "release_1_4_4_validation.json", validation),
        acceptance_path=_write_json(root / "release_1_4_4_acceptance.json", acceptance.to_dict()),
        tutorial_path=_write_tutorial(root / "release_1_4_4_tutorial.md", accepted=acceptance.accepted, native=acceptance.native_brep_certified),
        source_path=str(src),
        reference_dir=import_report.reference_dir,
        metadata={"release": __version__, "require_native_brep": bool(require_native_brep)},
    )
    return {
        "contract": "geoai_simkit_release_1_4_4_topology_binding_workflow_v1",
        "ok": bool(acceptance.accepted),
        "project": project,
        "native_brep_capability": native_cap,
        "step_ifc_capability": step_cap,
        "import_report": import_report.to_dict(),
        "binding_report": binding_report.to_dict(),
        "validation": validation,
        "acceptance": acceptance.to_dict(),
        "artifacts": artifacts.to_dict(),
    }


__all__ = ["run_release_1_4_4_workflow", "Release144Artifacts"]
