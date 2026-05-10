from __future__ import annotations

"""Default mesh-generator plugin registry."""

from geoai_simkit.adapters import LayeredMeshGeneratorAdapter, TaggedPreviewMeshGeneratorAdapter
from geoai_simkit.mesh.stl_volume_generators import ConformalTet4FromSTLRegionsMeshGenerator, GmshTet4FromSTLMeshGenerator, VoxelHex8FromSTLMeshGenerator
from geoai_simkit.contracts import MeshGenerator, MeshGeneratorRegistry

_DEFAULT_REGISTRY: MeshGeneratorRegistry | None = None


def get_default_mesh_generator_registry() -> MeshGeneratorRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = MeshGeneratorRegistry()
        registry.register(LayeredMeshGeneratorAdapter())
        registry.register(TaggedPreviewMeshGeneratorAdapter())
        registry.register(VoxelHex8FromSTLMeshGenerator())
        registry.register(GmshTet4FromSTLMeshGenerator())
        registry.register(ConformalTet4FromSTLRegionsMeshGenerator())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def register_mesh_generator(generator: MeshGenerator, *, replace: bool = False) -> None:
    get_default_mesh_generator_registry().register(generator, replace=replace)


def mesh_generator_descriptors() -> list[dict[str, object]]:
    registry = get_default_mesh_generator_registry()
    rows = registry.descriptors()
    for row in rows:
        item = registry.get(str(row["key"]))
        row.setdefault("capabilities", {})["supported_mesh_kinds"] = list(getattr(item, "supported_mesh_kinds", ()) or ())
    return rows


__all__ = [
    "get_default_mesh_generator_registry",
    "mesh_generator_descriptors",
    "register_mesh_generator",
]
