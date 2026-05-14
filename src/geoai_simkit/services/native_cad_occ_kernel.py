from __future__ import annotations

"""CAD facade hardening for the 1.4.2a workbench.

The module provides a production-facing facade between GeoProjectDocument
preview geometry and future CAD/BRep kernels. It prefers a gmsh.model.occ path
when available, but it does not certify native BRep output in 1.4.2a. Every
result clearly records whether a native-like backend or a deterministic
axis-aligned fallback executed the operation.

The fallback is intentionally conservative: it only handles axis-aligned volume
bounds and writes auditable topology/persistent-naming records.  This prevents
surrogate geometry from being mistaken for certified CAD output while still
making GUI modelling workflows usable in headless CI and on machines without a
full OCC stack.
"""

from dataclasses import dataclass, field
from hashlib import sha1
import importlib.util
from typing import Any, Iterable


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _round_tuple(values: Iterable[Any], ndigits: int = 9) -> tuple[float, ...]:
    return tuple(round(float(v), ndigits) for v in values)


def _stable_hash(payload: Any) -> str:
    text = repr(payload).encode("utf-8", errors="replace")
    return sha1(text).hexdigest()[:16]


def _volume_bounds(volume: Any) -> tuple[float, float, float, float, float, float] | None:
    bounds = getattr(volume, "bounds", None)
    if bounds is None:
        return None
    if len(bounds) != 6:
        return None
    x0, x1, y0, y1, z0, z1 = _round_tuple(bounds)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if z1 < z0:
        z0, z1 = z1, z0
    return (x0, x1, y0, y1, z0, z1)


def _bbox_union(bounds_rows: list[tuple[float, float, float, float, float, float]]) -> tuple[float, float, float, float, float, float] | None:
    if not bounds_rows:
        return None
    return (
        min(b[0] for b in bounds_rows),
        max(b[1] for b in bounds_rows),
        min(b[2] for b in bounds_rows),
        max(b[3] for b in bounds_rows),
        min(b[4] for b in bounds_rows),
        max(b[5] for b in bounds_rows),
    )


def _bbox_intersection(a: tuple[float, float, float, float, float, float], b: tuple[float, float, float, float, float, float]) -> tuple[float, float, float, float, float, float] | None:
    x0, x1 = max(a[0], b[0]), min(a[1], b[1])
    y0, y1 = max(a[2], b[2]), min(a[3], b[3])
    z0, z1 = max(a[4], b[4]), min(a[5], b[5])
    eps = 1.0e-12
    if x1 - x0 <= eps or y1 - y0 <= eps or z1 - z0 <= eps:
        return None
    return (x0, x1, y0, y1, z0, z1)


def _positive(bounds: tuple[float, float, float, float, float, float], eps: float = 1.0e-12) -> bool:
    return (bounds[1] - bounds[0] > eps) and (bounds[3] - bounds[2] > eps) and (bounds[5] - bounds[4] > eps)


def _subtract_aabb(base: tuple[float, float, float, float, float, float], cutter: tuple[float, float, float, float, float, float]) -> list[tuple[float, float, float, float, float, float]]:
    """Subtract cutter from base and return non-overlapping AABB fragments.

    The returned boxes exactly cover ``base - intersection(base, cutter)`` for
    axis-aligned boxes.  It is not a general CAD boolean, but it is deterministic
    and topology-preserving enough for preview and audit workflows.
    """

    inter = _bbox_intersection(base, cutter)
    if inter is None:
        return [base]
    x0, x1, y0, y1, z0, z1 = base
    ix0, ix1, iy0, iy1, iz0, iz1 = inter
    pieces = [
        (x0, ix0, y0, y1, z0, z1),
        (ix1, x1, y0, y1, z0, z1),
        (ix0, ix1, y0, iy0, z0, z1),
        (ix0, ix1, iy1, y1, z0, z1),
        (ix0, ix1, iy0, iy1, z0, iz0),
        (ix0, ix1, iy0, iy1, iz1, z1),
    ]
    return [p for p in pieces if _positive(p)]


