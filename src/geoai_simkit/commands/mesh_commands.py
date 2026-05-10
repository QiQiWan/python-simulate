from __future__ import annotations

"""Undoable mesh commands for the integrated visual modeling workbench."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.commands.command import Command, CommandResult


def _is_geoproject(document: Any) -> bool:
    return hasattr(document, "geometry_model") and hasattr(document, "mesh_model")


def _preview_mesh_from_geoproject(project: Any) -> Any:
    from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
    from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap

    nodes: list[tuple[float, float, float]] = []
    cells: list[tuple[int, ...]] = []
    block_tags: list[str] = []
    block_to_cells: dict[str, list[int]] = {}
    for volume in project.geometry_model.volumes.values():
        if volume.bounds is None:
            continue
        xmin, xmax, ymin, ymax, zmin, zmax = volume.bounds
        base = len(nodes)
        nodes.extend([
            (xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymax, zmin), (xmin, ymax, zmin),
            (xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax),
        ])
        cell_id = len(cells)
        cells.append(tuple(range(base, base + 8)))
        block_tags.append(volume.id)
        block_to_cells.setdefault(volume.id, []).append(cell_id)
    entity_map = MeshEntityMap(block_to_cells=block_to_cells, metadata={"source": "GeoProjectDocument preview mesh"})
    mesh = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=["hex8_preview"] * len(cells),
        cell_tags={"block_id": block_tags},
        entity_map=entity_map,
        quality=MeshQualityReport(min_quality=1.0 if cells else None, max_aspect_ratio=1.0 if cells else None),
        metadata={"mesher": "geoproject_preview_hex8", "source": "GeoProjectDocument"},
    )
    project.mesh_model.attach_mesh(mesh)
    project.mark_changed(["mesh"], action="generate_preview_mesh", affected_entities=list(block_to_cells))
    return mesh


@dataclass(slots=True)
class GeneratePreviewMeshCommand(Command):
    id: str = "generate_preview_mesh"
    name: str = "Generate preview mesh"
    _previous_mesh: Any = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            self._previous_mesh = document.mesh_model.mesh_document
            mesh = _preview_mesh_from_geoproject(document)
            return CommandResult(
                command_id=self.id,
                name=self.name,
                ok=True,
                message=f"Generated GeoProject preview mesh: {mesh.cell_count} cells / {mesh.node_count} nodes",
                affected_entities=list(document.geometry_model.volumes.keys()),
                metadata={"cell_count": mesh.cell_count, "node_count": mesh.node_count, "mesher": mesh.metadata.get("mesher")},
            )
        self._previous_mesh = getattr(document, "mesh", None)
        mesh = document.generate_preview_mesh()
        return CommandResult(
            command_id=self.id,
            name=self.name,
            ok=True,
            message=f"Generated tagged preview mesh: {mesh.cell_count} cells / {mesh.node_count} nodes",
            affected_entities=list(getattr(document.geometry, "blocks", {}).keys()),
            metadata={"cell_count": mesh.cell_count, "node_count": mesh.node_count, "mesher": mesh.metadata.get("mesher")},
        )

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            document.mesh_model.mesh_document = self._previous_mesh
            if self._previous_mesh is not None:
                document.mesh_model.mesh_entity_map = self._previous_mesh.entity_map
                document.mesh_model.quality_report = self._previous_mesh.quality
            document.mark_changed(["mesh"], action="undo_generate_preview_mesh")
            return CommandResult(command_id=self.id, name=f"Undo {self.name}", ok=True, message="Restored previous GeoProject mesh state")
        document.mesh = self._previous_mesh
        try:
            document.dirty.mesh_dirty = document.mesh is None
            document.dirty.solve_dirty = True
            document.dirty.result_stale = True
            document.dirty.messages.append("undo preview mesh generation")
        except Exception:
            pass
        return CommandResult(command_id=self.id, name=f"Undo {self.name}", ok=True, message="Restored previous mesh state")


@dataclass(slots=True)
class GenerateLayeredVolumeMeshCommand(Command):
    id: str = "generate_layered_volume_mesh"
    name: str = "Generate layered volume mesh"
    nx: int = 8
    ny: int = 8
    interpolate_missing: bool = True
    _previous_mesh: Any = field(default=None, init=False, repr=False)
    _previous_entity_map: Any = field(default=None, init=False, repr=False)
    _previous_quality: Any = field(default=None, init=False, repr=False)
    _previous_settings_metadata: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(
                command_id=self.id,
                name=self.name,
                ok=False,
                message="Layered volume mesh generation requires a GeoProjectDocument.",
            )
        from geoai_simkit.mesh.layered_mesher import generate_layered_volume_mesh

        self._previous_mesh = document.mesh_model.mesh_document
        self._previous_entity_map = document.mesh_model.mesh_entity_map
        self._previous_quality = document.mesh_model.quality_report
        self._previous_settings_metadata = dict(document.mesh_model.mesh_settings.metadata)
        result = generate_layered_volume_mesh(
            document,
            nx=self.nx,
            ny=self.ny,
            interpolate_missing=self.interpolate_missing,
            attach=True,
        )
        document.mark_changed(
            ["mesh"],
            action="generate_layered_volume_mesh",
            affected_entities=list(result.mesh.entity_map.block_to_cells),
        )
        return CommandResult(
            command_id=self.id,
            name=self.name,
            ok=result.ok,
            message=f"Generated layered volume mesh: {result.mesh.cell_count} cells / {result.mesh.node_count} nodes",
            affected_entities=list(result.mesh.entity_map.block_to_cells),
            metadata={
                "cell_count": result.mesh.cell_count,
                "node_count": result.mesh.node_count,
                "layer_count": result.layer_count,
                "warnings": list(result.warnings),
                "mesher": result.mesh.metadata.get("mesher"),
                "grid_shape": [max(int(self.ny), 2), max(int(self.nx), 2)],
            },
        )

    def undo(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(command_id=self.id, name=f"Undo {self.name}", ok=False, message="Layered mesh undo requires a GeoProjectDocument.")
        document.mesh_model.mesh_document = self._previous_mesh
        if self._previous_mesh is not None:
            document.mesh_model.mesh_entity_map = self._previous_mesh.entity_map
            document.mesh_model.quality_report = self._previous_mesh.quality
        else:
            document.mesh_model.mesh_entity_map = self._previous_entity_map
            document.mesh_model.quality_report = self._previous_quality
        document.mesh_model.mesh_settings.metadata = dict(self._previous_settings_metadata)
        document.mark_changed(["mesh"], action="undo_generate_layered_volume_mesh")
        return CommandResult(command_id=self.id, name=f"Undo {self.name}", ok=True, message="Restored previous GeoProject layered mesh state")


__all__ = ["GenerateLayeredVolumeMeshCommand", "GeneratePreviewMeshCommand"]
