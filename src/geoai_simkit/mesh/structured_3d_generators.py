from __future__ import annotations

"""Dependency-light structured 3D mesh generators.

These plugins provide deterministic Hex8/Tet4 solid meshes for verified 3D
analysis, examples and fallback workflows.  They do not require Gmsh or meshio.
"""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.contracts import MeshRequest, MeshResult, PluginCapability, PluginHealth
from geoai_simkit.mesh.complete_3d import apply_3d_boundary_tags
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.solid_readiness import validate_solid_analysis_readiness


def _current_mesh(project: Any) -> MeshDocument | None:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    return mesh if isinstance(mesh, MeshDocument) else None


def _bounds_from_mesh(mesh: MeshDocument | None) -> tuple[float, float, float, float, float, float]:
    if mesh is None or not mesh.nodes:
        return (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    xs = [float(p[0]) for p in mesh.nodes]
    ys = [float(p[1]) for p in mesh.nodes]
    zs = [float(p[2]) for p in mesh.nodes]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _parse_bounds(options: dict[str, Any], project: Any) -> tuple[float, float, float, float, float, float]:
    value = options.get("bounds")
    if isinstance(value, dict):
        return (
            float(value.get("xmin", 0.0)),
            float(value.get("xmax", 1.0)),
            float(value.get("ymin", 0.0)),
            float(value.get("ymax", 1.0)),
            float(value.get("zmin", 0.0)),
            float(value.get("zmax", 1.0)),
        )
    if isinstance(value, (list, tuple)) and len(value) >= 6:
        return tuple(float(v) for v in value[:6])  # type: ignore[return-value]
    return _bounds_from_mesh(_current_mesh(project))


def _parse_dims(options: dict[str, Any]) -> tuple[int, int, int]:
    if "dims" in options:
        vals = tuple(int(v) for v in (options.get("dims") or (1, 1, 1)))
        if len(vals) >= 3:
            return (max(1, vals[0]), max(1, vals[1]), max(1, vals[2]))
    if "subdivisions" in options:
        n = max(1, int(options.get("subdivisions") or 1))
        return (n, n, n)
    return (
        max(1, int(options.get("nx", 1) or 1)),
        max(1, int(options.get("ny", 1) or 1)),
        max(1, int(options.get("nz", 1) or 1)),
    )


def _positive_bounds(bounds: tuple[float, float, float, float, float, float], dims: tuple[int, int, int]) -> tuple[float, float, float, float, float, float]:
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    nx, ny, nz = dims
    if xmax <= xmin:
        xmax = xmin + float(nx)
    if ymax <= ymin:
        ymax = ymin + float(ny)
    if zmax <= zmin:
        zmax = zmin + float(nz)
    return (xmin, xmax, ymin, ymax, zmin, zmax)


def _structured_hex8_mesh(
    *,
    bounds: tuple[float, float, float, float, float, float],
    dims: tuple[int, int, int],
    mesh_kind: str,
    block_id: str,
    region_name: str,
    material_id: str,
    metadata: dict[str, Any],
) -> MeshDocument:
    xmin, xmax, ymin, ymax, zmin, zmax = _positive_bounds(bounds, dims)
    nx, ny, nz = dims
    nodes: list[tuple[float, float, float]] = []
    for k in range(nz + 1):
        z = zmin + (zmax - zmin) * k / nz
        for j in range(ny + 1):
            y = ymin + (ymax - ymin) * j / ny
            for i in range(nx + 1):
                x = xmin + (xmax - xmin) * i / nx
                nodes.append((float(x), float(y), float(z)))

    def nid(i: int, j: int, k: int) -> int:
        return k * (ny + 1) * (nx + 1) + j * (nx + 1) + i

    cells: list[tuple[int, ...]] = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                cells.append((
                    nid(i, j, k),
                    nid(i + 1, j, k),
                    nid(i + 1, j + 1, k),
                    nid(i, j + 1, k),
                    nid(i, j, k + 1),
                    nid(i + 1, j, k + 1),
                    nid(i + 1, j + 1, k + 1),
                    nid(i, j + 1, k + 1),
                ))
    count = len(cells)
    mesh = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=["hex8"] * count,
        cell_tags={
            "block_id": [block_id] * count,
            "region_name": [region_name] * count,
            "role": ["solid_volume"] * count,
            "material_id": [material_id] * count,
        },
        quality=MeshQualityReport(min_quality=1.0, max_aspect_ratio=max((xmax - xmin) / nx, (ymax - ymin) / ny, (zmax - zmin) / nz) / max(min((xmax - xmin) / nx, (ymax - ymin) / ny, (zmax - zmin) / nz), 1.0e-30)),
        metadata={
            "source": "structured_3d_generator",
            "mesh_kind": mesh_kind,
            "mesh_role": "solid_volume",
            "mesh_dimension": 3,
            "solid_solver_ready": True,
            "requires_volume_meshing": False,
            "cell_families": ["hex8"],
            "bounds": [xmin, xmax, ymin, ymax, zmin, zmax],
            "dims": [nx, ny, nz],
            **metadata,
        },
    )
    apply_3d_boundary_tags(mesh)
    return mesh


