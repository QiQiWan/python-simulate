from __future__ import annotations

"""Dependency-light block kernel for PLAXIS-like staged pit modeling."""

from typing import Any

from geoai_simkit.geometry.entities import BlockEntity, FaceEntity, PartitionFeature
from geoai_simkit.geometry.foundation_pit_blocks import build_foundation_pit_blocks
from geoai_simkit.geometry.kernel import GeometryBuildResult, GeometryDocument, GeometryKernel
from geoai_simkit.geometry.topology_graph import TopologyGraph, build_topology_from_foundation_pit_artifact


def _boundary_type(face: dict[str, Any]) -> str:
    role = str(face.get("role") or "").lower()
    side = str(face.get("side") or "").lower()
    axis = str(face.get("axis") or "").lower()
    if axis == "z" and side == "max":
        return "ground_surface"
    if axis == "z" and side == "min":
        return "bottom"
    if "horizontal" in role:
        return "horizontal_layer"
    return "external" if role == "boundary" else "unknown"


class LightBlockKernel(GeometryKernel):
    name = "light_block_kernel"

    def create_foundation_pit(self, parameters: dict[str, Any] | None = None) -> GeometryBuildResult:
        artifact = build_foundation_pit_blocks(parameters or {})
        geometry = geometry_document_from_artifact(artifact)
        topology = build_topology_from_foundation_pit_artifact(artifact)
        geometry.metadata.update({"kernel": self.name, "contract": artifact.get("contract"), "dimension": artifact.get("dimension")})
        return GeometryBuildResult(geometry=geometry, topology=topology, artifact=artifact)

    def split_by_horizontal_layers(self, document: GeometryDocument, levels: list[float]) -> GeometryDocument:
        feature_id = f"partition:horizontal_layer:{len(document.partition_features)+1:03d}"
        document.partition_features[feature_id] = PartitionFeature(
            id=feature_id,
            type="horizontal_layer",
            parameters={"z_levels": [float(v) for v in levels]},
            target_block_ids=tuple(document.blocks.keys()),
            generated_block_ids=tuple(document.blocks.keys()),
        )
        document.metadata["last_partition"] = feature_id
        return document

    def split_by_excavation(self, document: GeometryDocument, excavation_levels: list[float]) -> GeometryDocument:
        feature_id = f"partition:excavation_surface:{len(document.partition_features)+1:03d}"
        generated = tuple(block_id for block_id, block in document.blocks.items() if block.role == "excavation")
        document.partition_features[feature_id] = PartitionFeature(
            id=feature_id,
            type="excavation_surface",
            parameters={"excavation_levels": [float(v) for v in excavation_levels]},
            target_block_ids=tuple(document.blocks.keys()),
            generated_block_ids=generated,
        )
        document.metadata["last_partition"] = feature_id
        return document

    def find_adjacent_faces(self, document: GeometryDocument) -> TopologyGraph:
        graph = TopologyGraph()
        for block in document.blocks.values():
            graph.add_node(block.id, "block", label=block.name, role=block.role, material_id=block.material_id, layer_id=block.layer_id, bounds=list(block.bounds))
            for face_id in block.face_ids:
                if face_id in document.faces:
                    face = document.faces[face_id]
                    graph.add_node(face_id, "face", label=face_id, boundary_type=face.boundary_type, axis=face.axis, side=face.side, area=face.area)
                    graph.add_edge(block.id, face_id, "owns")
                    graph.add_edge(face_id, block.id, "bounded_by")

        blocks = list(document.blocks.values())
        tol = 1.0e-8

        def interval_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
            return max(0.0, min(a1, b1) - max(a0, b0))

        for i, a in enumerate(blocks):
            ax0, ax1, ay0, ay1, az0, az1 = a.bounds
            for b in blocks[i + 1:]:
                bx0, bx1, by0, by1, bz0, bz1 = b.bounds
                axis = None
                coordinate = None
                overlap_area = 0.0
                if abs(ax1 - bx0) <= tol or abs(bx1 - ax0) <= tol:
                    oy = interval_overlap(ay0, ay1, by0, by1)
                    oz = interval_overlap(az0, az1, bz0, bz1)
                    if oy > tol and oz > tol:
                        axis = "x"
                        coordinate = ax1 if abs(ax1 - bx0) <= tol else bx1
                        overlap_area = oy * oz
                if axis is None and (abs(ay1 - by0) <= tol or abs(by1 - ay0) <= tol):
                    ox = interval_overlap(ax0, ax1, bx0, bx1)
                    oz = interval_overlap(az0, az1, bz0, bz1)
                    if ox > tol and oz > tol:
                        axis = "y"
                        coordinate = ay1 if abs(ay1 - by0) <= tol else by1
                        overlap_area = ox * oz
                if axis is None and (abs(az1 - bz0) <= tol or abs(bz1 - az0) <= tol):
                    ox = interval_overlap(ax0, ax1, bx0, bx1)
                    oy = interval_overlap(ay0, ay1, by0, by1)
                    if ox > tol and oy > tol:
                        axis = "z"
                        coordinate = az1 if abs(az1 - bz0) <= tol else bz1
                        overlap_area = ox * oy
                if axis is None:
                    continue
                roles = {str(a.role), str(b.role)}
                if "wall" in roles or "support" in roles:
                    contact_mode = "interface"
                elif "excavation" in roles:
                    contact_mode = "release"
                else:
                    contact_mode = "tie"
                contact_id = f"contact:{a.id}:{b.id}:{axis}:{coordinate:.6g}"
                graph.add_edge(a.id, b.id, "adjacent_to", axis=axis, coordinate=coordinate, overlap_area=overlap_area, contact_mode=contact_mode, contact_id=contact_id)
                graph.add_edge(a.id, b.id, "contacts", axis=axis, coordinate=coordinate, overlap_area=overlap_area, contact_mode=contact_mode, contact_id=contact_id, confidence=0.9)
        return graph


