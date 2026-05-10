from __future__ import annotations

"""Small tagged block mesher for workflow smoke and GUI previews."""

from geoai_simkit.geometry.kernel import GeometryDocument
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap


def _box_nodes(bounds: tuple[float, float, float, float, float, float]) -> list[tuple[float, float, float]]:
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    return [
        (xmin, ymin, zmin),
        (xmax, ymin, zmin),
        (xmax, ymax, zmin),
        (xmin, ymax, zmin),
        (xmin, ymin, zmax),
        (xmax, ymin, zmax),
        (xmax, ymax, zmax),
        (xmin, ymax, zmax),
    ]


def generate_tagged_preview_mesh(geometry: GeometryDocument) -> MeshDocument:
    """Generate one hex-like cell per block while preserving engineering tags.

    This is not a production mesher. It is the dependency-light handoff that lets
    GUI, tests and the command pipeline verify block/face/stage semantics before
    Gmsh/OCC/VTK are available.
    """
    nodes: list[tuple[float, float, float]] = []
    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    block_id_tags: list[str] = []
    role_tags: list[str] = []
    material_tags: list[str] = []
    layer_tags: list[str] = []
    active_stage_tags: list[str] = []
    block_to_cells: dict[str, list[int]] = {}
    face_to_faces: dict[str, list[int]] = {}
    for block_id, block in geometry.blocks.items():
        start = len(nodes)
        nodes.extend(_box_nodes(block.bounds))
        cell_id = len(cells)
        cells.append(tuple(range(start, start + 8)))
        cell_types.append("hex8_preview")
        block_id_tags.append(block_id)
        role_tags.append(block.role)
        material_tags.append(block.material_id or "")
        layer_tags.append(block.layer_id or "")
        active_stage_tags.append("|".join(block.active_stage_ids))
        block_to_cells.setdefault(block_id, []).append(cell_id)
        for face_id in block.face_ids:
            face_to_faces.setdefault(face_id, []).append(cell_id)
    return MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=cell_types,
        cell_tags={
            "block_id": block_id_tags,
            "role": role_tags,
            "material_id": material_tags,
            "layer_id": layer_tags,
            "active_stages": active_stage_tags,
        },
        entity_map=MeshEntityMap(block_to_cells=block_to_cells, face_to_faces=face_to_faces, metadata={"source": "tagged_preview_mesher"}),
        quality=MeshQualityReport(min_quality=1.0, max_aspect_ratio=None, warnings=["preview mesh: one cell per block"]),
        metadata={"mesher": "tagged_preview_mesher", "preserves_block_tag": True, "preserves_face_tag": True},
    )


__all__ = ["generate_tagged_preview_mesh"]
