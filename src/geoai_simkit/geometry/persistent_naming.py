from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable


def _round_tuple(values: Iterable[Any], ndigits: int = 6) -> tuple[float, ...]:
    out: list[float] = []
    for value in values:
        try:
            out.append(round(float(value), ndigits))
        except Exception:
            out.append(0.0)
    return tuple(out)


def _stable_hash(payload: dict[str, Any], *, length: int = 12) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def _semantic_role(row: dict[str, Any]) -> str:
    for key in ("semantic_role", "surface_role", "role", "boundary_kind", "label"):
        value = str(row.get(key) or "").strip().lower()
        if value:
            return value.replace(" ", "_")
    return "entity"


def _center(row: dict[str, Any]) -> tuple[float, float, float]:
    values = list(row.get("center") or [])
    if len(values) >= 3:
        return _round_tuple(values[:3], 6)  # type: ignore[return-value]
    bounds = list(row.get("bounds") or row.get("bbox") or [])
    if len(bounds) >= 6:
        return (round((float(bounds[0]) + float(bounds[1])) * 0.5, 6), round((float(bounds[2]) + float(bounds[3])) * 0.5, 6), round((float(bounds[4]) + float(bounds[5])) * 0.5, 6))
    return (0.0, 0.0, 0.0)


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return float(math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b))))


@dataclass(frozen=True, slots=True)
class PersistentTopologyName:
    entity_id: str
    persistent_id: str
    kind: str
    semantic_role: str
    source_feature_id: str = ""
    occ_dim: int | None = None
    occ_tag: int | None = None
    physical_id: int | None = None
    fingerprint: str = ""
    stable_key: str = ""
    version: str = "persistent_topological_name_v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.version,
            "entity_id": self.entity_id,
            "persistent_id": self.persistent_id,
            "kind": self.kind,
            "semantic_role": self.semantic_role,
            "source_feature_id": self.source_feature_id,
            "occ_dim": self.occ_dim,
            "occ_tag": self.occ_tag,
            "physical_id": self.physical_id,
            "fingerprint": self.fingerprint,
            "stable_key": self.stable_key,
        }


