from __future__ import annotations

"""Dependency-light production mesh promotion utilities for 1.0 workflows.

The service does not claim to replace Gmsh/OCC for arbitrary geometry.  It
creates a conforming shared-node Hex8 volume mesh for axis-aligned GeoProject
volumes, tags material/region ownership, computes basic quality metrics and
marks the mesh as suitable for the baseline 1.0 linear-static staged workflow.
"""

from dataclasses import dataclass, field
from math import dist
from typing import Any

from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap


@dataclass(slots=True)
class ProductionMeshBuildReport:
    contract: str = "geoai_simkit_production_hex8_mesh_v1"
    ok: bool = False
    mesher: str = "shared_node_axis_aligned_hex8"
    node_count: int = 0
    cell_count: int = 0
    region_count: int = 0
    min_quality: float | None = None
    max_aspect_ratio: float | None = None
    bad_cell_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "mesher": self.mesher,
            "node_count": int(self.node_count),
            "cell_count": int(self.cell_count),
            "region_count": int(self.region_count),
            "min_quality": self.min_quality,
            "max_aspect_ratio": self.max_aspect_ratio,
            "bad_cell_ids": list(self.bad_cell_ids),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def _hex_aspect(nodes: list[tuple[float, float, float]], conn: list[int]) -> float:
    lengths: list[float] = []
    for i, a_id in enumerate(conn):
        a = nodes[int(a_id)]
        for b_id in conn[i + 1 :]:
            value = float(dist(a, nodes[int(b_id)]))
            if value > 0.0:
                lengths.append(value)
    if not lengths:
        return float("inf")
    return max(lengths) / max(min(lengths), 1.0e-30)


def _bounds_volume(bounds: tuple[float, float, float, float, float, float]) -> float:
    xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in bounds]
    return abs((xmax - xmin) * (ymax - ymin) * (zmax - zmin))


def generate_shared_node_hex8_mesh(
    project: Any,
    *,
    attach: bool = True,
    min_volume: float = 1.0e-12,
    max_aspect_ratio: float = 100.0,
    coordinate_digits: int = 9,
) -> tuple[MeshDocument, ProductionMeshBuildReport]:
    """Create a tagged shared-node Hex8 mesh from axis-aligned project volumes.

    Coincident vertices are deduplicated across volumes.  This is important for
    staged construction, because active regions then remain connected as volumes
    are deactivated and the phase compiler can safely compact inactive nodes.
    """

    nodes: list[tuple[float, float, float]] = []
    node_index: dict[tuple[float, float, float], int] = {}
    cells: list[tuple[int, ...]] = []
    block_tags: list[str] = []
    material_tags: list[str] = []
    region_tags: list[str] = []
    block_to_cells: dict[str, list[int]] = {}
    warnings: list[str] = []
    bad_cell_ids: list[int] = []
    aspects: list[float] = []
    qualities: list[float] = []

    volumes = list(getattr(getattr(project, "geometry_model", None), "volumes", {}).values())
    for volume in volumes:
        bounds = getattr(volume, "bounds", None)
        if bounds is None:
            warnings.append(f"volume {getattr(volume, 'id', '?')} has no bounds and was skipped")
            continue
        xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in bounds]
        coords = [
            (xmin, ymin, zmin),
            (xmax, ymin, zmin),
            (xmax, ymax, zmin),
            (xmin, ymax, zmin),
            (xmin, ymin, zmax),
            (xmax, ymin, zmax),
            (xmax, ymax, zmax),
            (xmin, ymax, zmax),
        ]
        conn: list[int] = []
        for xyz in coords:
            key = tuple(round(float(v), int(coordinate_digits)) for v in xyz)
            if key not in node_index:
                node_index[key] = len(nodes)
                nodes.append(tuple(float(v) for v in xyz))
            conn.append(node_index[key])
        cell_id = len(cells)
        cells.append(tuple(conn))
        block_id = str(getattr(volume, "id", f"volume_{cell_id:04d}"))
        material_id = str(getattr(volume, "material_id", "") or "")
        block_tags.append(block_id)
        material_tags.append(material_id)
        region_tags.append(block_id)
        block_to_cells.setdefault(block_id, []).append(cell_id)
        aspect = _hex_aspect(nodes, conn)
        volume_value = _bounds_volume(tuple(float(v) for v in bounds))
        aspects.append(float(aspect))
        quality = 0.0 if aspect <= 0.0 or aspect == float("inf") else 1.0 / float(aspect)
        qualities.append(float(quality))
        if volume_value <= min_volume or aspect > max_aspect_ratio:
            bad_cell_ids.append(cell_id)

    mesh = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=["hex8"] * len(cells),
        cell_tags={"block_id": block_tags, "region_name": region_tags, "material_id": material_tags},
        entity_map=MeshEntityMap(block_to_cells=block_to_cells, metadata={"source": "generate_shared_node_hex8_mesh"}),
        quality=MeshQualityReport(
            min_quality=min(qualities) if qualities else None,
            max_aspect_ratio=max(aspects) if aspects else None,
            bad_cell_ids=list(bad_cell_ids),
            warnings=list(warnings),
        ),
        metadata={
            "mesher": "shared_node_axis_aligned_hex8",
            "mesh_role": "solid_volume",
            "mesh_dimension": 3,
            "production_ready": not bad_cell_ids and bool(cells),
            "preview": False,
            "release_gate": "1.0_basic_engineering",
        },
    )
    report = ProductionMeshBuildReport(
        ok=bool(cells) and not bad_cell_ids,
        node_count=mesh.node_count,
        cell_count=mesh.cell_count,
        region_count=len(block_to_cells),
        min_quality=mesh.quality.min_quality,
        max_aspect_ratio=mesh.quality.max_aspect_ratio,
        bad_cell_ids=list(bad_cell_ids),
        warnings=list(warnings),
        metadata={"min_volume": float(min_volume), "max_aspect_ratio": float(max_aspect_ratio), "deduplicated_node_count": len(nodes)},
    )
    if attach:
        project.mesh_model.attach_mesh(mesh)
        project.mesh_model.metadata["last_production_mesh_build"] = report.to_dict()
        if hasattr(project, "mark_changed"):
            project.mark_changed(["mesh"], action="generate_shared_node_hex8_mesh", affected_entities=list(block_to_cells))
    return mesh, report