def _split_hexes_to_tets(hex_mesh: MeshDocument, *, mesh_kind: str, metadata: dict[str, Any]) -> MeshDocument:
    tet_pattern = ((0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6), (3, 4, 6, 7), (1, 3, 4, 6))
    cells: list[tuple[int, ...]] = []
    source_hex_ids: list[int] = []
    block_ids: list[str] = []
    region_names: list[str] = []
    material_ids: list[str] = []
    hex_blocks = list(hex_mesh.cell_tags.get("block_id") or [])
    hex_regions = list(hex_mesh.cell_tags.get("region_name") or [])
    hex_materials = list(hex_mesh.cell_tags.get("material_id") or [])
    for hid, hcell in enumerate(hex_mesh.cells):
        if len(hcell) < 8:
            continue
        for pattern in tet_pattern:
            cells.append(tuple(int(hcell[i]) for i in pattern))
            source_hex_ids.append(hid)
            block_ids.append(str(hex_blocks[hid]) if hid < len(hex_blocks) else "structured_volume")
            region_names.append(str(hex_regions[hid]) if hid < len(hex_regions) else block_ids[-1])
            material_ids.append(str(hex_materials[hid]) if hid < len(hex_materials) else "default_solid")
    mesh = MeshDocument(
        nodes=list(hex_mesh.nodes),
        cells=cells,
        cell_types=["tet4"] * len(cells),
        cell_tags={
            "block_id": block_ids,
            "region_name": region_names,
            "role": ["solid_volume"] * len(cells),
            "material_id": material_ids,
            "source_hex_id": source_hex_ids,
        },
        quality=MeshQualityReport(min_quality=1.0, warnings=["Structured Tet4 mesh generated by deterministic Hex8 subdivision."]),
        metadata={
            **dict(hex_mesh.metadata),
            **metadata,
            "mesh_kind": mesh_kind,
            "cell_families": ["tet4"],
            "source_hex_cell_count": int(hex_mesh.cell_count),
        },
    )
    apply_3d_boundary_tags(mesh)
    return mesh


def _attach(project: Any, mesh: MeshDocument, *, element_family: str, mesh_kind: str) -> None:
    if hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
        project.mesh_model.mesh_settings.element_family = element_family
        project.mesh_model.mesh_settings.metadata["solid_solver_ready"] = True
        project.mesh_model.mesh_settings.metadata["volume_mesher"] = mesh_kind
        project.mesh_model.attach_mesh(mesh)