class PersistentTopologyNamer:
    """Stable topology naming helper for editable BRep/OCC-derived entities.

    This is not full OpenCascade TNaming, but v4 adds a practical persistent
    naming layer for GUI workflows: semantic source feature, rounded geometry
    fingerprint, stable key, duplicate detection and candidate scoring.
    """

    def _row_kind(self, row: dict[str, Any], fallback: str = "entity") -> str:
        eid = str(row.get("id") or row.get("topology_entity_id") or "")
        if eid.startswith("solid:") or row.get("occ_dim") == 3 or row.get("occ_volume_tag") not in {None, ""}:
            return "solid"
        if eid.startswith(("face:", "face_set:", "protected_surface:")) or row.get("occ_dim") == 2 or row.get("occ_surface_tag") not in {None, ""}:
            return "face"
        if eid.startswith("edge:") or row.get("occ_dim") == 1:
            return "edge"
        if eid.startswith("vertex:") or row.get("occ_dim") == 0:
            return "vertex"
        return fallback

    def fingerprint_entity(self, row: dict[str, Any]) -> str:
        bounds = _round_tuple(row.get("bounds") or row.get("bbox") or ())
        center = _center(row)
        normal = _round_tuple(row.get("normal") or row.get("owner_to_neighbor_normal") or ())
        payload = {
            "kind": self._row_kind(row),
            "role": _semantic_role(row),
            "source": str(row.get("source_block") or row.get("source_feature_id") or row.get("region_name") or row.get("name") or ""),
            "bounds": bounds,
            "center": center,
            "normal": normal,
            "area": round(float(row.get("area", 0.0) or 0.0), 6),
            "volume": round(float(row.get("volume", 0.0) or 0.0), 6),
        }
        return _stable_hash(payload, length=16)

    def stable_key(self, row: dict[str, Any], *, fallback_kind: str = "entity") -> str:
        kind = self._row_kind(row, fallback=fallback_kind)
        source = str(row.get("source_feature_id") or row.get("source_block") or row.get("region_name") or row.get("solid_id") or row.get("name") or "source")
        role = _semantic_role(row)
        normal = _round_tuple(row.get("normal") or row.get("owner_to_neighbor_normal") or (), 3)
        center = _round_tuple(_center(row), 3)
        return f"{kind}|{source}|{role}|c={center}|n={normal}"

    def name_entity(self, row: dict[str, Any], *, fallback_kind: str = "entity") -> dict[str, Any]:
        kind = self._row_kind(row, fallback=fallback_kind)
        semantic = _semantic_role(row)
        source_feature = str(row.get("source_feature_id") or row.get("source_block") or row.get("region_name") or row.get("solid_id") or row.get("name") or "source")
        occ_dim = row.get("occ_dim")
        if occ_dim in {None, ""}:
            occ_dim = 3 if kind == "solid" else (2 if kind == "face" else (1 if kind == "edge" else None))
        occ_tag = row.get("occ_tag") or row.get("occ_volume_tag") or row.get("occ_surface_tag") or row.get("tag")
        physical = row.get("physical_id") or row.get("gmsh_physical_id")
        fp = self.fingerprint_entity(row)
        skey = self.stable_key(row, fallback_kind=kind)
        base = {
            "source_feature_id": source_feature,
            "kind": kind,
            "semantic_role": semantic,
            "stable_key": skey,
            "fingerprint": fp,
        }
        suffix = _stable_hash(base, length=10)
        persistent_id = f"{kind}:{source_feature}:{semantic}:{suffix}".replace(" ", "_")
        entity_id = str(row.get("id") or row.get("topology_entity_id") or persistent_id)
        return PersistentTopologyName(
            entity_id=entity_id,
            persistent_id=persistent_id,
            kind=kind,
            semantic_role=semantic,
            source_feature_id=source_feature,
            occ_dim=None if occ_dim in {None, ""} else int(occ_dim),
            occ_tag=None if occ_tag in {None, ""} else int(occ_tag),
            physical_id=None if physical in {None, ""} else int(physical),
            fingerprint=fp,
            stable_key=skey,
        ).to_dict()

    def decorate_document(self, brep_document: dict[str, Any] | None) -> dict[str, Any]:
        doc = dict(brep_document or {})
        volumes: list[dict[str, Any]] = []
        surfaces: list[dict[str, Any]] = []
        name_rows: list[dict[str, Any]] = []
        persistent_seen: dict[str, int] = {}
        for key, fallback in (("volumes", "solid"), ("surfaces", "face")):
            decorated_rows: list[dict[str, Any]] = []
            for row in list(doc.get(key, []) or []):
                item = dict(row)
                name = self.name_entity(item, fallback_kind=fallback)
                pid = str(name["persistent_id"])
                persistent_seen[pid] = persistent_seen.get(pid, 0) + 1
                if persistent_seen[pid] > 1:
                    pid = f"{pid}:dup_{persistent_seen[pid]}"
                    name["persistent_id"] = pid
                    name["duplicate_resolved"] = True
                item.setdefault("persistent_id", name["persistent_id"])
                item.setdefault("topological_fingerprint", name["fingerprint"])
                item.setdefault("stable_topology_key", name["stable_key"])
                item.setdefault("naming_contract", name["contract"])
                decorated_rows.append(item)
                name_rows.append(name)
            if key == "volumes":
                volumes = decorated_rows
            else:
                surfaces = decorated_rows
        doc["volumes"] = volumes
        doc["surfaces"] = surfaces
        doc["persistent_name_rows"] = name_rows
        doc["persistent_name_index"] = {str(row.get("entity_id") or row.get("persistent_id")): str(row.get("persistent_id")) for row in name_rows}
        doc["topological_naming"] = "feature_semantic_stable_geometry_fingerprint_v4"
        doc["contract"] = "brep_document_with_persistent_topology_names_v4"
        doc["naming_summary"] = {
            "persistent_name_count": len(name_rows),
            "duplicate_name_count": sum(1 for row in name_rows if row.get("duplicate_resolved")),
            "mesh_editable": False,
            "edit_policy": "edit_source_entity_then_remesh",
        }
        return doc

    def build_transfer_candidates(self, old_rows: Iterable[dict[str, Any]], new_rows: Iterable[dict[str, Any]], *, max_distance: float = 0.25) -> dict[str, Any]:
        old_list = [dict(r) for r in list(old_rows or []) if isinstance(r, dict)]
        new_list = [dict(r) for r in list(new_rows or []) if isinstance(r, dict)]
        candidates: list[dict[str, Any]] = []
        for old in old_list:
            old_name = self.name_entity(old)
            old_center = _center(old)
            ranked: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
            for new in new_list:
                new_name = self.name_entity(new)
                score = 0.0
                reasons: list[str] = []
                if new_name.get("fingerprint") == old_name.get("fingerprint"):
                    score += 10.0
                    reasons.append("exact_fingerprint")
                if new_name.get("stable_key") == old_name.get("stable_key"):
                    score += 5.0
                    reasons.append("stable_key")
                if str(new_name.get("source_feature_id") or "") == str(old_name.get("source_feature_id") or ""):
                    score += 3.0
                    reasons.append("same_source_feature")
                if str(new_name.get("kind") or "") == str(old_name.get("kind") or ""):
                    score += 2.0
                    reasons.append("same_kind")
                if str(new_name.get("semantic_role") or "") == str(old_name.get("semantic_role") or ""):
                    score += 1.0
                    reasons.append("same_semantic_role")
                dist = _distance(old_center, _center(new))
                if dist <= max_distance:
                    score += max(0.0, 2.0 * (1.0 - dist / max(max_distance, 1.0e-9)))
                    reasons.append("near_center")
                ranked.append((score, new_name, {"distance": dist, "reasons": reasons}))
            ranked.sort(key=lambda x: x[0], reverse=True)
            best = ranked[0] if ranked else (0.0, {}, {"distance": None, "reasons": []})
            candidates.append({
                "old_entity_id": old_name.get("entity_id"),
                "old_persistent_id": old_name.get("persistent_id"),
                "new_persistent_id": best[1].get("persistent_id", ""),
                "new_entity_id": best[1].get("entity_id", ""),
                "score": float(best[0]),
                "distance": best[2].get("distance"),
                "reasons": best[2].get("reasons", []),
                "auto_transfer_recommended": float(best[0]) >= 6.0,
                "review_required": float(best[0]) < 8.0,
            })
        return {"contract": "persistent_topology_transfer_candidates_v2", "candidates": candidates, "summary": {"candidate_count": len(candidates), "auto_transfer_count": sum(1 for c in candidates if c.get("auto_transfer_recommended")), "review_required_count": sum(1 for c in candidates if c.get("review_required"))}}


__all__ = ["PersistentTopologyName", "PersistentTopologyNamer"]
