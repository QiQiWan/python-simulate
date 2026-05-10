from __future__ import annotations

"""Dependency-light readiness and materialization helpers for interface/contact behavior."""

from typing import Any, Mapping


def materialize_interface_candidates(project: Any, candidates: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None, *, material_id: str = "default_coulomb_interface") -> dict[str, Any]:
    """Create StructuralInterfaceRecord rows from mesh interface candidates.

    The helper is intentionally conservative: it only records contact/interface
    pairs and a Coulomb material assignment.  The runtime solver still controls
    how those interfaces are assembled and updated.
    """

    if project is None:
        return {"ok": False, "created": 0, "issues": [{"code": "project.missing"}]}
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    if candidates is None and mesh is not None:
        candidates = list((getattr(mesh, "face_tags", {}) or {}).get("interface_candidates", []) or [])
    rows = [dict(row) for row in list(candidates or [])]
    if not rows:
        return {"ok": True, "created": 0, "interface_ids": [], "issues": []}
    try:
        from geoai_simkit.geoproject.document import MaterialRecord, StructuralInterfaceRecord
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "created": 0, "issues": [{"code": "import.failed", "message": str(exc)}]}
    library = getattr(project, "material_library", None)
    if library is not None and material_id not in getattr(library, "interface_materials", {}):
        library.interface_materials[material_id] = MaterialRecord(
            id=material_id,
            name="Default Coulomb interface",
            model_type="coulomb_interface",
            parameters={"kn": 5.0e8, "ks": 1.0e8, "friction_deg": 25.0, "cohesion": 0.0, "tensile_cutoff": 0.0},
            metadata={"source": "interface_candidate_materializer", "engineering_level": "penalty_coulomb"},
        )
    structure_model = getattr(project, "structure_model", None)
    created: list[str] = []
    if structure_model is None:
        return {"ok": False, "created": 0, "issues": [{"code": "structure_model.missing"}]}
    for row in rows:
        master = str(row.get("master_ref") or row.get("region_a") or "")
        slave = str(row.get("slave_ref") or row.get("region_b") or "")
        if not master or not slave or master == slave:
            continue
        iid = f"interface_{master}_{slave}".replace(" ", "_")
        if iid in structure_model.structural_interfaces:
            continue
        structure_model.structural_interfaces[iid] = StructuralInterfaceRecord(
            id=iid,
            name=f"Interface {master} / {slave}",
            master_ref=master,
            slave_ref=slave,
            material_id=material_id,
            contact_mode="frictional_coulomb_penalty",
            metadata={"source": "multi_stl_interface_candidate", **row},
        )
        created.append(iid)
    if created and hasattr(project, "refresh_phase_snapshot"):
        project.refresh_phase_snapshot(getattr(getattr(project, "phase_manager", None), "initial_phase", object()).id)
    return {"ok": True, "created": len(created), "interface_ids": created, "issues": []}


def validate_interface_contact_readiness(project: Any) -> dict[str, Any]:
    """Return a structured contact/interface readiness report."""

    issues: list[dict[str, Any]] = []
    structure_model = getattr(project, "structure_model", None)
    library = getattr(project, "material_library", None)
    interfaces = dict(getattr(structure_model, "structural_interfaces", {}) or {}) if structure_model is not None else {}
    materials = dict(getattr(library, "interface_materials", {}) or {}) if library is not None else {}
    for iid, row in interfaces.items():
        material_id = str(getattr(row, "material_id", "") or "")
        if not material_id:
            issues.append({"severity": "error", "code": "interface.material_missing", "interface_id": str(iid), "message": "Interface has no material_id."})
            continue
        if material_id not in materials:
            issues.append({"severity": "error", "code": "interface.material_undefined", "interface_id": str(iid), "material_id": material_id, "message": "Interface material is not defined in MaterialLibrary.InterfaceMaterials."})
            continue
        params = dict(getattr(materials[material_id], "parameters", {}) or {})
        if float(params.get("kn", 0.0) or 0.0) <= 0.0 or float(params.get("ks", 0.0) or 0.0) <= 0.0:
            issues.append({"severity": "error", "code": "interface.stiffness_invalid", "interface_id": str(iid), "material_id": material_id, "message": "Interface kn/ks must be positive."})
    return {
        "ready": not any(row.get("severity") == "error" for row in issues),
        "interface_count": len(interfaces),
        "interface_material_count": len(materials),
        "issues": issues,
        "engineering_level": "penalty_coulomb_interface_v1",
    }


__all__ = ["materialize_interface_candidates", "validate_interface_contact_readiness"]