class StructuredHex8BoxMeshGenerator:
    key = "structured_hex8_box"
    label = "Structured Hex8 box volume mesher"
    supported_mesh_kinds = ("structured_hex8_box", "hex8_box", "box_hex8")
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="mesh_generator",
        version="1",
        features=("3d_volume", "hex8", "boundary_faces", "dependency_light", "solver_ready"),
        supported_inputs=("bounds", "ProjectWritePort", "optional surface bounds"),
        supported_outputs=("MeshDocument:solid_volume", "3D boundary face tags"),
        health=PluginHealth(available=True),
        metadata={"mesh_kinds": supported_mesh_kinds, "contract": "structured_hex8_box_generator_v1"},
    )

    def can_generate(self, request: MeshRequest) -> bool:
        return str(request.mesh_kind or "") in self.supported_mesh_kinds

    def generate(self, request: MeshRequest) -> MeshResult:
        project = request.project_document()
        options = dict(request.options or {})
        bounds = _parse_bounds(options, project)
        dims = _parse_dims(options)
        mesh = _structured_hex8_mesh(
            bounds=bounds,
            dims=dims,
            mesh_kind=self.key,
            block_id=str(options.get("block_id") or "structured_volume"),
            region_name=str(options.get("region_name") or options.get("block_id") or "structured_volume"),
            material_id=str(options.get("material_id") or "default_solid"),
            metadata={"complete_3d_mesh_capability": True, **dict(request.metadata)},
        )
        if bool(request.attach):
            _attach(project, mesh, element_family="hex8", mesh_kind=self.key)
        return MeshResult(mesh=mesh, mesh_kind=self.key, attached=bool(request.attach), quality=mesh.quality, metadata={"solid_readiness": validate_solid_analysis_readiness(mesh).to_dict(), "complete_3d_mesh": True, **dict(request.metadata)})


class StructuredTet4BoxMeshGenerator:
    key = "structured_tet4_box"
    label = "Structured Tet4 box volume mesher"
    supported_mesh_kinds = ("structured_tet4_box", "tet4_box", "box_tet4")
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="mesh_generator",
        version="1",
        features=("3d_volume", "tet4", "hex_to_tet_subdivision", "boundary_faces", "dependency_light", "solver_ready"),
        supported_inputs=("bounds", "ProjectWritePort", "optional surface bounds"),
        supported_outputs=("MeshDocument:solid_volume", "3D boundary face tags"),
        health=PluginHealth(available=True),
        metadata={"mesh_kinds": supported_mesh_kinds, "contract": "structured_tet4_box_generator_v1"},
    )

    def can_generate(self, request: MeshRequest) -> bool:
        return str(request.mesh_kind or "") in self.supported_mesh_kinds

    def generate(self, request: MeshRequest) -> MeshResult:
        project = request.project_document()
        options = dict(request.options or {})
        bounds = _parse_bounds(options, project)
        dims = _parse_dims(options)
        hex_mesh = _structured_hex8_mesh(
            bounds=bounds,
            dims=dims,
            mesh_kind="structured_hex8_intermediate",
            block_id=str(options.get("block_id") or "structured_volume"),
            region_name=str(options.get("region_name") or options.get("block_id") or "structured_volume"),
            material_id=str(options.get("material_id") or "default_solid"),
            metadata={"intermediate_for": self.key, **dict(request.metadata)},
        )
        mesh = _split_hexes_to_tets(hex_mesh, mesh_kind=self.key, metadata={"complete_3d_mesh_capability": True, **dict(request.metadata)})
        if bool(request.attach):
            _attach(project, mesh, element_family="tet4", mesh_kind=self.key)
        return MeshResult(mesh=mesh, mesh_kind=self.key, attached=bool(request.attach), quality=mesh.quality, warnings=tuple(mesh.quality.warnings), metadata={"solid_readiness": validate_solid_analysis_readiness(mesh).to_dict(), "complete_3d_mesh": True, **dict(request.metadata)})


__all__ = ["StructuredHex8BoxMeshGenerator", "StructuredTet4BoxMeshGenerator"]
