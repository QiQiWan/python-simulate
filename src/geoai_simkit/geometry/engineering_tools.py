from __future__ import annotations

"""Dependency-light engineering tools for the section-based visual editor."""

from dataclasses import dataclass
from math import hypot
from typing import Any, Iterable

from geoai_simkit.geometry.editor import GeometryEditor
from geoai_simkit.geometry.entities import PartitionFeature


def _next_key(mapping: dict[str, Any], prefix: str) -> str:
    idx = len(mapping) + 1
    while f"{prefix}_{idx:03d}" in mapping:
        idx += 1
    return f"{prefix}_{idx:03d}"


def _next_partition_id(document: Any, prefix: str) -> str:
    existing = getattr(document.geometry, "partition_features", {})
    idx = len(existing) + 1
    while f"partition:{prefix}:{idx:03d}" in existing:
        idx += 1
    return f"partition:{prefix}:{idx:03d}"


def _overlap(a0: float, a1: float, b0: float, b1: float, *, tol: float = 1e-9) -> bool:
    return min(a1, b1) - max(a0, b0) > tol


@dataclass(slots=True)
class SnapCandidate:
    x: float
    y: float
    z: float
    kind: str
    source_id: str
    distance: float
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": float(self.x),
            "y": float(self.y),
            "z": float(self.z),
            "kind": self.kind,
            "source_id": self.source_id,
            "distance": float(self.distance),
            "label": self.label or self.source_id,
        }