@dataclass(slots=True)
class CadOccCapabilityReport:
    contract: str = "geoai_simkit_cad_facade_capability_v1"
    ok: bool = True
    preferred_backend: str = "gmsh_occ"
    native_available: bool = False
    gmsh_available: bool = False
    gmsh_occ_available: bool = False
    pythonocc_available: bool = False
    ocp_available: bool = False
    fallback_available: bool = True
    selected_backend: str = "aabb_fallback"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "preferred_backend": self.preferred_backend,
            "native_available": bool(self.native_available),
            "gmsh_available": bool(self.gmsh_available),
            "gmsh_occ_available": bool(self.gmsh_occ_available),
            "pythonocc_available": bool(self.pythonocc_available),
            "ocp_available": bool(self.ocp_available),
            "fallback_available": bool(self.fallback_available),
            "selected_backend": self.selected_backend,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class CadTopologyIndexReport:
    contract: str = "geoai_simkit_cad_facade_topology_index_v1"
    ok: bool = False
    solid_count: int = 0
    face_count: int = 0
    edge_count: int = 0
    vertex_count: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "solid_count": int(self.solid_count),
            "face_count": int(self.face_count),
            "edge_count": int(self.edge_count),
            "vertex_count": int(self.vertex_count),
            "records": [dict(r) for r in self.records],
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class CadFeatureExecutionReport:
    contract: str = "geoai_simkit_cad_facade_feature_execution_v1"
    ok: bool = False
    backend: str = "aabb_fallback"
    native_backend_used: bool = False
    fallback_used: bool = True
    feature_count: int = 0
    executed_feature_count: int = 0
    generated_volume_ids: list[str] = field(default_factory=list)
    consumed_volume_ids: list[str] = field(default_factory=list)
    skipped_feature_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    capability: dict[str, Any] = field(default_factory=dict)
    topology_index: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "backend": self.backend,
            "native_backend_used": bool(self.native_backend_used),
            "fallback_used": bool(self.fallback_used),
            "feature_count": int(self.feature_count),
            "executed_feature_count": int(self.executed_feature_count),
            "generated_volume_ids": list(self.generated_volume_ids),
            "consumed_volume_ids": list(self.consumed_volume_ids),
            "skipped_feature_ids": list(self.skipped_feature_ids),
            "warnings": list(self.warnings),
            "capability": dict(self.capability),
            "topology_index": dict(self.topology_index),
            "metadata": dict(self.metadata),
        }


def probe_native_cad_occ_kernel() -> CadOccCapabilityReport:
    """Return a non-throwing capability report for CAD/OCC backends."""

    warnings: list[str] = []
    gmsh_available = _has_module("gmsh")
    pythonocc_available = _has_module("OCC.Core")
    ocp_available = _has_module("OCP")
    gmsh_occ_available = False
    gmsh_version = ""
    if gmsh_available:
        try:
            import gmsh  # type: ignore

            gmsh_version = str(getattr(gmsh, "__version__", ""))
            gmsh_occ_available = hasattr(getattr(gmsh, "model", None), "occ")
        except Exception as exc:
            warnings.append(f"gmsh import failed: {type(exc).__name__}: {exc}")
            gmsh_available = False
            gmsh_occ_available = False
    if not gmsh_occ_available:
        warnings.append("Native gmsh.model.occ backend is unavailable; deterministic AABB fallback will be used unless native execution is required.")
    native = bool(gmsh_occ_available or pythonocc_available or ocp_available)
    selected = "gmsh_occ" if gmsh_occ_available else ("pythonocc" if pythonocc_available else ("ocp" if ocp_available else "aabb_fallback"))
    return CadOccCapabilityReport(
        ok=True,
        native_available=native,
        gmsh_available=gmsh_available,
        gmsh_occ_available=gmsh_occ_available,
        pythonocc_available=pythonocc_available,
        ocp_available=ocp_available,
        selected_backend=selected,
        warnings=warnings,
        metadata={"gmsh_version": gmsh_version, "release_mode": "cad_facade", "native_certified": False},
    )


