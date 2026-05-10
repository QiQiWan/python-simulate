from __future__ import annotations

"""STL-surface to 3D volume mesh generator plugins."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.contracts import MeshRequest, MeshResult, PluginCapability, PluginDependencyStatus, PluginHealth
from geoai_simkit.geometry.gmsh_mesher import GmshMesher
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.solid_readiness import validate_solid_analysis_readiness
from geoai_simkit.mesh.multi_region_stl import deterministic_conformal_tet4_from_closed_regions, diagnose_multi_stl_closure


def _surface_mesh_from_project(project: Any) -> MeshDocument | None:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    if isinstance(mesh, MeshDocument):
        return mesh
    return None


def _primary_block_id(mesh: MeshDocument, fallback: str = "imported_volume") -> str:
    block_ids = mesh.cell_tags.get("block_id", []) if mesh is not None else []
    return str(block_ids[0]) if block_ids else fallback


def _bounds(mesh: MeshDocument) -> tuple[float, float, float, float, float, float]:
    xs = [float(row[0]) for row in mesh.nodes]
    ys = [float(row[1]) for row in mesh.nodes]
    zs = [float(row[2]) for row in mesh.nodes]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _positive_span(a: float, b: float) -> float:
    return max(float(b) - float(a), 1.0)


def _structured_hex_mesh_from_bounds(surface: MeshDocument, *, dims: tuple[int, int, int], mesher_key: str, request_metadata: dict[str, Any]) -> MeshDocument:
    xmin, xmax, ymin, ymax, zmin, zmax = _bounds(surface)
    nx, ny, nz = [max(1, int(v)) for v in dims]
    dx = _positive_span(xmin, xmax) / nx
    dy = _positive_span(ymin, ymax) / ny
    dz = _positive_span(zmin, zmax) / nz
    if xmax <= xmin:
        xmax = xmin + dx * nx
    if ymax <= ymin:
        ymax = ymin + dy * ny
    if zmax <= zmin:
        zmax = zmin + dz * nz

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

    block_id = _primary_block_id(surface)
    count = len(cells)
    return MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=["hex8"] * count,
        cell_tags={
            "block_id": [block_id] * count,
            "region_name": [block_id] * count,
            "role": ["solid_volume"] * count,
            "material_id": list(surface.cell_tags.get("material_id", ["imported_geology"] * max(1, count)))[:1] * count,
        },
        face_tags={
            "boundary_sets": ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"],
        },
        quality=MeshQualityReport(min_quality=1.0, warnings=["Voxel Hex8 mesh is a bounding-box approximation of the STL surface; use gmsh_tet4_from_stl for conformal meshing when available."]),
        metadata={
            "source": "stl_volume_mesher",
            "source_mesh_role": surface.metadata.get("mesh_role", "geometry_surface"),
            "source_surface_cell_count": int(surface.cell_count),
            "mesh_kind": mesher_key,
            "mesh_role": "solid_volume",
            "mesh_dimension": 3,
            "solid_solver_ready": True,
            "requires_volume_meshing": False,
            "cell_families": ["hex8"],
            "bounds": [xmin, xmax, ymin, ymax, zmin, zmax],
            "dims": [nx, ny, nz],
            **dict(request_metadata),
        },
    )


def _single_tet_from_tetra_surface(surface: MeshDocument, *, mesher_key: str, request_metadata: dict[str, Any]) -> MeshDocument | None:
    if int(surface.node_count) != 4:
        return None
    cell_types = {str(item).lower() for item in list(surface.cell_types or [])}
    if cell_types != {"tri3"} or int(surface.cell_count) < 4:
        return None
    block_id = _primary_block_id(surface)
    material_id = str((surface.cell_tags.get("material_id", []) or ["imported_geology"])[0])
    return MeshDocument(
        nodes=list(surface.nodes),
        cells=[(0, 1, 2, 3)],
        cell_types=["tet4"],
        cell_tags={"block_id": [block_id], "region_name": [block_id], "role": ["solid_volume"], "material_id": [material_id]},
        quality=MeshQualityReport(min_quality=1.0, warnings=["Generated a single Tet4 cell from a closed tetrahedral STL surface."]),
        metadata={
            "source": "stl_volume_mesher",
            "source_surface_cell_count": int(surface.cell_count),
            "mesh_kind": mesher_key,
            "mesh_role": "solid_volume",
            "mesh_dimension": 3,
            "solid_solver_ready": True,
            "requires_volume_meshing": False,
            "cell_families": ["tet4"],
            **dict(request_metadata),
        },
    )


class VoxelHex8FromSTLMeshGenerator:
    key = "voxel_hex8_from_stl"
    label = "Dependency-light STL bounding-box Hex8 volume mesher"
    supported_mesh_kinds = ("auto", "voxel_hex8_from_stl", "stl_voxel_hex8", "hex8_from_stl")
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="mesh_generator",
        version="1",
        features=("stl_surface_to_volume", "hex8", "dependency_light", "solid_readiness"),
        supported_inputs=("STL surface MeshDocument", "ProjectWritePort"),
        supported_outputs=("MeshDocument:solid_volume",),
        health=PluginHealth(available=True),
        metadata={"mesh_kinds": supported_mesh_kinds, "conformity": "bounding_box_approximation"},
    )

    def can_generate(self, request: MeshRequest) -> bool:
        kind = str(request.mesh_kind or "auto")
        if kind not in self.supported_mesh_kinds:
            return False
        mesh = _surface_mesh_from_project(request.project_document())
        if mesh is None:
            return False
        readiness = validate_solid_analysis_readiness(mesh)
        return bool(readiness.surface_cell_count and not readiness.solid_cell_count)

    def generate(self, request: MeshRequest) -> MeshResult:
        project = request.project_document()
        surface = _surface_mesh_from_project(project)
        if surface is None:
            raise ValueError("voxel_hex8_from_stl requires an attached STL surface MeshDocument.")
        options = dict(request.options or {})
        if "dims" in options:
            dims_value = tuple(int(v) for v in options.get("dims") or (1, 1, 1))
        else:
            subdivisions = int(options.get("subdivisions", 1) or 1)
            dims_value = (subdivisions, subdivisions, subdivisions)
        mesh = _structured_hex_mesh_from_bounds(surface, dims=dims_value, mesher_key=self.key, request_metadata=dict(request.metadata))
        if bool(request.attach) and hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.mesh_settings.element_family = "hex8"
            project.mesh_model.mesh_settings.metadata["solid_solver_ready"] = True
            project.mesh_model.mesh_settings.metadata["volume_mesher"] = self.key
            project.mesh_model.attach_mesh(mesh)
            try:
                from geoai_simkit.solver.contact_readiness import materialize_interface_candidates
                project.mesh_model.metadata["interface_materialization"] = materialize_interface_candidates(project, mesh.face_tags.get("interface_candidates", []))
            except Exception as exc:  # pragma: no cover
                project.mesh_model.metadata["interface_materialization"] = {"ok": False, "error": str(exc)}
        return MeshResult(mesh=mesh, mesh_kind=self.key, attached=bool(request.attach), quality=mesh.quality, warnings=tuple(mesh.quality.warnings), metadata={"solid_readiness": validate_solid_analysis_readiness(mesh).to_dict(), **dict(request.metadata)})


class GmshTet4FromSTLMeshGenerator:
    key = "gmsh_tet4_from_stl"
    label = "Gmsh STL Tet4 volume mesher"
    supported_mesh_kinds = ("gmsh_tet4_from_stl", "stl_gmsh_tet4", "tet4_from_stl")

    @property
    def capabilities(self) -> PluginCapability:
        available = bool(GmshMesher.available())
        dependencies = () if available else (PluginDependencyStatus(name="gmsh/meshio", available=False, detail="Install gmsh and meshio for conformal Tet4 STL volume meshing."),)
        return PluginCapability(
            key=self.key,
            label=self.label,
            category="mesh_generator",
            version="1",
            features=("stl_surface_to_volume", "tet4", "gmsh_optional", "solid_readiness"),
            supported_inputs=("closed STL surface MeshDocument", "ProjectWritePort"),
            supported_outputs=("MeshDocument:solid_volume",),
            health=PluginHealth(available=available, status="available" if available else "missing_optional_dependency", diagnostics=() if available else ("gmsh/meshio unavailable; tetra STL heuristic fallback remains available for simple tetrahedra.",), dependencies=dependencies),
            metadata={"mesh_kinds": self.supported_mesh_kinds},
        )

    def can_generate(self, request: MeshRequest) -> bool:
        kind = str(request.mesh_kind or "")
        if kind not in self.supported_mesh_kinds:
            return False
        mesh = _surface_mesh_from_project(request.project_document())
        return mesh is not None and bool(validate_solid_analysis_readiness(mesh).surface_cell_count)

    def generate(self, request: MeshRequest) -> MeshResult:
        project = request.project_document()
        surface = _surface_mesh_from_project(project)
        if surface is None:
            raise ValueError("gmsh_tet4_from_stl requires an attached STL surface MeshDocument.")
        # Dependency-light deterministic path for tetrahedral STL smoke tests.
        tet = _single_tet_from_tetra_surface(surface, mesher_key=self.key, request_metadata=dict(request.metadata))
        warnings: list[str] = []
        if tet is None:
            # Keep this plugin as a safe gate in minimal environments.  The legacy
            # GmshMesher remains available for GUI/pipeline paths with optional deps.
            raise RuntimeError("gmsh_tet4_from_stl requires gmsh/meshio for general STL geometry. Simple tetra STL fallback was not applicable.")
        warnings.extend(list(tet.quality.warnings))
        if bool(request.attach) and hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.mesh_settings.element_family = "tet4"
            project.mesh_model.mesh_settings.metadata["solid_solver_ready"] = True
            project.mesh_model.mesh_settings.metadata["volume_mesher"] = self.key
            project.mesh_model.attach_mesh(tet)
        return MeshResult(mesh=tet, mesh_kind=self.key, attached=bool(request.attach), quality=tet.quality, warnings=tuple(warnings), metadata={"solid_readiness": validate_solid_analysis_readiness(tet).to_dict(), **dict(request.metadata)})


class ConformalTet4FromSTLRegionsMeshGenerator:
    key = "conformal_tet4_from_stl_regions"
    label = "Multi-STL conformal Tet4 geological volume mesher"
    supported_mesh_kinds = ("conformal_tet4_from_stl_regions", "multi_stl_tet4", "stl_regions_tet4")

    @property
    def capabilities(self) -> PluginCapability:
        available = bool(GmshMesher.available())
        dependencies = () if available else (PluginDependencyStatus(name="gmsh/meshio", available=False, detail="Install gmsh and meshio for general high-quality conformal multi-STL Tet4 meshing; deterministic fallback supports simple closed tetra/cube shells."),)
        return PluginCapability(
            key=self.key,
            label=self.label,
            category="mesh_generator",
            version="1",
            features=("multi_stl", "closed_region_validation", "material_mapping", "conformal_tet4", "interface_candidates", "gmsh_optional"),
            supported_inputs=("closed STL region surface MeshDocument", "ProjectWritePort"),
            supported_outputs=("MeshDocument:solid_volume", "multi-region material cell_tags"),
            health=PluginHealth(available=True, status="fallback_available" if not available else "available", diagnostics=() if available else ("gmsh/meshio unavailable; complex STL shells will be rejected instead of approximated.",), dependencies=dependencies),
            metadata={"mesh_kinds": self.supported_mesh_kinds, "fallback": "simple_closed_tetra_or_cube_shells", "conformity": "deterministic fallback or external gmsh"},
        )

    def can_generate(self, request: MeshRequest) -> bool:
        kind = str(request.mesh_kind or "")
        if kind not in self.supported_mesh_kinds:
            return False
        mesh = _surface_mesh_from_project(request.project_document())
        return mesh is not None and bool(validate_solid_analysis_readiness(mesh).surface_cell_count)

    def generate(self, request: MeshRequest) -> MeshResult:
        project = request.project_document()
        surface = _surface_mesh_from_project(project)
        if surface is None:
            raise ValueError("conformal_tet4_from_stl_regions requires an attached STL surface MeshDocument.")
        closure = diagnose_multi_stl_closure(surface)
        if not closure.ready:
            raise RuntimeError("Multi-STL conformal Tet4 meshing requires closed manifold region shells. " + str(closure.to_dict()))
        mesh = deterministic_conformal_tet4_from_closed_regions(surface)
        if mesh is None:
            if not GmshMesher.available():
                raise RuntimeError("Complex conformal Tet4 meshing requires gmsh/meshio. Deterministic fallback only supports simple closed tetra/cube shells.")
            raise RuntimeError("Gmsh-backed conformal multi-STL meshing is available in this installation but the dependency-light adapter path is not configured for direct project MeshDocument conversion yet.")
        mesh.metadata.update({"mesh_kind": self.key, "closure_report": closure.to_dict(), **dict(request.metadata)})
        if bool(request.attach) and hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.mesh_settings.element_family = "tet4"
            project.mesh_model.mesh_settings.conformal_blocks = True
            project.mesh_model.mesh_settings.preserve_interfaces = True
            project.mesh_model.mesh_settings.metadata["solid_solver_ready"] = True
            project.mesh_model.mesh_settings.metadata["volume_mesher"] = self.key
            project.mesh_model.mesh_settings.metadata["multi_region_material_mapping"] = True
            project.mesh_model.attach_mesh(mesh)
            try:
                from geoai_simkit.solver.contact_readiness import materialize_interface_candidates
                project.mesh_model.metadata["interface_materialization"] = materialize_interface_candidates(project, mesh.face_tags.get("interface_candidates", []))
            except Exception as exc:  # pragma: no cover
                project.mesh_model.metadata["interface_materialization"] = {"ok": False, "error": str(exc)}
        return MeshResult(mesh=mesh, mesh_kind=self.key, attached=bool(request.attach), quality=mesh.quality, warnings=tuple(mesh.quality.warnings), metadata={"solid_readiness": validate_solid_analysis_readiness(mesh).to_dict(), "closure_report": closure.to_dict(), **dict(request.metadata)})


__all__ = ["ConformalTet4FromSTLRegionsMeshGenerator", "GmshTet4FromSTLMeshGenerator", "VoxelHex8FromSTLMeshGenerator"]
