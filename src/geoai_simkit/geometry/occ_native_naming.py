from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from geoai_simkit.geometry.persistent_naming import PersistentTopologyNamer


def pythonocc_available() -> bool:
    try:
        import OCC.Core.TNaming  # type: ignore  # noqa: F401
        import OCC.Core.TDF  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


@dataclass(slots=True)
class NativeNamingAudit:
    contract: str = "opencascade_native_persistent_naming_audit_v1"
    native_backend_available: bool = False
    native_tnaming_enabled: bool = False
    fallback_used: bool = True
    entity_count: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "native_backend_available": bool(self.native_backend_available),
            "native_tnaming_enabled": bool(self.native_tnaming_enabled),
            "fallback_used": bool(self.fallback_used),
            "entity_count": int(self.entity_count),
            "notes": list(self.notes),
            "fallback_contract": "feature_semantic_stable_geometry_fingerprint_v4",
            "edit_policy": "edit_source_entity_then_remesh",
        }


class OpenCascadeNativeNamingBridge:
    """Bridge for OpenCascade-native persistent naming.

    The gmsh OCC API does not expose OpenCascade TNaming labels. When pythonocc
    is available, this class prepares per-entity native handles and the data
    shape needed by a future TDF/TNaming document. Without pythonocc, it returns
    an explicit audit and decorates the document with the v4 stable fallback.
    """

    def decorate_document(self, brep_document: dict[str, Any] | None, *, feature_history: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        doc = PersistentTopologyNamer().decorate_document(dict(brep_document or {}))
        available = pythonocc_available()
        rows: list[dict[str, Any]] = []
        for row in list(doc.get("volumes", []) or []) + list(doc.get("surfaces", []) or []):
            item = dict(row)
            native_handle = {
                "source_feature_id": item.get("source_feature_id") or item.get("source_block") or item.get("region_name") or item.get("name") or "",
                "occ_dim": item.get("occ_dim") or (3 if item in list(doc.get("volumes", []) or []) else 2),
                "occ_tag": item.get("occ_tag") or item.get("occ_volume_tag") or item.get("occ_surface_tag"),
                "physical_id": item.get("physical_id") or item.get("gmsh_physical_id"),
                "persistent_id": item.get("persistent_id"),
                "topological_fingerprint": item.get("topological_fingerprint"),
            }
            if available:
                native_handle["tnaming_label_path"] = f"/GeoAISimKit/{native_handle['source_feature_id']}/{native_handle['occ_dim']}/{native_handle['occ_tag']}"
                native_handle["native_status"] = "ready_for_tdf_tnaming_document"
            else:
                native_handle["native_status"] = "pythonocc_unavailable_fingerprint_fallback"
            rows.append(native_handle)
        audit = NativeNamingAudit(
            native_backend_available=available,
            native_tnaming_enabled=available,
            fallback_used=not available,
            entity_count=len(rows),
            notes=[] if available else ["pythonocc-core is not installed; using stable fingerprint transfer instead of TNaming labels."],
        ).to_dict()
        doc["native_persistent_naming"] = {
            "contract": "opencascade_native_persistent_naming_bridge_v1",
            "audit": audit,
            "native_name_rows": rows,
            "feature_history_rows": [dict(r) for r in list(feature_history or []) if isinstance(r, dict)],
        }
        doc["topological_naming"] = "opencascade_tnaming_bridge_with_fingerprint_fallback_v1" if available else doc.get("topological_naming", "")
        return doc


def build_native_naming_audit(brep_document: dict[str, Any] | None) -> dict[str, Any]:
    return OpenCascadeNativeNamingBridge().decorate_document(brep_document).get("native_persistent_naming", {})


__all__ = ["OpenCascadeNativeNamingBridge", "NativeNamingAudit", "build_native_naming_audit", "pythonocc_available"]
