from __future__ import annotations

"""IFC product representation expansion for swept solids, CSG and BRep forms."""

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from typing import Any

IFC_REPRESENTATION_EXPANSION_CONTRACT = "geoai_simkit_ifc_representation_expansion_v1"

_REP_TYPES = [
    "IfcExtrudedAreaSolid", "IfcRevolvedAreaSolid", "IfcSweptDiskSolid", "IfcFixedReferenceSweptAreaSolid",
    "IfcBooleanResult", "IfcCsgSolid", "IfcFacetedBrep", "IfcAdvancedBrep", "IfcShellBasedSurfaceModel",
    "IfcFaceBasedSurfaceModel", "IfcMappedItem", "IfcTriangulatedFaceSet", "IfcPolygonalFaceSet",
]

@dataclass(slots=True)
class IfcRepresentationExpansionReport:
    contract: str = IFC_REPRESENTATION_EXPANSION_CONTRACT
    ok: bool = False
    status: str = "not_run"
    source_path: str = ""
    product_count: int = 0
    representation_item_count: int = 0
    exact_product_identity: bool = False
    exact_solid_body_extraction: bool = False
    native_brep_certified: bool = False
    product_records: list[dict[str, Any]] = field(default_factory=list)
    representation_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"contract":self.contract,"ok":bool(self.ok),"status":self.status,"source_path":self.source_path,"product_count":self.product_count,"representation_item_count":self.representation_item_count,"exact_product_identity":bool(self.exact_product_identity),"exact_solid_body_extraction":bool(self.exact_solid_body_extraction),"native_brep_certified":bool(self.native_brep_certified),"product_records":list(self.product_records),"representation_counts":dict(self.representation_counts),"warnings":list(self.warnings),"metadata":dict(self.metadata)}


def _expand_with_ifcopenshell(path: Path) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    warnings: list[str] = []
    try:  # pragma: no cover - host dependent
        import ifcopenshell  # type: ignore
        model = ifcopenshell.open(str(path))
    except Exception as exc:
        return [], {}, [f"IfcOpenShell unavailable or failed to open IFC: {type(exc).__name__}: {exc}"]
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    products = []
    for typ in ("IfcBuildingElement", "IfcElement", "IfcProduct"):
        try:
            products.extend(list(model.by_type(typ)))
        except Exception:
            pass
    seen: set[str] = set()
    for product in products:
        gid = str(getattr(product, "GlobalId", "") or product.id())
        if gid in seen:
            continue
        seen.add(gid)
        rep_items: list[dict[str, Any]] = []
        try:
            reps = list(getattr(getattr(product, "Representation", None), "Representations", []) or [])
            for rep in reps:
                ctx = str(getattr(rep, "RepresentationIdentifier", "") or "")
                rtype = str(getattr(rep, "RepresentationType", "") or "")
                for item in list(getattr(rep, "Items", []) or []):
                    item_type = str(item.is_a()) if hasattr(item, "is_a") else type(item).__name__
                    counts[item_type] = counts.get(item_type, 0) + 1
                    rep_items.append({"context": ctx, "representation_type": rtype, "item_type": item_type, "item_id": int(item.id()) if hasattr(item, "id") else None})
        except Exception as exc:
            warnings.append(f"Failed to expand representations for {gid}: {type(exc).__name__}: {exc}")
        records.append({
            "global_id": gid,
            "name": str(getattr(product, "Name", "") or gid),
            "ifc_type": str(product.is_a()) if hasattr(product, "is_a") else type(product).__name__,
            "representation_items": rep_items,
            "has_swept_solid": any(x.get("item_type") in {"IfcExtrudedAreaSolid", "IfcRevolvedAreaSolid", "IfcSweptDiskSolid", "IfcFixedReferenceSweptAreaSolid"} for x in rep_items),
            "has_csg": any(x.get("item_type") in {"IfcBooleanResult", "IfcCsgSolid"} for x in rep_items),
            "has_brep": any(x.get("item_type") in {"IfcFacetedBrep", "IfcAdvancedBrep"} for x in rep_items),
        })
    return records, counts, warnings


def _expand_by_text(path: Path) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    counts: dict[str, int] = {}
    for typ in _REP_TYPES:
        counts[typ] = len(re.findall(r"\b" + re.escape(typ).upper() + r"\b", text.upper()))
    product_ids = re.findall(r"=\s*(IFC\w+)\s*\(", text.upper())[:50]
    records = [{"global_id":"text_scan_product_001","name":path.stem,"ifc_type":"text_scan","representation_items":[{"item_type":k,"count":v} for k,v in counts.items() if v],"has_swept_solid":any(counts.get(k,0) for k in ("IfcExtrudedAreaSolid","IfcRevolvedAreaSolid","IfcSweptDiskSolid")),"has_csg":any(counts.get(k,0) for k in ("IfcBooleanResult","IfcCsgSolid")),"has_brep":any(counts.get(k,0) for k in ("IfcFacetedBrep","IfcAdvancedBrep")),"scanned_entity_types":product_ids[:12]}] if text else []
    return records, counts, ["IfcOpenShell not used; representation expansion is based on text scan."]


def expand_ifc_product_representations(source_path: str | Path, *, write_json: str | Path | None = None) -> IfcRepresentationExpansionReport:
    path = Path(source_path)
    if not path.exists():
        return IfcRepresentationExpansionReport(ok=False, status="source_not_found", source_path=str(path), warnings=[f"Source file not found: {path}"])
    records, counts, warnings = _expand_with_ifcopenshell(path)
    exact_identity = bool(records and not any("IfcOpenShell unavailable" in w for w in warnings))
    if not records:
        records, counts, tw = _expand_by_text(path)
        warnings.extend(tw)
    item_count = sum(int(v) for v in counts.values())
    exact_solid = bool(exact_identity and item_count > 0)
    report = IfcRepresentationExpansionReport(ok=bool(records), status="expanded" if records else "no_products", source_path=str(path), product_count=len(records), representation_item_count=item_count, exact_product_identity=exact_identity, exact_solid_body_extraction=exact_solid, native_brep_certified=False, product_records=records, representation_counts=counts, warnings=warnings, metadata={"representation_types": _REP_TYPES})
    if write_json:
        p=Path(write_json); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report

__all__ = ["IfcRepresentationExpansionReport", "expand_ifc_product_representations"]