def _volume_face_records(volume_id: str, bounds: tuple[float, float, float, float, float, float]) -> list[dict[str, Any]]:
    x0, x1, y0, y1, z0, z1 = bounds
    faces = [
        ("xmin", (x0, x0, y0, y1, z0, z1), (-1.0, 0.0, 0.0), (y1 - y0) * (z1 - z0)),
        ("xmax", (x1, x1, y0, y1, z0, z1), (1.0, 0.0, 0.0), (y1 - y0) * (z1 - z0)),
        ("ymin", (x0, x1, y0, y0, z0, z1), (0.0, -1.0, 0.0), (x1 - x0) * (z1 - z0)),
        ("ymax", (x0, x1, y1, y1, z0, z1), (0.0, 1.0, 0.0), (x1 - x0) * (z1 - z0)),
        ("zmin", (x0, x1, y0, y1, z0, z0), (0.0, 0.0, -1.0), (x1 - x0) * (y1 - y0)),
        ("zmax", (x0, x1, y0, y1, z1, z1), (0.0, 0.0, 1.0), (x1 - x0) * (y1 - y0)),
    ]
    records = []
    for side, fbounds, normal, area in faces:
        name = f"{volume_id}/face/{side}"
        records.append({
            "kind": "face",
            "source_entity_id": volume_id,
            "stable_name": name,
            "side": side,
            "bounds": list(fbounds),
            "normal": list(normal),
            "area": float(area),
            "topology_hash": _stable_hash((name, _round_tuple(fbounds), normal)),
        })
    return records


def _volume_vertex_records(volume_id: str, bounds: tuple[float, float, float, float, float, float]) -> list[dict[str, Any]]:
    x0, x1, y0, y1, z0, z1 = bounds
    pts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    rows = []
    for i, xyz in enumerate(pts):
        name = f"{volume_id}/vertex/{i}"
        rows.append({"kind": "vertex", "source_entity_id": volume_id, "stable_name": name, "xyz": list(xyz), "topology_hash": _stable_hash((name, _round_tuple(xyz)))})
    return rows


def _volume_edge_records(volume_id: str, bounds: tuple[float, float, float, float, float, float]) -> list[dict[str, Any]]:
    # Edges are defined by vertex index pairs from the ordering above.
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    rows = []
    vertices = _volume_vertex_records(volume_id, bounds)
    coords = [tuple(v["xyz"]) for v in vertices]
    for i, (a, b) in enumerate(edges):
        name = f"{volume_id}/edge/{i}"
        rows.append({"kind": "edge", "source_entity_id": volume_id, "stable_name": name, "vertex_names": [vertices[a]["stable_name"], vertices[b]["stable_name"]], "points": [list(coords[a]), list(coords[b])], "topology_hash": _stable_hash((name, coords[a], coords[b]))})
    return rows


def build_cad_topology_index(project: Any, *, attach: bool = True) -> CadTopologyIndexReport:
    """Build persistent CAD-style names for GeoProject volumes/faces/edges."""

    records: list[dict[str, Any]] = []
    solid_count = face_count = edge_count = vertex_count = 0
    for volume_id, volume in sorted(getattr(project.geometry_model, "volumes", {}).items()):
        bounds = _volume_bounds(volume)
        if bounds is None:
            continue
        solid_name = f"{volume_id}/solid"
        records.append({
            "kind": "solid",
            "source_entity_id": volume_id,
            "stable_name": solid_name,
            "bounds": list(bounds),
            "role": getattr(volume, "role", "unknown"),
            "material_id": getattr(volume, "material_id", None),
            "topology_hash": _stable_hash((solid_name, bounds, getattr(volume, "role", "unknown"))),
        })
        solid_count += 1
        faces = _volume_face_records(volume_id, bounds)
        edges = _volume_edge_records(volume_id, bounds)
        vertices = _volume_vertex_records(volume_id, bounds)
        face_count += len(faces)
        edge_count += len(edges)
        vertex_count += len(vertices)
        records.extend(faces)
        records.extend(edges)
        records.extend(vertices)
    report = CadTopologyIndexReport(
        ok=solid_count > 0,
        solid_count=solid_count,
        face_count=face_count,
        edge_count=edge_count,
        vertex_count=vertex_count,
        records=records,
        metadata={"naming_scheme": "source_entity_id/topology_kind/index_or_side", "hash_precision": 9, "topology_source": "aabb_facade_or_imported_bounds", "native_brep_topology": False},
    )
    if attach:
        project.geometry_model.metadata["cad_occ_topology_index"] = report.to_dict()
        try:
            project.mark_changed(["geometry"], action="build_cad_topology_index", affected_entities=[r["source_entity_id"] for r in records if r["kind"] == "solid"])
        except Exception:
            pass
    return report