@dataclass(slots=True)
class EngineeringSnapService:
    document: Any
    grid_size: float = 1.0
    grid_tolerance: float = 0.35
    endpoint_tolerance: float = 0.85
    enabled: bool = True

    def grid_point(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        g = self.grid_size if self.grid_size > 0 else 1.0
        return (round(float(x) / g) * g, round(float(y) / g) * g, round(float(z) / g) * g)

    def endpoint_candidates(self, x: float, y: float, z: float) -> list[SnapCandidate]:
        out: list[SnapCandidate] = []
        for pid, point in self.document.geometry.points.items():
            px, py, pz = point.to_tuple()
            dist = hypot(float(x) - px, float(z) - pz)
            if dist <= self.endpoint_tolerance:
                out.append(SnapCandidate(px, py, pz, "endpoint", pid, dist, label=pid))
        out.sort(key=lambda item: item.distance)
        return out

    def locate(self, x: float, y: float, z: float, *, prefer_endpoint: bool = True) -> dict[str, Any]:
        raw = (float(x), float(y), float(z))
        endpoints = self.endpoint_candidates(*raw)
        endpoint = endpoints[0] if prefer_endpoint and endpoints else None
        if endpoint is not None and self.enabled:
            snapped = (endpoint.x, endpoint.y, endpoint.z)
            mode = "endpoint"
            source_id = endpoint.source_id
            dist = endpoint.distance
        else:
            grid = self.grid_point(*raw)
            grid_dist = hypot(raw[0] - grid[0], raw[2] - grid[2])
            if self.enabled and grid_dist <= self.grid_tolerance:
                snapped = grid
                mode = "grid"
                source_id = "grid"
                dist = grid_dist
            else:
                snapped = raw
                mode = "free"
                source_id = ""
                dist = 0.0
        return {
            "raw": list(raw),
            "snapped": list(snapped),
            "snap_mode": mode,
            "source_id": source_id,
            "distance": float(dist),
            "grid_size": float(self.grid_size),
            "enabled": bool(self.enabled),
            "endpoint_candidates": [item.to_dict() for item in endpoints[:8]],
        }

    def grid_overlays(self, *, x_min: float = -50.0, x_max: float = 50.0, z_min: float = -35.0, z_max: float = 5.0, max_lines: int = 240) -> list[dict[str, Any]]:
        g = self.grid_size if self.grid_size > 0 else 1.0
        overlays: list[dict[str, Any]] = []
        for ix in range(int(x_min // g) - 1, int(x_max // g) + 2):
            x = ix * g
            overlays.append({"kind": "grid_line", "axis": "x", "points": [[x, 0.0, z_min], [x, 0.0, z_max]], "major": ix % 5 == 0})
            if len(overlays) >= max_lines:
                return overlays
        for iz in range(int(z_min // g) - 1, int(z_max // g) + 2):
            z = iz * g
            overlays.append({"kind": "grid_line", "axis": "z", "points": [[x_min, 0.0, z], [x_max, 0.0, z]], "major": iz % 5 == 0})
            if len(overlays) >= max_lines:
                break
        return overlays

    def endpoint_overlays(self) -> list[dict[str, Any]]:
        return [{"kind": "snap_endpoint", "entity_id": pid, "point": [point.x, point.y, point.z], "label": pid} for pid, point in self.document.geometry.points.items()]

    def contract(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "grid_size": float(self.grid_size),
            "grid_tolerance": float(self.grid_tolerance),
            "endpoint_tolerance": float(self.endpoint_tolerance),
            "endpoint_count": len(self.document.geometry.points),
        }


@dataclass(slots=True)
class EngineeringSupportService:
    document: Any

    def create_support_axis(self, start: tuple[float, float, float], end: tuple[float, float, float], *, support_type: str = "strut", support_id: str | None = None, material_id: str | None = None, stage_id: str | None = None) -> dict[str, Any]:
        editor = GeometryEditor(self.document.geometry)
        edge = editor.create_line_from_coords(start, end, role="support_axis", snap=True)
        sid = support_id or _next_key(self.document.supports, support_type)
        row = {
            "id": sid,
            "type": support_type,
            "axis_edge_id": edge.id,
            "point_ids": list(edge.point_ids),
            "material_id": material_id or f"{support_type}_material",
            "active_stage_id": stage_id or self.document.stages.active_stage_id,
            "start": list(start),
            "end": list(end),
            "status": "active",
        }
        self.document.supports[sid] = row
        if row["material_id"] not in self.document.materials:
            from geoai_simkit.document.engineering_document import MaterialLibraryRecord
            self.document.materials[row["material_id"]] = MaterialLibraryRecord(id=row["material_id"], name=row["material_id"], model_type="support_placeholder")
        stage = self.document.stages.get(str(row["active_stage_id"]))
        if stage is not None:
            stage.active_supports.add(sid)
        self.document.topology.add_node(sid, "support", label=sid, support_type=support_type, axis_edge_id=edge.id)
        self.document.topology.add_node(edge.id, "edge", label=edge.id, role="support_axis")
        self.document.topology.add_edge(sid, edge.id, "mapped_to")
        self.document.dirty.geometry_dirty = True
        self.document.dirty.mesh_dirty = True
        self.document.dirty.solve_dirty = True
        self.document.dirty.result_stale = True
        return row


def split_soil_by_horizontal_level(document: Any, z_level: float, *, target_roles: tuple[str, ...] = ("soil",), layer_prefix: str = "manual_layer") -> dict[str, Any]:
    z = float(z_level)
    editor = GeometryEditor(document.geometry)
    target_ids: list[str] = []
    generated: list[str] = []
    removed: list[str] = []
    for block_id, block in list(document.geometry.blocks.items()):
        if block.role not in target_roles:
            continue
        xmin, xmax, ymin, ymax, zmin, zmax = block.bounds
        if not (zmin < z < zmax):
            continue
        target_ids.append(block_id)
        document.geometry.blocks.pop(block_id, None)
        for fid in block.face_ids:
            document.geometry.faces.pop(fid, None)
        removed.append(block_id)
        lower = editor.create_block((xmin, xmax, ymin, ymax, zmin, z), block_id=f"{block_id}_below_{abs(z):g}".replace(".", "p"), name=f"{block.name} below z={z:g}", role=block.role, material_id=block.material_id, layer_id=f"{layer_prefix}_below_{abs(z):g}".replace(".", "p"), metadata={"split_from": block_id, "split_level": z})
        upper = editor.create_block((xmin, xmax, ymin, ymax, z, zmax), block_id=f"{block_id}_above_{abs(z):g}".replace(".", "p"), name=f"{block.name} above z={z:g}", role=block.role, material_id=block.material_id, layer_id=f"{layer_prefix}_above_{abs(z):g}".replace(".", "p"), metadata={"split_from": block_id, "split_level": z})
        generated.extend([lower.id, upper.id])
    feature_id = _next_partition_id(document, "horizontal_layer_drag")
    document.geometry.partition_features[feature_id] = PartitionFeature(id=feature_id, type="horizontal_layer", parameters={"z_level": z, "source": "mouse_drag_split"}, target_block_ids=tuple(target_ids), generated_block_ids=tuple(generated), metadata={"removed_block_ids": removed})
    from geoai_simkit.geometry.light_block_kernel import LightBlockKernel
    document.topology = LightBlockKernel().find_adjacent_faces(document.geometry)
    document.dirty.geometry_dirty = True
    document.dirty.mesh_dirty = True
    document.dirty.solve_dirty = True
    document.dirty.result_stale = True
    return {"feature_id": feature_id, "z_level": z, "target_block_ids": target_ids, "generated_block_ids": generated, "removed_block_ids": removed}


def split_excavation_by_polygon(document: Any, vertices: list[tuple[float, float, float]], *, stage_id: str | None = None) -> dict[str, Any]:
    if len(vertices) < 3:
        raise ValueError("Excavation polygon requires at least three vertices.")
    xs = [float(v[0]) for v in vertices]
    ys = [float(v[1]) for v in vertices]
    zs = [float(v[2]) for v in vertices]
    ex0, ex1 = min(xs), max(xs)
    ey0, ey1 = min(ys) - 0.5, max(ys) + 0.5
    ez0, ez1 = min(zs), max(zs)
    if abs(ey1 - ey0) < 1e-6:
        ey0, ey1 = -0.5, 0.5
    editor = GeometryEditor(document.geometry)
    removed: list[str] = []
    generated_soil: list[str] = []
    generated_excavation: list[str] = []
    target_ids: list[str] = []
    for block_id, block in list(document.geometry.blocks.items()):
        if block.role != "soil":
            continue
        xmin, xmax, ymin, ymax, zmin, zmax = block.bounds
        if not (_overlap(xmin, xmax, ex0, ex1) and _overlap(zmin, zmax, ez0, ez1)):
            continue
        target_ids.append(block_id)
        document.geometry.blocks.pop(block_id, None)
        for fid in block.face_ids:
            document.geometry.faces.pop(fid, None)
        removed.append(block_id)
        ix0, ix1 = max(xmin, ex0), min(xmax, ex1)
        iz0, iz1 = max(zmin, ez0), min(zmax, ez1)
        excavation = editor.create_block((ix0, ix1, ymin, ymax, iz0, iz1), block_id=f"excavation_poly_{len(generated_excavation)+1:03d}", name=f"Excavation polygon {len(generated_excavation)+1}", role="excavation", material_id=None, metadata={"split_from": block_id, "polygon_vertices": [list(v) for v in vertices]})
        generated_excavation.append(excavation.id)
        fragments = [
            (xmin, ix0, ymin, ymax, zmin, zmax, "left"),
            (ix1, xmax, ymin, ymax, zmin, zmax, "right"),
            (ix0, ix1, ymin, ymax, zmin, iz0, "below"),
            (ix0, ix1, ymin, ymax, iz1, zmax, "above"),
        ]
        for fx0, fx1, fy0, fy1, fz0, fz1, label in fragments:
            if fx1 - fx0 > 1e-8 and fy1 - fy0 > 1e-8 and fz1 - fz0 > 1e-8:
                soil = editor.create_block((fx0, fx1, fy0, fy1, fz0, fz1), block_id=f"{block_id}_{label}_after_excavation_{len(generated_soil)+1:03d}", name=f"{block.name} {label} residual", role="soil", material_id=block.material_id, layer_id=block.layer_id, metadata={"split_from": block_id, "excavation_polygon_feature": True})
                generated_soil.append(soil.id)
    active_stage = stage_id or document.stages.active_stage_id
    if active_stage and active_stage in document.stages.stages:
        for bid in generated_excavation:
            document.stages.deactivate_block(active_stage, bid)
    feature_id = _next_partition_id(document, "excavation_polygon")
    document.geometry.partition_features[feature_id] = PartitionFeature(id=feature_id, type="excavation_surface", parameters={"polygon_vertices": [list(v) for v in vertices], "bbox": [ex0, ex1, ey0, ey1, ez0, ez1], "stage_id": active_stage}, target_block_ids=tuple(target_ids), generated_block_ids=tuple([*generated_excavation, *generated_soil]), metadata={"removed_block_ids": removed, "implementation": "section_bbox_prism"})
    from geoai_simkit.geometry.light_block_kernel import LightBlockKernel
    document.topology = LightBlockKernel().find_adjacent_faces(document.geometry)
    document.dirty.geometry_dirty = True
    document.dirty.mesh_dirty = True
    document.dirty.solve_dirty = True
    document.dirty.result_stale = True
    return {"feature_id": feature_id, "removed_block_ids": removed, "excavation_block_ids": generated_excavation, "residual_soil_block_ids": generated_soil, "stage_id": active_stage}


@dataclass(slots=True)
class InterfaceReviewService:
    document: Any

    def rebuild_candidates(self) -> list[dict[str, Any]]:
        from geoai_simkit.geometry.light_block_kernel import LightBlockKernel
        self.document.topology = LightBlockKernel().find_adjacent_faces(self.document.geometry)
        rows: list[dict[str, Any]] = []
        for idx, edge in enumerate(self.document.topology.contact_edges(), start=1):
            attrs = dict(edge.attributes)
            source_node = self.document.topology.nodes.get(edge.source)
            target_node = self.document.topology.nodes.get(edge.target)
            source_role = str(source_node.attributes.get("role", "")) if source_node else ""
            target_role = str(target_node.attributes.get("role", "")) if target_node else ""
            pair_id = attrs.get("contact_id") or f"contact_{idx:03d}"
            if "wall" in {source_role, target_role} or "support" in {source_role, target_role}:
                contact_type = "interface"
            elif "excavation" in {source_role, target_role}:
                contact_type = "release"
            else:
                contact_type = "tie"
            rows.append({
                "id": str(pair_id),
                "source_block_id": edge.source,
                "target_block_id": edge.target,
                "source_role": source_role,
                "target_role": target_role,
                "contact_type": contact_type,
                "status": "candidate",
                "confidence": float(attrs.get("confidence", 0.85) or 0.85),
                "attributes": attrs,
            })
        self.document.metadata["interface_review_candidates"] = rows
        return rows

    def rows(self) -> list[dict[str, Any]]:
        existing = list(self.document.metadata.get("interface_review_candidates", []) or [])
        if existing:
            accepted = {str(v.get("contact_id") or v.get("id")): dict(v) for v in self.document.interfaces.values() if isinstance(v, dict)}
            for row in existing:
                if row["id"] in accepted:
                    row.update({"status": accepted[row["id"]].get("status", "accepted"), "contact_type": accepted[row["id"]].get("contact_type", row.get("contact_type"))})
            return existing
        return self.rebuild_candidates()

    def set_status(self, contact_id: str, *, status: str = "accepted", contact_type: str | None = None) -> dict[str, Any]:
        rows = self.rows()
        match = None
        for row in rows:
            if row.get("id") == contact_id:
                match = dict(row)
                break
        if match is None:
            raise KeyError(f"Contact candidate not found: {contact_id}")
        if contact_type is not None:
            match["contact_type"] = contact_type
        match["status"] = status
        match["contact_id"] = contact_id
        self.document.interfaces[contact_id] = match
        if status == "accepted":
            stage = self.document.stages.get()
            if stage is not None:
                stage.active_interfaces.add(contact_id)
        self.document.metadata["interface_review_candidates"] = [match if row.get("id") == contact_id else row for row in rows]
        self.document.dirty.mesh_dirty = True
        self.document.dirty.solve_dirty = True
        self.document.dirty.result_stale = True
        return match

    def accept_all(self, *, max_count: int | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.rows()[: max_count or None]:
            out.append(self.set_status(str(row["id"]), status="accepted", contact_type=str(row.get("contact_type") or "interface")))
        return out

    def contract(self) -> dict[str, Any]:
        rows = self.rows()
        accepted = [r for r in rows if str(r.get("status")) == "accepted"]
        rejected = [r for r in rows if str(r.get("status")) == "rejected"]
        pending = [r for r in rows if str(r.get("status")) not in {"accepted", "rejected"}]
        return {
            "rows": rows,
            "summary": {
                "candidate_count": len(rows),
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "pending_count": len(pending),
                "interface_count": len(self.document.interfaces),
            },
        }


__all__ = [
    "EngineeringSnapService",
    "EngineeringSupportService",
    "InterfaceReviewService",
    "split_soil_by_horizontal_level",
    "split_excavation_by_polygon",
]
