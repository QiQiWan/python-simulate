from __future__ import annotations

"""Mesh-generator adapters for existing meshing implementations."""

from geoai_simkit.contracts import MeshRequest, MeshResult, PluginCapability, PluginHealth


class LayeredMeshGeneratorAdapter:
    key = "layered"
    label = "Layered borehole surface mesher"
    supported_mesh_kinds = ("auto", "layered", "layered_surface", "borehole_layered")
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="mesh_generator",
        version="1",
        features=("layered_surfaces", "attach_to_project", "quality_warnings"),
        supported_inputs=("GeoProjectDocument", "ProjectWritePort"),
        supported_outputs=("MeshDocument",),
        health=PluginHealth(available=True),
        metadata={"mesh_kinds": supported_mesh_kinds},
    )

    def can_generate(self, request: MeshRequest) -> bool:
        kind = str(request.mesh_kind or "auto")
        if kind not in self.supported_mesh_kinds:
            return False
        project = request.project_document()
        volumes = getattr(getattr(project, "geometry_model", None), "volumes", {}) or {}
        surfaces = getattr(getattr(project, "soil_model", None), "soil_layer_surfaces", {}) or {}
        return bool(volumes and surfaces)

    def generate(self, request: MeshRequest) -> MeshResult:
        from geoai_simkit.mesh.layered_mesher import generate_layered_volume_mesh

        project = request.project_document()
        options = dict(request.options)
        nx = int(options.pop("nx", 5))
        ny = int(options.pop("ny", 5))
        interpolate_missing = bool(options.pop("interpolate_missing", True))
        result = generate_layered_volume_mesh(
            project,
            nx=nx,
            ny=ny,
            interpolate_missing=interpolate_missing,
            attach=bool(request.attach),
        )
        return MeshResult(
            mesh=result.mesh,
            mesh_kind=self.key,
            attached=bool(request.attach),
            quality=getattr(result.mesh, "quality", None),
            warnings=tuple(result.warnings),
            metadata={"layer_count": int(result.layer_count), **dict(request.metadata)},
        )


class TaggedPreviewMeshGeneratorAdapter:
    key = "tagged_preview"
    label = "Tagged preview mesh generator"
    supported_mesh_kinds = ("auto", "preview", "tagged_preview")
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="mesh_generator",
        version="1",
        features=("preview", "block_tags", "headless"),
        supported_inputs=("GeometryDocument", "ProjectWritePort"),
        supported_outputs=("TaggedMesh",),
        health=PluginHealth(available=True),
        metadata={"mesh_kinds": supported_mesh_kinds},
    )

    def can_generate(self, request: MeshRequest) -> bool:
        kind = str(request.mesh_kind or "auto")
        if kind not in self.supported_mesh_kinds:
            return False
        project = request.project_document()
        geometry = getattr(getattr(project, "geometry_model", None), "geometry_document", None)
        if geometry is None:
            geometry = getattr(project, "geometry", None)
        return geometry is not None and hasattr(geometry, "blocks")

    def generate(self, request: MeshRequest) -> MeshResult:
        from geoai_simkit.mesh.tagged_mesher import generate_tagged_preview_mesh

        project = request.project_document()
        geometry = getattr(getattr(project, "geometry_model", None), "geometry_document", None)
        if geometry is None:
            geometry = getattr(project, "geometry", None)
        mesh = generate_tagged_preview_mesh(geometry)
        if bool(request.attach) and hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.attach_mesh(mesh)
        return MeshResult(
            mesh=mesh,
            mesh_kind=self.key,
            attached=bool(request.attach),
            quality=getattr(mesh, "quality", None),
            warnings=tuple(getattr(mesh.quality, "warnings", []) or []),
            metadata=dict(request.metadata),
        )


__all__ = ["LayeredMeshGeneratorAdapter", "TaggedPreviewMeshGeneratorAdapter"]
