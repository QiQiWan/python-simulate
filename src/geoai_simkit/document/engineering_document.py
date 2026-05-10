from __future__ import annotations

"""Unified engineering document for PLAXIS/Abaqus-style visual modeling."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.document.dirty_state import DirtyState
from geoai_simkit.document.selection import SelectionRef, SelectionSet
from geoai_simkit.geometry.kernel import GeometryDocument
from geoai_simkit.geometry.light_block_kernel import LightBlockKernel, geometry_document_from_artifact
from geoai_simkit.geometry.topology_graph import TopologyGraph, build_topology_from_foundation_pit_artifact
from geoai_simkit.mesh.mesh_document import MeshDocument
from geoai_simkit.mesh.tagged_mesher import generate_tagged_preview_mesh
from geoai_simkit.results.result_package import ResultPackage, result_package_from_stage_metrics
from geoai_simkit.stage.stage_plan import StagePlan, stage_plan_from_rows


@dataclass(slots=True)
class MaterialLibraryRecord:
    id: str
    name: str
    model_type: str = "linear_elastic"
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "model_type": self.model_type, "parameters": dict(self.parameters), "metadata": dict(self.metadata)}


@dataclass(slots=True)
class EngineeringDocument:
    name: str
    geometry: GeometryDocument
    topology: TopologyGraph
    materials: dict[str, MaterialLibraryRecord] = field(default_factory=dict)
    supports: dict[str, dict[str, Any]] = field(default_factory=dict)
    interfaces: dict[str, dict[str, Any]] = field(default_factory=dict)
    boundaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    loads: dict[str, dict[str, Any]] = field(default_factory=dict)
    stages: StagePlan = field(default_factory=StagePlan)
    mesh: MeshDocument | None = None
    results: ResultPackage | None = None
    selection: SelectionSet = field(default_factory=SelectionSet)
    dirty: DirtyState = field(default_factory=DirtyState)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_foundation_pit_artifact(cls, artifact: dict[str, Any], *, name: str = "foundation-pit") -> "EngineeringDocument":
        geometry = geometry_document_from_artifact(artifact)
        topology = build_topology_from_foundation_pit_artifact(artifact)
        all_block_ids = list(geometry.blocks.keys())
        stages = stage_plan_from_rows(list(artifact.get("stage_rows", []) or []), all_block_ids=all_block_ids)
        materials: dict[str, MaterialLibraryRecord] = {}
        for block in geometry.blocks.values():
            if block.material_id and block.material_id not in materials:
                materials[block.material_id] = MaterialLibraryRecord(id=block.material_id, name=block.material_id, model_type="engineering_placeholder")
        interfaces = {}
        for row in list(artifact.get("interface_requests", []) or []):
            key = str(row.get("interface_name") or row.get("name") or f"interface_{len(interfaces)+1:03d}")
            interfaces[key] = dict(row)
        results = result_package_from_stage_metrics(name, list(artifact.get("stage_metrics", []) or artifact.get("stage_result_metrics", []) or []))
        return cls(
            name=name,
            geometry=geometry,
            topology=topology,
            materials=materials,
            interfaces=interfaces,
            stages=stages,
            mesh=None,
            results=results,
            metadata={"source": "foundation_pit_artifact", "contract": artifact.get("contract"), "summary": dict(artifact.get("summary", {}) or {}), "parameters": dict(artifact.get("parameters", {}) or {})},
        )

    @classmethod
    def create_foundation_pit(cls, parameters: dict[str, Any] | None = None, *, name: str = "foundation-pit") -> "EngineeringDocument":
        build = LightBlockKernel().create_foundation_pit(parameters or {})
        doc = cls.from_foundation_pit_artifact(build.artifact, name=name)
        doc.geometry = build.geometry
        doc.topology = build.topology
        return doc

    def select(self, ref: SelectionRef | None) -> None:
        self.selection.set_single(ref)

    def select_block(self, block_id: str) -> SelectionRef:
        block = self.geometry.blocks[block_id]
        ref = SelectionRef(entity_id=block_id, entity_type="block", source="geometry", display_name=block.name, metadata={"role": block.role})
        self.select(ref)
        return ref

    def generate_preview_mesh(self) -> MeshDocument:
        self.mesh = generate_tagged_preview_mesh(self.geometry)
        self.dirty.mark_mesh_generated()
        return self.mesh

    def stage_preview(self, stage_id: str | None = None) -> dict[str, Any]:
        from geoai_simkit.stage.activation_service import StageActivationService

        sid = stage_id or self.stages.active_stage_id or (self.stages.order[0] if self.stages.order else "")
        preview = StageActivationService(self.stages).preview_stage(sid, tuple(self.geometry.blocks.keys()))
        return preview.to_dict()

    def set_block_material(self, block_id: str, material_id: str) -> None:
        if block_id not in self.geometry.blocks:
            raise KeyError(f"Block not found: {block_id}")
        self.geometry.blocks[block_id].material_id = material_id
        if material_id not in self.materials:
            self.materials[material_id] = MaterialLibraryRecord(id=material_id, name=material_id, model_type="engineering_placeholder")
        self.dirty.material_dirty = True
        self.dirty.solve_dirty = True
        self.dirty.result_stale = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "geometry": self.geometry.to_dict(),
            "topology": self.topology.to_dict(),
            "materials": [m.to_dict() for m in self.materials.values()],
            "supports": dict(self.supports),
            "interfaces": dict(self.interfaces),
            "boundaries": dict(self.boundaries),
            "loads": dict(self.loads),
            "stages": self.stages.to_dict(),
            "mesh": self.mesh.to_dict() if self.mesh is not None else None,
            "results": self.results.to_dict() if self.results is not None else None,
            "selection": self.selection.to_dict(),
            "dirty": self.dirty.to_dict(),
            "metadata": dict(self.metadata),
        }


def engineering_document_from_simulation_model(model: Any, *, name: str | None = None) -> EngineeringDocument:
    metadata = getattr(model, "metadata", {}) or {}
    artifact = metadata.get("foundation_pit.workflow") or metadata.get("foundation_pit_workflow") or {}
    if isinstance(artifact, dict) and artifact.get("blocks"):
        return EngineeringDocument.from_foundation_pit_artifact(artifact, name=name or str(getattr(model, "name", "foundation-pit")))
    return EngineeringDocument.create_foundation_pit({}, name=name or str(getattr(model, "name", "foundation-pit")))


__all__ = ["MaterialLibraryRecord", "EngineeringDocument", "engineering_document_from_simulation_model"]