def _next_volume_id(project: Any, prefix: str = "cad_volume") -> str:
    existing = getattr(project.geometry_model, "volumes", {})
    i = len(existing) + 1
    while f"{prefix}_{i:03d}" in existing:
        i += 1
    return f"{prefix}_{i:03d}"


def _new_volume(project: Any, bounds: tuple[float, float, float, float, float, float], *, name: str, role: str = "unknown", material_id: str | None = None, metadata: dict[str, Any] | None = None) -> str:
    from geoai_simkit.geoproject import GeometryVolume

    vid = _next_volume_id(project)
    project.geometry_model.volumes[vid] = GeometryVolume(id=vid, name=name, bounds=tuple(float(v) for v in bounds), role=role, material_id=material_id, metadata=dict(metadata or {}))
    try:
        for phase_id in project.phase_ids():
            project.set_phase_volume_activation(phase_id, vid, True)
    except Exception:
        pass
    return vid


def _target_volumes(project: Any, target_ids: Iterable[str]) -> list[Any]:
    volumes = []
    for tid in target_ids:
        volume = project.geometry_model.volumes.get(str(tid))
        if volume is not None:
            volumes.append(volume)
    return volumes


def _execute_boolean_aabb(project: Any, feature: Any, *, backend: str) -> tuple[list[str], list[str], list[str]]:
    params = dict(getattr(feature, "parameters", {}) or {})
    operation = str(params.get("operation", "union")).lower()
    target_ids = [str(v) for v in params.get("target_ids", getattr(feature, "target_block_ids", []) or [])]
    volumes = _target_volumes(project, target_ids)
    bounds_rows = [b for b in (_volume_bounds(v) for v in volumes) if b is not None]
    generated: list[str] = []
    consumed: list[str] = []
    warnings: list[str] = []
    if not bounds_rows:
        return generated, consumed, [f"feature {feature.id} has no valid target volume bounds"]
    base = volumes[0]
    role = getattr(base, "role", "unknown") or "unknown"
    material_id = getattr(base, "material_id", None)
    if operation in {"union", "fuse", "merge"}:
        merged = _bbox_union(bounds_rows)
        if merged is None:
            return generated, consumed, [f"feature {feature.id} union produced no bounds"]
        vid = _new_volume(
            project,
            merged,
            name=f"cad_union_{feature.id}",
            role=role,
            material_id=material_id,
            metadata={"created_by_cad_feature": feature.id, "cad_backend": backend, "cad_operation": operation, "source_volume_ids": target_ids, "visible": True},
        )
        generated.append(vid)
        consumed.extend(target_ids)
    elif operation in {"subtract", "cut", "difference"}:
        fragments = [bounds_rows[0]]
        for cutter in bounds_rows[1:]:
            new_fragments: list[tuple[float, float, float, float, float, float]] = []
            for frag in fragments:
                new_fragments.extend(_subtract_aabb(frag, cutter))
            fragments = new_fragments
        if not fragments:
            warnings.append(f"feature {feature.id} subtract removed the entire base volume")
        for index, fragment in enumerate(fragments, start=1):
            vid = _new_volume(
                project,
                fragment,
                name=f"cad_subtract_{feature.id}_{index}",
                role=role,
                material_id=material_id,
                metadata={"created_by_cad_feature": feature.id, "cad_backend": backend, "cad_operation": operation, "source_volume_ids": target_ids, "visible": True},
            )
            generated.append(vid)
        consumed.append(target_ids[0])
    else:
        warnings.append(f"feature {feature.id} operation {operation!r} is not supported by the 1.4.2 CAD executor")
    for tid in consumed:
        volume = project.geometry_model.volumes.get(tid)
        if volume is not None:
            volume.metadata["visible"] = False
            volume.metadata["cad_consumed_by"] = str(feature.id)
    return generated, consumed, warnings


