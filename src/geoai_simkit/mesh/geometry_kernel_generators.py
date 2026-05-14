from __future__ import annotations

"""Mesh-generator plugins backed by the strengthened geometry-kernel service."""

from geoai_simkit.contracts import MeshRequest, MeshResult, PluginCapability, PluginDependencyStatus, PluginHealth
from geoai_simkit.mesh.solid_readiness import validate_solid_analysis_readiness
from geoai_simkit.mesh.geometry_kernel_core import build_soil_layer_volume_mesh, geometry_kernel_dependency_status, optimize_stl_surface_mesh


class SoilLayeredVolumeFromSTLMeshGenerator:
    key = "soil_layered_volume_from_stl"
    label = "Soil-layer split volume mesher from STL bounds"
    supported_mesh_kinds = ("soil_layered_volume_from_stl", "stl_soil_layers", "layered_hex8_from_stl", "layered_tet4_from_stl")

    @property
    def capabilities(self) -> PluginCapability:
        deps = geometry_kernel_dependency_status()
        dependency_rows = () if deps.production_tet4_available else (
            PluginDependencyStatus(name="gmsh/meshio", available=False, detail="Optional only. Install gmsh and meshio for production conformal Tet4; dependency-light soil-layer cutting remains available."),
        )
        return PluginCapability(
            key=self.key,
            label=self.label,
            category="mesh_generator",
            version="1",
            features=("stl_surface_to_volume", "soil_layer_cutting", "hex8", "tet4", "material_mapping", "interface_candidates", "dependency_light_fallback"),
            supported_inputs=("STL surface MeshDocument", "soil layer definitions", "ProjectWritePort"),
            supported_outputs=("MeshDocument:solid_volume",),
            health=PluginHealth(available=True, status="available", dependencies=dependency_rows, diagnostics=tuple(deps.diagnostics)),
            metadata={"mesh_kinds": self.supported_mesh_kinds, "production_tet4_available": deps.production_tet4_available},
        )

    def can_generate(self, request: MeshRequest) -> bool:
        kind = str(request.mesh_kind or "")
        if kind not in self.supported_mesh_kinds:
            return False
        project = request.project_document()
        mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
        return bool(mesh is not None and validate_solid_analysis_readiness(mesh).surface_cell_count)

    def generate(self, request: MeshRequest) -> MeshResult:
        project = request.project_document()
        options = dict(request.options or {})
        optimize_first = bool(options.get("optimize_stl", True))
        if optimize_first:
            optimize_stl_surface_mesh(project, tolerance=float(options.get("tolerance", 1.0e-9)), attach=True)
        dims = tuple(int(v) for v in (options.get("dims") or (1, 1)))
        if len(dims) < 2:
            dims = (int(dims[0]), int(dims[0]))
        element_family = str(options.get("element_family") or ("tet4" if str(request.mesh_kind) == "layered_tet4_from_stl" else "hex8"))
        mesh, report = build_soil_layer_volume_mesh(project, layers=tuple(options.get("layers") or ()), dims=(int(dims[0]), int(dims[1])), element_family=element_family, attach=bool(request.attach))
        if mesh is None:
            raise RuntimeError("soil_layered_volume_from_stl could not generate a volume mesh from the current STL surface.")
        return MeshResult(
            mesh=mesh,
            mesh_kind=self.key,
            attached=bool(request.attach),
            quality=mesh.quality,
            warnings=tuple(mesh.quality.warnings),
            metadata={"soil_layer_cut": report.to_dict(), "solid_readiness": validate_solid_analysis_readiness(mesh).to_dict(), **dict(request.metadata)},
        )


__all__ = ["SoilLayeredVolumeFromSTLMeshGenerator", "StratigraphicSurfaceVolumeFromSTLMeshGenerator"]


