from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.commands.cad_kernel_commands import ExecuteGmshOccBooleanMeshRoundtripCommand, BuildCadShapeStoreCommand, BindTopologyMaterialPhaseCommand, AssignTopologyMaterialPhaseCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.interactive_geometry_commands import BooleanGeometryCommand
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.native_runtime_verification import verify_native_desktop_runtime
from geoai_simkit.services.native_brep_serialization import probe_native_brep_capability
from geoai_simkit.services.step_ifc_shape_import import import_step_ifc_solid_topology, probe_step_ifc_import_capability, validate_step_ifc_shape_bindings
from geoai_simkit.services.ifc_representation_expansion import expand_ifc_product_representations
from geoai_simkit.services.boolean_topology_lineage import build_boolean_topology_lineage, validate_boolean_topology_lineage
from geoai_simkit.services.topology_material_phase_binding import validate_topology_material_phase_bindings
from geoai_simkit.services.release_acceptance_145 import audit_release_1_4_5

@dataclass(slots=True)
class Release145Artifacts:
    project_path: str = ""
    runtime_verification_path: str = ""
    native_brep_capability_path: str = ""
    step_ifc_capability_path: str = ""
    step_import_path: str = ""
    ifc_source_path: str = ""
    ifc_expansion_path: str = ""
    roundtrip_path: str = ""
    shape_store_path: str = ""
    lineage_path: str = ""
    binding_validation_path: str = ""
    lineage_validation_path: str = ""
    acceptance_path: str = ""
    tutorial_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _write_sample_step(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"solids":[{"id":"curved_step_wall","name":"Curved STEP Wall Reference","bounds":[-8.0,-7.0,-5.0,5.0,-8.0,0.0],"role":"imported_wall","material_id":"concrete","metadata":{"curved_face_hint":True,"surface_types":["plane","cylinder"]}},{"id":"curved_step_cap","name":"Curved STEP Cap Reference","bounds":[-8.0,8.0,-5.0,5.0,-0.3,0.0],"role":"imported_cap","material_id":"concrete"}]}
    text = "ISO-10303-21;\nHEADER;FILE_DESCRIPTION(('GeoAI 1.4.5 curved-face sample'),'2;1');ENDSEC;\nDATA;\n#1=CARTESIAN_POINT('',(-8.0,-5.0,-8.0));\n#2=CARTESIAN_POINT('',(8.0,5.0,0.0));\n#10=CYLINDRICAL_SURFACE('',#9,3.0);\n/* GEOAI_SIMKIT_SOLIDS: " + json.dumps(payload) + " */\nENDSEC;\nEND-ISO-10303-21;\n"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _write_sample_ifc(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = """ISO-10303-21;
HEADER;FILE_DESCRIPTION(('GeoAI 1.4.5 IFC representation sample'),'2;1');ENDSEC;
DATA;
#1=IFCPROJECT('0PROJECT',$,'GeoAI Demo',$,$,$,$,$,$);
#20=IFCCARTESIANPOINT((0.,0.,0.));
#21=IFCDIRECTION((0.,0.,1.));
#22=IFCAXIS2PLACEMENT3D(#20,$,#21);
#30=IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,'pit_profile',$);
#40=IFCEXTRUDEDAREASOLID(#30,#22,#21,8.0);
#50=IFCBOOLEANRESULT(.DIFFERENCE.,#40,#40);
#60=IFCFACETEDBREP($);
#100=IFCWALL('3xYzDemoGuid001',$,'IFC Demo Wall',$,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;
"""
    path.write_text(text, encoding="utf-8")
    return str(path)


def _write_tutorial(path: Path, *, accepted: bool, native: bool) -> str:
    text = "\n".join([
        "# GeoAI SimKit 1.4.5 Native Geometry Certification Workflow",
        "",
        f"Accepted: `{accepted}`",
        f"Native BRep certified in this run: `{native}`",
        "",
        "This workflow verifies desktop native runtime capability, imports STEP/IFC topology references, expands IFC swept/CSG/BRep representations, builds boolean face lineage, and supports face/edge material/phase assignment.",
        "",
        "Native-certified acceptance requires real TopoDS_Shape BRep serialization plus native topology enumeration. In environments without OCP/pythonocc/IfcOpenShell, the workflow remains useful as a contract run and clearly marks native_brep_certified=false.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8"); return str(path)


def run_release_1_4_5_workflow(output_dir: str | Path = "docs/release/release_1_4_5_native_geometry_certification_review_bundle", *, require_native_brep: bool = False) -> dict[str, Any]:
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    project = load_demo_project("foundation_pit_3d_beta")
    project.metadata["release"] = __version__
    runtime = verify_native_desktop_runtime(require_native_brep=False)
    native_cap = probe_native_brep_capability().to_dict()
    step_cap = probe_step_ifc_import_capability().to_dict()

    stack = CommandStack()
    volume_ids = list(project.geometry_model.volumes)[:2]
    if len(volume_ids) >= 2:
        br = stack.execute(BooleanGeometryCommand(operation="union", target_ids=tuple(volume_ids)), project)
        if not br.ok:
            raise RuntimeError(br.message or "Boolean feature recording failed")
        rr = stack.execute(ExecuteGmshOccBooleanMeshRoundtripCommand(output_dir=str(root), stem="release_1_4_5_gmsh_occ", require_native=False), project)
        if not rr.ok:
            raise RuntimeError(rr.message or "Boolean mesh roundtrip failed")
        roundtrip = dict(rr.metadata or {})
    else:
        roundtrip = {"ok": False, "status": "not_enough_volumes"}

    sr = stack.execute(BuildCadShapeStoreCommand(output_dir=str(root), include_roundtrip=True, export_references=True), project)
    if not sr.ok:
        raise RuntimeError(sr.message or "CadShapeStore build failed")

    step_path = root / "sample_curved_step_1_4_5.step"
    ifc_path = root / "sample_ifc_representation_1_4_5.ifc"
    _write_sample_step(step_path); _write_sample_ifc(ifc_path)
    step_import = import_step_ifc_solid_topology(project, step_path, output_dir=root, attach=True, require_native=require_native_brep, export_references=True)
    if not step_import.ok:
        raise RuntimeError("STEP import failed: " + str(step_import.to_dict()))
    ifc_expansion = expand_ifc_product_representations(ifc_path)
    project.metadata["release_1_4_5_ifc_representation_expansion"] = ifc_expansion.to_dict()

    bind_result = stack.execute(BindTopologyMaterialPhaseCommand(), project)
    if not bind_result.ok:
        raise RuntimeError(bind_result.message or "Topology material/phase binding failed")
    # Demonstrate GUI-equivalent face/edge direct assignment on the first available face.
    face_id = next((tid for tid, topo in project.cad_shape_store.topology_records.items() if topo.kind == "face"), "")
    direct_assignment = {}
    if face_id:
        ar = stack.execute(AssignTopologyMaterialPhaseCommand(topology_id=face_id, material_id="concrete", phase_ids=["initial", "support_1"], role="support_contact"), project)
        direct_assignment = dict(ar.metadata or {})
    lineage = build_boolean_topology_lineage(project)
    binding_validation = validate_topology_material_phase_bindings(project)
    lineage_validation = validate_boolean_topology_lineage(project, require_face_lineage=False)
    acceptance = audit_release_1_4_5(project, require_native_brep=require_native_brep, require_lineage=True)
    artifacts = Release145Artifacts(
        project_path=str(project.save_json(root / "release_1_4_5_project.geoproject.json")),
        runtime_verification_path=_write_json(root / "release_1_4_5_native_runtime_verification.json", runtime.to_dict()),
        native_brep_capability_path=_write_json(root / "release_1_4_5_native_brep_capability.json", native_cap),
        step_ifc_capability_path=_write_json(root / "release_1_4_5_step_ifc_capability.json", step_cap),
        step_import_path=_write_json(root / "release_1_4_5_step_import.json", step_import.to_dict()),
        ifc_source_path=str(ifc_path),
        ifc_expansion_path=_write_json(root / "release_1_4_5_ifc_representation_expansion.json", ifc_expansion.to_dict()),
        roundtrip_path=_write_json(root / "release_1_4_5_roundtrip.json", roundtrip),
        shape_store_path=_write_json(root / "release_1_4_5_cad_shape_store.json", project.cad_shape_store.to_dict()),
        lineage_path=_write_json(root / "release_1_4_5_boolean_topology_lineage.json", lineage.to_dict()),
        binding_validation_path=_write_json(root / "release_1_4_5_topology_binding_validation.json", binding_validation),
        lineage_validation_path=_write_json(root / "release_1_4_5_lineage_validation.json", lineage_validation),
        acceptance_path=_write_json(root / "release_1_4_5_acceptance.json", acceptance.to_dict()),
        tutorial_path=_write_tutorial(root / "release_1_4_5_tutorial.md", accepted=acceptance.accepted, native=acceptance.native_brep_certified),
        metadata={"release": __version__, "require_native_brep": bool(require_native_brep), "direct_assignment": direct_assignment},
    )
    return {"contract":"geoai_simkit_release_1_4_5_native_geometry_certification_workflow_v1","ok":bool(acceptance.accepted),"project":project,"runtime_verification":runtime.to_dict(),"native_brep_capability":native_cap,"step_ifc_capability":step_cap,"step_import":step_import.to_dict(),"ifc_representation_expansion":ifc_expansion.to_dict(),"roundtrip":roundtrip,"shape_store_summary":project.cad_shape_store.summary(),"boolean_topology_lineage":lineage.to_dict(),"topology_binding_validation":binding_validation,"lineage_validation":lineage_validation,"acceptance":acceptance.to_dict(),"artifacts":artifacts.to_dict()}

__all__ = ["run_release_1_4_5_workflow", "Release145Artifacts"]