def _execute_boolean_gmsh_occ(project: Any, feature: Any) -> tuple[list[str], list[str], list[str]]:
    """Try a native gmsh.model.occ boolean and import result bboxes.

    The native path is intentionally small and defensive.  It is used only when
    gmsh with an OCC model is importable.  Failures are reported to the caller so
    it can fall back or raise depending on policy.
    """

    import gmsh  # type: ignore

    params = dict(getattr(feature, "parameters", {}) or {})
    operation = str(params.get("operation", "union")).lower()
    target_ids = [str(v) for v in params.get("target_ids", getattr(feature, "target_block_ids", []) or [])]
    volumes = _target_volumes(project, target_ids)
    if len(volumes) < 1:
        return [], [], [f"feature {feature.id} has no target volumes"]
    initialized_here = False
    try:
        try:
            gmsh.initialize()
            initialized_here = True
        except Exception:
            initialized_here = False
        gmsh.model.add(f"geoai_cad_feature_{feature.id}")
        dimtags: list[tuple[int, int]] = []
        id_by_tag: dict[int, str] = {}
        for volume in volumes:
            b = _volume_bounds(volume)
            if b is None:
                continue
            x0, x1, y0, y1, z0, z1 = b
            tag = gmsh.model.occ.addBox(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0)
            dimtags.append((3, int(tag)))
            id_by_tag[int(tag)] = str(getattr(volume, "id", ""))
        if not dimtags:
            return [], [], [f"feature {feature.id} has no native OCC boxes"]
        if operation in {"union", "fuse", "merge"} and len(dimtags) > 1:
            out, _map = gmsh.model.occ.fuse([dimtags[0]], dimtags[1:], removeObject=True, removeTool=True)
        elif operation in {"subtract", "cut", "difference"} and len(dimtags) > 1:
            out, _map = gmsh.model.occ.cut([dimtags[0]], dimtags[1:], removeObject=True, removeTool=True)
        else:
            out = dimtags
        gmsh.model.occ.synchronize()
        generated: list[str] = []
        consumed: list[str] = list(target_ids if operation in {"union", "fuse", "merge"} else target_ids[:1])
        base = volumes[0]
        role = getattr(base, "role", "unknown") or "unknown"
        material_id = getattr(base, "material_id", None)
        for index, dimtag in enumerate(out, start=1):
            if not dimtag or int(dimtag[0]) != 3:
                continue
            try:
                xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(int(dimtag[0]), int(dimtag[1]))
            except Exception:
                continue
            bounds = (float(xmin), float(xmax), float(ymin), float(ymax), float(zmin), float(zmax))
            if not _positive(bounds):
                continue
            vid = _new_volume(
                project,
                bounds,
                name=f"occ_{operation}_{feature.id}_{index}",
                role=role,
                material_id=material_id,
                metadata={"created_by_cad_feature": feature.id, "cad_backend": "gmsh_occ", "cad_operation": operation, "source_volume_ids": target_ids, "occ_dimtag": [int(dimtag[0]), int(dimtag[1])], "visible": True},
            )
            generated.append(vid)
        for tid in consumed:
            volume = project.geometry_model.volumes.get(tid)
            if volume is not None:
                volume.metadata["visible"] = False
                volume.metadata["cad_consumed_by"] = str(feature.id)
        return generated, consumed, []
    finally:
        if initialized_here:
            try:
                gmsh.finalize()
            except Exception:
                pass