class StratigraphicSurfaceVolumeFromSTLMeshGenerator:
    key = "stratigraphic_surface_volume_from_stl"
    label = "Real stratigraphic-surface closure volume mesher"
    supported_mesh_kinds = (
        "stratigraphic_surface_volume_from_stl",
        "stl_stratigraphic_surfaces",
        "surface_layered_volume_from_stl",
        "surface_strata_tet4_from_stl",
        "surface_strata_hex8_from_stl",
    )

    @property
    def capabilities(self) -> PluginCapability:
        from geoai_simkit.mesh.geometry_kernel_core import geometry_kernel_dependency_status

        deps = geometry_kernel_dependency_status()
        dependency_rows = () if deps.production_tet4_available else (
            PluginDependencyStatus(name="gmsh/meshio", available=False, detail="Optional for CAD-grade conformal Tet4. Dependency-light surface-closure Hex8/Tet4 path remains available."),
        )
        return PluginCapability(
            key=self.key,
            label=self.label,
            category="mesh_generator",
            version="1",
            features=("real_stratigraphic_surfaces", "surface_closure", "physical_group_preservation", "hex8", "tet4", "material_mapping", "interface_candidates"),
            supported_inputs=("STL surface MeshDocument with surface_id/region tags", "surface layer definitions", "ProjectWritePort"),
            supported_outputs=("MeshDocument:solid_volume",),
            health=PluginHealth(available=True, status="available", dependencies=dependency_rows, diagnostics=tuple(deps.diagnostics)),
            metadata={"mesh_kinds": self.supported_mesh_kinds, "production_tet4_available": deps.production_tet4_available},
        )

    def can_generate(self, request: MeshRequest) -> bool:
        kind = str(request.mesh_kind or "")
        if kind not in self.supported_mesh_kinds:
            return False
        project = request.project_document()
        mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
        return bool(mesh is not None and validate_solid_analysis_readiness(mesh).surface_cell_count)

    def generate(self, request: MeshRequest) -> MeshResult:
        from geoai_simkit.mesh.geometry_kernel_core import build_stratigraphic_surface_volume_mesh, optimize_complex_stl_surface_mesh, optimize_volume_mesh_quality

        project = request.project_document()
        options = dict(request.options or {})
        if bool(options.get("optimize_stl", True)):
            optimize_complex_stl_surface_mesh(
                project,
                tolerance=float(options.get("tolerance", 1.0e-9)),
                fill_holes=bool(options.get("fill_holes", True)),
                orient_normals=bool(options.get("orient_normals", True)),
                attach=True,
            )
        dims_raw = tuple(int(v) for v in (options.get("dims") or (1, 1)))
        dims = (int(dims_raw[0]), int(dims_raw[1] if len(dims_raw) > 1 else dims_raw[0]))
        element_family = str(options.get("element_family") or ("tet4" if "tet4" in str(request.mesh_kind) else "hex8"))
        mesh, report = build_stratigraphic_surface_volume_mesh(
            project,
            layers=tuple(options.get("surface_layers") or options.get("layers") or ()),
            dims=dims,
            element_family=element_family,
            attach=bool(request.attach),
        )
        if mesh is None:
            raise RuntimeError("stratigraphic_surface_volume_from_stl could not generate a sealed volume mesh. " + str(report.to_dict()))
        if bool(options.get("quality_optimize", False)):
            mesh2, qreport = optimize_volume_mesh_quality(project if request.attach else mesh, min_volume=float(options.get("min_volume", 1.0e-12)), max_aspect_ratio=float(options.get("max_aspect_ratio", 1.0e6)), attach=bool(request.attach))
            if mesh2 is not None:
                mesh = mesh2
                mesh.metadata["mesh_quality_optimization"] = qreport.to_dict()
        return MeshResult(
            mesh=mesh,
            mesh_kind=self.key,
            attached=bool(request.attach),
            quality=mesh.quality,
            warnings=tuple(mesh.quality.warnings),
            metadata={"stratigraphic_closure": report.to_dict(), "solid_readiness": validate_solid_analysis_readiness(mesh).to_dict(), **dict(request.metadata)},
        )

class GmshOCCFragmentTet4MeshGenerator:
    key = "gmsh_occ_fragment_tet4_from_stl"
    label = "Gmsh/OCC fragment Tet4 mesher for STL strata"
    supported_mesh_kinds = (
        "gmsh_occ_fragment_tet4_from_stl",
        "gmsh_occ_fragment_strata",
        "production_gmsh_occ_tet4",
        "occ_fragment_tet4_from_stl",
    )

    @property
    def capabilities(self) -> PluginCapability:
        from geoai_simkit.mesh.geometry_kernel_core import geometry_kernel_dependency_status

        deps = geometry_kernel_dependency_status()
        dependency_rows = () if deps.production_tet4_available else (
            PluginDependencyStatus(name="gmsh", available=deps.gmsh_available, detail="Required for production OCC fragment Tet4 meshing."),
            PluginDependencyStatus(name="meshio", available=deps.meshio_available, detail="Required to convert Gmsh .msh output to MeshDocument."),
        )
        return PluginCapability(
            key=self.key,
            label=self.label,
            category="mesh_generator",
            version="1",
            features=(
                "gmsh_occ_fragment",
                "production_tet4",
                "physical_group_preservation",
                "meshio_conversion",
                "debug_logging",
                "dependency_light_fallback",
            ),
            supported_inputs=("STL surface MeshDocument", "soil or stratigraphic layer definitions", "ProjectWritePort"),
            supported_outputs=("MeshDocument:solid_volume", "GmshOCCFragmentMeshingReport"),
            health=PluginHealth(
                available=True,
                status="available" if deps.production_tet4_available else "fallback",
                dependencies=dependency_rows,
                diagnostics=tuple(deps.diagnostics),
            ),
            metadata={"mesh_kinds": self.supported_mesh_kinds, "production_tet4_available": deps.production_tet4_available},
        )

    def can_generate(self, request: MeshRequest) -> bool:
        kind = str(request.mesh_kind or "")
        if kind not in self.supported_mesh_kinds:
            return False
        project = request.project_document()
        mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
        return bool(mesh is not None and validate_solid_analysis_readiness(mesh).surface_cell_count)

    def generate(self, request: MeshRequest) -> MeshResult:
        from geoai_simkit.mesh.geometry_kernel_core import build_gmsh_occ_fragment_tet4_mesh

        project = request.project_document()
        options = dict(request.options or {})
        mesh, report = build_gmsh_occ_fragment_tet4_mesh(
            project,
            layers=tuple(options.get("layers") or options.get("surface_layers") or ()),
            mesh_size=options.get("mesh_size"),
            attach=bool(request.attach),
            allow_fallback=bool(options.get("allow_fallback", True)),
            debug=options.get("debug"),
            debug_dir=options.get("debug_dir"),
        )
        if mesh is None:
            raise RuntimeError("gmsh_occ_fragment_tet4_from_stl failed: " + str(report.to_dict()))
        return MeshResult(
            mesh=mesh,
            mesh_kind=self.key,
            attached=bool(request.attach),
            quality=mesh.quality,
            warnings=tuple(mesh.quality.warnings),
            metadata={"gmsh_occ_fragment": report.to_dict(), "solid_readiness": validate_solid_analysis_readiness(mesh).to_dict(), **dict(request.metadata)},
        )


try:
    __all__.append("GmshOCCFragmentTet4MeshGenerator")
except NameError:
    __all__ = ["GmshOCCFragmentTet4MeshGenerator"]