def geometry_document_from_artifact(artifact: dict[str, Any]) -> GeometryDocument:
    faces_by_block: dict[str, list[str]] = {}
    faces: dict[str, FaceEntity] = {}
    for row in list(artifact.get("face_tags", []) or []):
        fid = str(row.get("tag") or row.get("id") or "")
        owner = str(row.get("block_name") or row.get("owner_block_id") or "")
        if not fid or not owner:
            continue
        face = FaceEntity(
            id=fid,
            owner_block_id=owner,
            axis=str(row.get("axis") or ""),
            side=str(row.get("side") or ""),
            coordinate=float(row.get("coordinate") or 0.0),
            area=float(row.get("area") or 0.0),
            boundary_type=_boundary_type(row),
            metadata=dict(row.get("metadata", {}) or {}),
        )
        faces[fid] = face
        faces_by_block.setdefault(owner, []).append(fid)
    blocks: dict[str, BlockEntity] = {}
    for row in list(artifact.get("blocks", []) or []):
        name = str(row.get("name") or row.get("id") or "")
        if not name:
            continue
        bounds = tuple(float(v) for v in list(row.get("bounds", []) or [])[:6])
        if len(bounds) != 6:
            continue
        blocks[name] = BlockEntity(
            id=name,
            name=name,
            bounds=bounds,  # type: ignore[arg-type]
            role=str(row.get("role") or "unknown"),  # type: ignore[arg-type]
            material_id=None if row.get("material_name") in {None, ""} else str(row.get("material_name")),
            layer_id=None if row.get("layer_name") in {None, ""} else str(row.get("layer_name")),
            active_stage_ids=tuple(str(v) for v in list(row.get("active_stages", []) or [])),
            face_ids=tuple(faces_by_block.get(name, [])),
            metadata=dict(row.get("metadata", {}) or {}),
        )
    features: dict[str, PartitionFeature] = {}
    params = dict(artifact.get("parameters", {}) or {})
    if params.get("layer_levels"):
        features["partition:horizontal_layers"] = PartitionFeature(
            id="partition:horizontal_layers",
            type="horizontal_layer",
            parameters={"z_levels": list(params.get("layer_levels") or [])},
            generated_block_ids=tuple(blocks.keys()),
        )
    if params.get("excavation_levels"):
        features["partition:excavation_levels"] = PartitionFeature(
            id="partition:excavation_levels",
            type="excavation_surface",
            parameters={"excavation_levels": list(params.get("excavation_levels") or [])},
            generated_block_ids=tuple(k for k, b in blocks.items() if b.role == "excavation"),
        )
    return GeometryDocument(blocks=blocks, faces=faces, partition_features=features, metadata={"source": "foundation_pit_blocks", "summary": dict(artifact.get("summary", {}) or {})})


__all__ = ["LightBlockKernel", "geometry_document_from_artifact"]