def execute_deferred_cad_features(
    project: Any,
    *,
    require_native: bool = False,
    allow_fallback: bool = True,
    attach_topology_index: bool = True,
) -> CadFeatureExecutionReport:
    """Execute deferred boolean CAD features in a GeoProjectDocument.

    Deferred features are generated by the 1.4.1 geometry authoring tools.  This
    executor resolves them through a native gmsh/OCC backend where possible and
    otherwise uses deterministic AABB operations when allowed.
    """

    capability = probe_native_cad_occ_kernel()
    features = list(getattr(project.geometry_model, "parametric_features", {}).values())
    candidate_features = []
    for feature in features:
        params = dict(getattr(feature, "parameters", {}) or {})
        if params.get("backend") == "deferred_occ_boolean" and getattr(feature, "metadata", {}).get("status") != "executed":
            candidate_features.append(feature)
    warnings: list[str] = []
    generated_all: list[str] = []
    consumed_all: list[str] = []
    skipped: list[str] = []
    backend = capability.selected_backend
    native_used = False
    fallback_used = True
    if require_native and not capability.native_available:
        raise RuntimeError("Native CAD/OCC execution is required but no native backend is available.")
    for feature in candidate_features:
        generated: list[str] = []
        consumed: list[str] = []
        fwarnings: list[str] = []
        used_backend = backend
        if capability.gmsh_occ_available:
            try:
                generated, consumed, fwarnings = _execute_boolean_gmsh_occ(project, feature)
                used_backend = "gmsh_occ"
                native_used = True
                fallback_used = False
            except Exception as exc:
                fwarnings.append(f"Native gmsh/OCC execution failed for {feature.id}: {type(exc).__name__}: {exc}")
                if not allow_fallback:
                    raise
        if not generated and allow_fallback:
            used_backend = "aabb_fallback"
            g2, c2, w2 = _execute_boolean_aabb(project, feature, backend=used_backend)
            generated, consumed = g2, c2
            fwarnings.extend(w2)
            fallback_used = True
        if generated or consumed:
            feature.generated_block_ids = tuple(generated)
            feature.metadata["status"] = "executed"
            feature.metadata["executed_by"] = "execute_deferred_cad_features"
            feature.metadata["cad_backend"] = used_backend
            feature.metadata["native_backend_used"] = used_backend == "gmsh_occ"
            feature.metadata["fallback_used"] = used_backend != "gmsh_occ"
            generated_all.extend(generated)
            consumed_all.extend(consumed)
        else:
            skipped.append(str(feature.id))
        warnings.extend(fwarnings)
    topology = build_cad_topology_index(project, attach=attach_topology_index)
    ok = len(candidate_features) == 0 or (len(generated_all) > 0 and len(skipped) == 0)
    report = CadFeatureExecutionReport(
        ok=ok,
        backend="gmsh_occ" if native_used and not fallback_used else ("mixed" if native_used and fallback_used else "aabb_fallback"),
        native_backend_used=native_used,
        fallback_used=fallback_used,
        feature_count=len(candidate_features),
        executed_feature_count=len(candidate_features) - len(skipped),
        generated_volume_ids=generated_all,
        consumed_volume_ids=sorted(set(consumed_all)),
        skipped_feature_ids=skipped,
        warnings=warnings,
        capability=capability.to_dict(),
        topology_index=topology.to_dict(),
        metadata={"require_native": bool(require_native), "allow_fallback": bool(allow_fallback), "release_mode": "cad_facade", "native_brep_certified": False, "backend_mode": ("native_passthrough_facade" if native_used and not fallback_used else ("mixed_facade" if native_used and fallback_used else "deterministic_aabb_facade"))},
    )
    project.geometry_model.metadata["last_cad_occ_feature_execution"] = report.to_dict()
    project.metadata["release_1_4_2a_cad_facade_occ"] = report.to_dict()
    try:
        project.mark_changed(["geometry", "topology", "mesh", "solver", "result"], action="execute_deferred_cad_features", affected_entities=[*generated_all, *consumed_all])
    except Exception:
        pass
    return report


__all__ = [
    "CadOccCapabilityReport",
    "CadTopologyIndexReport",
    "CadFeatureExecutionReport",
    "probe_native_cad_occ_kernel",
    "build_cad_topology_index",
    "execute_deferred_cad_features",
]
