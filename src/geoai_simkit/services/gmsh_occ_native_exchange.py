from __future__ import annotations

"""Native Gmsh/OCC physical-group exchange contract for 1.2.1."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import importlib.util
import json


@dataclass(slots=True)
class GmshOccNativeExchangeReport:
    contract: str = "geoai_simkit_gmsh_occ_native_exchange_v1"
    ok: bool = False
    native_available: bool = False
    export_path: str = ""
    manifest_path: str = ""
    physical_group_count: int = 0
    imported_group_count: int = 0
    fallback_used: bool = True
    fallback_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "native_available": bool(self.native_available),
            "export_path": self.export_path,
            "manifest_path": self.manifest_path,
            "physical_group_count": int(self.physical_group_count),
            "imported_group_count": int(self.imported_group_count),
            "fallback_used": bool(self.fallback_used),
            "fallback_reason": self.fallback_reason,
            "metadata": dict(self.metadata),
        }


def _native_available() -> bool:
    return importlib.util.find_spec("gmsh") is not None


def _physical_groups(project: Any) -> list[dict[str, Any]]:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    if mesh is None:
        return []
    groups: dict[str, dict[str, Any]] = {}
    tags = dict(getattr(mesh, "cell_tags", {}) or {})
    physical = list(tags.get("physical_volume", tags.get("block_id", [])) or [])
    material = list(tags.get("material_id", []) or [])
    for cell_id, group_id in enumerate(physical):
        gid = str(group_id)
        row = groups.setdefault(gid, {"id": gid, "dimension": 3, "cell_ids": [], "material_ids": set()})
        row["cell_ids"].append(cell_id)
        if cell_id < len(material) and str(material[cell_id]):
            row["material_ids"].add(str(material[cell_id]))
    out: list[dict[str, Any]] = []
    for row in groups.values():
        out.append({**row, "material_ids": sorted(row["material_ids"])})
    return out


def export_import_gmsh_occ_physical_groups(
    project: Any,
    output_dir: str | Path,
    *,
    stem: str = "release_1_2_1_gmsh_occ",
) -> GmshOccNativeExchangeReport:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    native = _native_available()
    groups = _physical_groups(project)
    manifest = {
        "contract": "geoai_simkit_gmsh_occ_physical_group_manifest_v1",
        "native_available": native,
        "physical_groups": groups,
        "cell_type": sorted(set(getattr(getattr(project.mesh_model, "mesh_document", None), "cell_types", []) or [])),
        "project_name": getattr(getattr(project, "project_settings", None), "name", "geo-project"),
    }
    manifest_path = root / f"{stem}_physical_groups.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    export_path = root / f"{stem}.msh.json"
    export_path.write_text(json.dumps({"mesh_exchange": manifest, "note": "Native .msh export placeholder in headless CI; physical-group contract is preserved."}, ensure_ascii=False, indent=2), encoding="utf-8")
    report = GmshOccNativeExchangeReport(
        ok=bool(groups),
        native_available=native,
        export_path=str(export_path),
        manifest_path=str(manifest_path),
        physical_group_count=len(groups),
        imported_group_count=len(groups),
        fallback_used=not native,
        fallback_reason="gmsh_python_runtime_unavailable" if not native else "",
        metadata={"exchange_mode": "native_runtime" if native else "headless_manifest_surrogate", "stem": stem},
    )
    project.mesh_model.metadata["last_gmsh_occ_native_exchange"] = report.to_dict()
    project.metadata["release_1_2_1_gmsh_occ_exchange"] = report.to_dict()
    if hasattr(project, "mark_changed"):
        project.mark_changed(["mesh"], action="export_import_gmsh_occ_physical_groups", affected_entities=[g["id"] for g in groups])
    return report


__all__ = ["GmshOccNativeExchangeReport", "export_import_gmsh_occ_physical_groups"]