__all__ = ["ProductionMeshBuildReport", "generate_shared_node_hex8_mesh"]

@dataclass(slots=True)
class GmshOccMeshRouteReport:
    contract: str = "geoai_simkit_gmsh_occ_mesh_route_v1"
    ok: bool = False
    selected_backend: str = "shared_node_axis_aligned_hex8"
    requested_backend: str = "gmsh_occ_tet4"
    gmsh_available: bool = False
    occ_fragmentation_enabled: bool = True
    fallback_used: bool = True
    fallback_reason: str = ""
    mesh_report: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "selected_backend": self.selected_backend,
            "requested_backend": self.requested_backend,
            "gmsh_available": bool(self.gmsh_available),
            "occ_fragmentation_enabled": bool(self.occ_fragmentation_enabled),
            "fallback_used": bool(self.fallback_used),
            "fallback_reason": self.fallback_reason,
            "mesh_report": dict(self.mesh_report),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def _gmsh_available_safely() -> bool:
    try:
        from geoai_simkit.geometry.gmsh_mesher import GmshMesher

        return bool(GmshMesher.available())
    except Exception:
        return False


def generate_gmsh_occ_or_shared_hex8_mesh(
    project: Any,
    *,
    attach: bool = True,
    require_gmsh: bool = False,
    element_size: float | None = None,
) -> tuple[MeshDocument, GmshOccMeshRouteReport]:
    """Select the 1.0.5 production meshing route.

    In a desktop installation with Gmsh/OCC available this route records the
    intended backend policy.  In CI/headless environments where Gmsh is missing,
    it falls back to the deterministic shared-node Hex8 production mesh and
    records the fallback explicitly so acceptance and reports do not confuse it
    with a Gmsh-generated tetrahedral mesh.
    """

    gmsh_available = _gmsh_available_safely()
    warnings: list[str] = []
    if gmsh_available:
        fallback_reason = "geoproject_to_occ_tet4_adapter_not_enabled_in_basic_build"
        warnings.append("Gmsh is available, but this lightweight 1.0.5 package uses the audited shared-node Hex8 production fallback for GeoProjectDocument volumes.")
    else:
        fallback_reason = "gmsh_or_meshio_runtime_unavailable"
        warnings.append("Gmsh/OCC runtime is unavailable; using audited shared-node Hex8 production fallback.")
    if require_gmsh and not gmsh_available:
        raise RuntimeError("Gmsh/OCC meshing was required but is not available in this environment.")
    mesh, base_report = generate_shared_node_hex8_mesh(project, attach=attach)
    mesh.metadata.update(
        {
            "meshing_policy": "gmsh_occ_preferred_with_shared_hex8_fallback",
            "requested_backend": "gmsh_occ_tet4",
            "selected_backend": "shared_node_axis_aligned_hex8",
            "gmsh_available": bool(gmsh_available),
            "fallback_used": True,
            "fallback_reason": fallback_reason,
            "release_gate": "1.0.5_basic_engineering",
        }
    )
    report = GmshOccMeshRouteReport(
        ok=bool(base_report.ok),
        gmsh_available=bool(gmsh_available),
        fallback_used=True,
        fallback_reason=fallback_reason,
        mesh_report=base_report.to_dict(),
        warnings=warnings,
        metadata={"element_size": element_size, "node_count": mesh.node_count, "cell_count": mesh.cell_count},
    )
    if attach:
        project.mesh_model.attach_mesh(mesh)
        project.mesh_model.metadata["last_gmsh_occ_mesh_route"] = report.to_dict()
        if hasattr(project, "mark_changed"):
            project.mark_changed(["mesh"], action="generate_gmsh_occ_or_shared_hex8_mesh", affected_entities=list(mesh.entity_map.block_to_cells))
    return mesh, report


__all__.extend(["GmshOccMeshRouteReport", "generate_gmsh_occ_or_shared_hex8_mesh"])
