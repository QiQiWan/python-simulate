from __future__ import annotations

"""GeoProjectDocument-native geometry commands with legacy fallback.

These commands now operate directly on GeoProjectDocument when the document has
``geometry_model``.  The old EngineeringDocument path is kept only as a
compatibility fallback for older scripts.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar
import copy

from geoai_simkit.commands.command import Command, CommandResult


def _is_geoproject(document: Any) -> bool:
    return hasattr(document, "geometry_model") and hasattr(document, "phase_manager")


def _next_id(prefix: str, existing: set[str] | dict[str, Any]) -> str:
    keys = set(existing.keys()) if isinstance(existing, dict) else set(existing)
    index = len(keys) + 1
    while f"{prefix}_{index:03d}" in keys:
        index += 1
    return f"{prefix}_{index:03d}"


def _mark(project: Any, scopes: list[str], action: str, affected: list[str]) -> None:
    if hasattr(project, "mark_changed"):
        project.mark_changed(scopes, action=action, affected_entities=affected)
    elif hasattr(project, "metadata"):
        project.metadata["dirty"] = True


def _legacy_dirty(document: Any) -> None:
    try:
        document.dirty.geometry_dirty = True
        document.dirty.mesh_dirty = True
        document.dirty.solve_dirty = True
        document.dirty.result_stale = True
    except Exception:
        pass


@dataclass(slots=True)
class GeoProjectDocumentCommand(Command):
    """Marker base class for commands that natively mutate GeoProjectDocument."""

    transaction_scope: ClassVar[tuple[str, ...]] = ("project",)

    def mark_changed(self, document: Any, *, action: str, affected_entities: list[str]) -> None:
        if _is_geoproject(document):
            _mark(document, list(self.transaction_scope), action, affected_entities)


@dataclass(slots=True)
class AssignMaterialCommand(GeoProjectDocumentCommand):
    block_id: str
    material_id: str
    id: str = "assign_material"
    name: str = "Assign material"
    transaction_scope: ClassVar[tuple[str, ...]] = ("material",)
    _previous_material: str | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            volume = document.geometry_model.volumes[self.block_id]
            self._previous_material = volume.material_id
            document.set_volume_material(self.block_id, self.material_id)
            return CommandResult(self.id, self.name, affected_entities=[self.block_id], message=f"Assigned {self.material_id} to {self.block_id}", metadata=volume.to_dict())
        block = document.geometry.blocks[self.block_id]
        self._previous_material = block.material_id
        document.set_block_material(self.block_id, self.material_id)
        return CommandResult(self.id, self.name, affected_entities=[self.block_id], message=f"Assigned {self.material_id} to {self.block_id}")

    def undo(self, document: Any) -> CommandResult:
        if self._previous_material is not None:
            if _is_geoproject(document):
                document.set_volume_material(self.block_id, self._previous_material)
            else:
                document.set_block_material(self.block_id, self._previous_material)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.block_id], message=f"Restored material on {self.block_id}")


@dataclass(slots=True)
class SetBlockVisibilityCommand(GeoProjectDocumentCommand):
    block_id: str
    visible: bool
    id: str = "set_block_visibility"
    name: str = "Set block visibility"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry",)
    _previous_visible: bool | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            volume = document.geometry_model.volumes[self.block_id]
            self._previous_visible = bool(volume.metadata.get("visible", True))
            volume.metadata["visible"] = bool(self.visible)
            self.mark_changed(document, action=self.id, affected_entities=[self.block_id])
            return CommandResult(self.id, self.name, affected_entities=[self.block_id], metadata=volume.to_dict())
        block = document.geometry.blocks[self.block_id]
        self._previous_visible = bool(block.visible)
        block.visible = bool(self.visible)
        try:
            document.dirty.messages.append(f"block visibility changed: {self.block_id}")
        except Exception:
            pass
        return CommandResult(self.id, self.name, affected_entities=[self.block_id])

    def undo(self, document: Any) -> CommandResult:
        if self._previous_visible is not None:
            if _is_geoproject(document):
                document.geometry_model.volumes[self.block_id].metadata["visible"] = self._previous_visible
                self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[self.block_id])
            else:
                document.geometry.blocks[self.block_id].visible = self._previous_visible
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.block_id])


@dataclass(slots=True)
class CreatePointCommand(GeoProjectDocumentCommand):
    x: float
    y: float
    z: float
    point_id: str | None = None
    snap: bool = True
    id: str = "create_point"
    name: str = "Create point"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry",)
    _created_id: str | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            from geoai_simkit.geometry.entities import PointEntity

            pid = self.point_id or _next_id("point", document.geometry_model.points)
            point = PointEntity(id=pid, x=float(self.x), y=float(self.y), z=float(self.z), metadata={"created_by_command": self.id})
            document.geometry_model.points[pid] = point
            document.topology_graph.add_node(pid, "point", label=pid)
            self._created_id = pid
            self.mark_changed(document, action=self.id, affected_entities=[pid])
            return CommandResult(self.id, self.name, affected_entities=[pid], message=f"Created point {pid}", metadata=point.to_dict())
        from geoai_simkit.geometry.editor import GeometryEditor

        point = GeometryEditor(document.geometry).create_point(self.x, self.y, self.z, point_id=self.point_id, snap=self.snap, metadata={"created_by_command": self.id})
        self._created_id = point.id
        _legacy_dirty(document)
        return CommandResult(self.id, self.name, affected_entities=[point.id], message=f"Created point {point.id}", metadata=point.to_dict())

    def undo(self, document: Any) -> CommandResult:
        if self._created_id:
            if _is_geoproject(document):
                document.geometry_model.points.pop(self._created_id, None)
                self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[self._created_id])
            else:
                document.geometry.points.pop(self._created_id, None)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[] if not self._created_id else [self._created_id])


@dataclass(slots=True)
class MovePointCommand(GeoProjectDocumentCommand):
    point_id: str
    x: float
    y: float
    z: float
    snap: bool = True
    id: str = "move_point"
    name: str = "Move point"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry",)
    _previous: tuple[float, float, float] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            point = document.geometry_model.points[self.point_id]
            self._previous = point.to_tuple()
            point.x, point.y, point.z = float(self.x), float(self.y), float(self.z)
            self.mark_changed(document, action=self.id, affected_entities=[self.point_id])
            return CommandResult(self.id, self.name, affected_entities=[self.point_id], message=f"Moved point {self.point_id}", metadata=point.to_dict())
        from geoai_simkit.geometry.editor import GeometryEditor

        point, previous = GeometryEditor(document.geometry).move_point(self.point_id, self.x, self.y, self.z, snap=self.snap)
        self._previous = previous
        _legacy_dirty(document)
        return CommandResult(self.id, self.name, affected_entities=[self.point_id], message=f"Moved point {self.point_id}", metadata=point.to_dict())

    def undo(self, document: Any) -> CommandResult:
        if self._previous is not None:
            if _is_geoproject(document):
                point = document.geometry_model.points[self.point_id]
                point.x, point.y, point.z = self._previous
                self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[self.point_id])
            else:
                from geoai_simkit.geometry.editor import GeometryEditor

                GeometryEditor(document.geometry).move_point(self.point_id, *self._previous, snap=False)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.point_id])


@dataclass(slots=True)
class CreateLineCommand(GeoProjectDocumentCommand):
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    edge_id: str | None = None
    role: str = "sketch"
    snap: bool = True
    id: str = "create_line"
    name: str = "Create line"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry", "topology")
    _created_edge_id: str | None = field(default=None, init=False, repr=False)
    _created_point_ids: list[str] = field(default_factory=list, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            from geoai_simkit.geometry.entities import PointEntity
            from geoai_simkit.geoproject import GeometryCurve

            pid1 = _next_id("point", document.geometry_model.points)
            document.geometry_model.points[pid1] = PointEntity(pid1, *map(float, self.start), metadata={"created_by": self.id})
            pid2 = _next_id("point", document.geometry_model.points)
            document.geometry_model.points[pid2] = PointEntity(pid2, *map(float, self.end), metadata={"created_by": self.id})
            edge_id = self.edge_id or _next_id("curve", document.geometry_model.curves)
            curve = GeometryCurve(id=edge_id, name=edge_id, point_ids=[pid1, pid2], kind=self.role, metadata={"created_by_command": self.id})
            document.geometry_model.curves[edge_id] = curve
            document.topology_graph.add_node(edge_id, "edge", label=edge_id, role=self.role)
            for pid in (pid1, pid2):
                document.topology_graph.add_node(pid, "point", label=pid)
                document.topology_graph.add_edge(edge_id, pid, "owns")
            self._created_edge_id = edge_id
            self._created_point_ids = [pid1, pid2]
            self.mark_changed(document, action=self.id, affected_entities=[edge_id, pid1, pid2])
            return CommandResult(self.id, self.name, affected_entities=[edge_id, pid1, pid2], message=f"Created line {edge_id}", metadata=curve.to_dict())
        from geoai_simkit.geometry.editor import GeometryEditor

        before = set(document.geometry.points.keys())
        edge = GeometryEditor(document.geometry).create_line_from_coords(self.start, self.end, edge_id=self.edge_id, role=self.role, snap=self.snap)
        self._created_edge_id = edge.id
        self._created_point_ids = sorted(set(document.geometry.points.keys()) - before)
        _legacy_dirty(document)
        return CommandResult(self.id, self.name, affected_entities=[edge.id, *edge.point_ids], message=f"Created line {edge.id}", metadata=edge.to_dict())

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            if self._created_edge_id:
                document.geometry_model.curves.pop(self._created_edge_id, None)
            for pid in self._created_point_ids:
                document.geometry_model.points.pop(pid, None)
            self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[self._created_edge_id or "", *self._created_point_ids])
        else:
            if self._created_edge_id:
                document.geometry.edges.pop(self._created_edge_id, None)
            for pid in self._created_point_ids:
                document.geometry.points.pop(pid, None)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[] if not self._created_edge_id else [self._created_edge_id])


@dataclass(slots=True)
class CreateSurfaceCommand(GeoProjectDocumentCommand):
    coords: tuple[tuple[float, float, float], ...]
    surface_id: str | None = None
    role: str = "sketch"
    plane: str = "xz"
    snap: bool = True
    id: str = "create_surface"
    name: str = "Create surface"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry", "topology")
    _created_surface_id: str | None = field(default=None, init=False, repr=False)
    _created_point_ids: list[str] = field(default_factory=list, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            from geoai_simkit.geometry.entities import PointEntity
            from geoai_simkit.geoproject import GeometrySurface

            point_ids = []
            for xyz in self.coords:
                pid = _next_id("point", document.geometry_model.points)
                document.geometry_model.points[pid] = PointEntity(pid, *map(float, xyz), metadata={"created_by": self.id})
                point_ids.append(pid)
            sid = self.surface_id or _next_id("surface", document.geometry_model.surfaces)
            surface = GeometrySurface(id=sid, name=sid, point_ids=point_ids, kind=self.role, metadata={"plane": self.plane, "created_by_command": self.id})
            document.geometry_model.surfaces[sid] = surface
            document.topology_graph.add_node(sid, "face", label=sid, role=self.role)
            for pid in point_ids:
                document.topology_graph.add_edge(sid, pid, "owns")
            self._created_surface_id = sid
            self._created_point_ids = point_ids
            self.mark_changed(document, action=self.id, affected_entities=[sid, *point_ids])
            return CommandResult(self.id, self.name, affected_entities=[sid, *point_ids], message=f"Created surface {sid}", metadata=surface.to_dict())
        from geoai_simkit.geometry.editor import GeometryEditor

        before_points = set(document.geometry.points.keys())
        surface = GeometryEditor(document.geometry).create_surface_from_coords(list(self.coords), surface_id=self.surface_id, role=self.role, plane=self.plane, snap=self.snap)
        self._created_surface_id = surface.id
        self._created_point_ids = sorted(set(document.geometry.points.keys()) - before_points)
        _legacy_dirty(document)
        return CommandResult(self.id, self.name, affected_entities=[surface.id, *surface.point_ids], message=f"Created surface {surface.id}", metadata=surface.to_dict())

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            if self._created_surface_id:
                document.geometry_model.surfaces.pop(self._created_surface_id, None)
            for pid in self._created_point_ids:
                document.geometry_model.points.pop(pid, None)
            self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[self._created_surface_id or "", *self._created_point_ids])
        else:
            if self._created_surface_id:
                document.geometry.surfaces.pop(self._created_surface_id, None)
            for pid in self._created_point_ids:
                document.geometry.points.pop(pid, None)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[] if not self._created_surface_id else [self._created_surface_id])


@dataclass(slots=True)
class CreateBlockCommand(GeoProjectDocumentCommand):
    bounds: tuple[float, float, float, float, float, float]
    block_id: str | None = None
    name_hint: str | None = None
    role: str = "structure"
    material_id: str | None = None
    id: str = "create_block"
    name: str = "Create block"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry", "topology", "mesh", "solver", "result")
    _created_block_id: str | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            from geoai_simkit.geoproject import GeometryVolume

            vid = self.block_id or _next_id("volume", document.geometry_model.volumes)
            volume = GeometryVolume(id=vid, name=self.name_hint or vid, bounds=tuple(map(float, self.bounds)), role=self.role, material_id=self.material_id, metadata={"created_by_command": self.id, "visible": True})
            document.geometry_model.volumes[vid] = volume
            document.topology_graph.add_node(vid, "volume", label=volume.name, role=volume.role, material_id=volume.material_id)
            if self.material_id:
                document.topology_graph.add_node(self.material_id, "material", label=self.material_id)
                document.topology_graph.add_edge(vid, self.material_id, "mapped_to", relation_group="volume_material")
            for phase_id in document.phase_ids():
                document.set_phase_volume_activation(phase_id, vid, True)
            self._created_block_id = vid
            self.mark_changed(document, action=self.id, affected_entities=[vid])
            return CommandResult(self.id, self.name, affected_entities=[vid], message=f"Created volume {vid}", metadata=volume.to_dict())
        from geoai_simkit.geometry.editor import GeometryEditor

        block = GeometryEditor(document.geometry).create_block(self.bounds, block_id=self.block_id, name=self.name_hint, role=self.role, material_id=self.material_id)
        self._created_block_id = block.id
        document.topology = __import__('geoai_simkit.geometry.light_block_kernel', fromlist=['LightBlockKernel']).LightBlockKernel().find_adjacent_faces(document.geometry)
        _legacy_dirty(document)
        return CommandResult(self.id, self.name, affected_entities=[block.id, *block.face_ids], message=f"Created block {block.id}", metadata=block.to_dict())

    def undo(self, document: Any) -> CommandResult:
        if self._created_block_id:
            if _is_geoproject(document):
                document.geometry_model.volumes.pop(self._created_block_id, None)
                for phase_id in document.phase_ids():
                    try:
                        phase = document.get_phase(phase_id)
                        phase.active_blocks.discard(self._created_block_id)
                        phase.inactive_blocks.discard(self._created_block_id)
                        document.refresh_phase_snapshot(phase_id)
                    except Exception:
                        pass
                self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[self._created_block_id])
            else:
                document.geometry.blocks.pop(self._created_block_id, None)
                document.topology = __import__('geoai_simkit.geometry.light_block_kernel', fromlist=['LightBlockKernel']).LightBlockKernel().find_adjacent_faces(document.geometry)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[] if not self._created_block_id else [self._created_block_id])


@dataclass(slots=True)
class DeleteGeometryEntityCommand(GeoProjectDocumentCommand):
    entity_type: str
    entity_id: str
    id: str = "delete_geometry_entity"
    name: str = "Delete geometry entity"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry", "topology", "mesh", "solver", "result")
    _backup: Any | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            mapping = {
                "point": document.geometry_model.points,
                "edge": document.geometry_model.curves,
                "curve": document.geometry_model.curves,
                "surface": document.geometry_model.surfaces,
                "block": document.geometry_model.volumes,
                "volume": document.geometry_model.volumes,
            }
            store = mapping.get(self.entity_type)
            if store is None or self.entity_id not in store:
                return CommandResult(self.id, self.name, ok=False, message=f"Entity not found: {self.entity_type}:{self.entity_id}")
            self._backup = copy.deepcopy(store[self.entity_id])
            store.pop(self.entity_id, None)
            for phase_id in document.phase_ids():
                try:
                    phase = document.get_phase(phase_id)
                    phase.active_blocks.discard(self.entity_id)
                    phase.inactive_blocks.discard(self.entity_id)
                    document.refresh_phase_snapshot(phase_id)
                except Exception:
                    pass
            self.mark_changed(document, action=self.id, affected_entities=[self.entity_id])
            return CommandResult(self.id, self.name, affected_entities=[self.entity_id], message=f"Deleted {self.entity_type} {self.entity_id}")
        from geoai_simkit.geometry.editor import GeometryEditor

        self._backup = GeometryEditor(document.geometry).delete_entity(self.entity_type, self.entity_id)
        if self._backup is None:
            return CommandResult(self.id, self.name, ok=False, message=f"Entity not found: {self.entity_type}:{self.entity_id}")
        _legacy_dirty(document)
        try:
            document.selection.remove(f"geometry:{self.entity_type}:{self.entity_id}")
        except Exception:
            pass
        return CommandResult(self.id, self.name, affected_entities=[self.entity_id], message=f"Deleted {self.entity_type} {self.entity_id}")

    def undo(self, document: Any) -> CommandResult:
        if self._backup is None:
            return CommandResult(self.id, f"Undo {self.name}", ok=False, message="No backup is available")
        if _is_geoproject(document):
            store = {
                "point": document.geometry_model.points,
                "edge": document.geometry_model.curves,
                "curve": document.geometry_model.curves,
                "surface": document.geometry_model.surfaces,
                "block": document.geometry_model.volumes,
                "volume": document.geometry_model.volumes,
            }.get(self.entity_type)
            if store is None:
                return CommandResult(self.id, f"Undo {self.name}", ok=False, message=f"Unsupported entity type: {self.entity_type}")
            store[self.entity_id] = self._backup
            self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[self.entity_id])
        else:
            store = {
                "point": document.geometry.points,
                "edge": document.geometry.edges,
                "surface": document.geometry.surfaces,
                "block": document.geometry.blocks,
                "face": document.geometry.faces,
            }.get(self.entity_type)
            if store is None:
                return CommandResult(self.id, f"Undo {self.name}", ok=False, message=f"Unsupported entity type: {self.entity_type}")
            store[self.entity_id] = self._backup
            _legacy_dirty(document)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.entity_id], message=f"Restored {self.entity_type} {self.entity_id}")


@dataclass(slots=True)
class CreateSupportCommand(GeoProjectDocumentCommand):
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    support_type: str = "strut"
    support_id: str | None = None
    material_id: str | None = None
    stage_id: str | None = None
    id: str = "create_support"
    name: str = "Create support structure"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry", "structure", "phase", "solver")
    _support_id: str | None = field(default=None, init=False, repr=False)
    _edge_id: str | None = field(default=None, init=False, repr=False)
    _created_point_ids: list[str] = field(default_factory=list, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            from geoai_simkit.geometry.entities import PointEntity
            from geoai_simkit.geoproject import GeometryCurve, StructureRecord

            sid = self.support_id or _next_id("beam", document.structure_model.beams)
            p1 = _next_id("point", document.geometry_model.points)
            document.geometry_model.points[p1] = PointEntity(p1, *map(float, self.start), metadata={"created_by": self.id})
            p2 = _next_id("point", document.geometry_model.points)
            document.geometry_model.points[p2] = PointEntity(p2, *map(float, self.end), metadata={"created_by": self.id})
            edge_id = _next_id("support_axis", document.geometry_model.curves)
            document.geometry_model.curves[edge_id] = GeometryCurve(id=edge_id, name=edge_id, point_ids=[p1, p2], kind="support_axis", metadata={"support_type": self.support_type})
            record = StructureRecord(id=sid, name=sid, geometry_ref=edge_id, material_id=self.material_id or "support_beam", active_stage_ids=[], metadata={"support_type": self.support_type})
            document.structure_model.beams[sid] = record
            if self.stage_id:
                document.set_phase_structure_activation(self.stage_id, sid, True)
            document.topology_graph.add_node(sid, "support", label=sid, support_type=self.support_type)
            document.topology_graph.add_edge(sid, edge_id, "generated_by")
            self._support_id = sid
            self._edge_id = edge_id
            self._created_point_ids = [p1, p2]
            self.mark_changed(document, action=self.id, affected_entities=[sid, edge_id, p1, p2])
            return CommandResult(self.id, self.name, affected_entities=[sid, edge_id], message=f"Created {self.support_type} {sid}", metadata=record.to_dict())
        from geoai_simkit.geometry.engineering_tools import EngineeringSupportService

        before_points = set(document.geometry.points.keys())
        row = EngineeringSupportService(document).create_support_axis(self.start, self.end, support_type=self.support_type, support_id=self.support_id, material_id=self.material_id, stage_id=self.stage_id)
        self._support_id = str(row["id"])
        self._edge_id = str(row["axis_edge_id"])
        self._created_point_ids = sorted(set(document.geometry.points.keys()) - before_points)
        return CommandResult(self.id, self.name, affected_entities=[self._support_id, self._edge_id], message=f"Created {self.support_type} {self._support_id}", metadata=row)

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            if self._support_id:
                document.structure_model.beams.pop(self._support_id, None)
                for phase_id in document.phase_ids():
                    document.get_phase(phase_id).active_supports.discard(self._support_id)
                    document.refresh_phase_snapshot(phase_id)
            if self._edge_id:
                document.geometry_model.curves.pop(self._edge_id, None)
            for pid in self._created_point_ids:
                document.geometry_model.points.pop(pid, None)
            self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[] if not self._support_id else [self._support_id])
        else:
            if self._support_id:
                document.supports.pop(self._support_id, None)
                for stage in document.stages.stages.values():
                    stage.active_supports.discard(self._support_id)
            if self._edge_id:
                document.geometry.edges.pop(self._edge_id, None)
            for pid in self._created_point_ids:
                document.geometry.points.pop(pid, None)
            _legacy_dirty(document)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[] if not self._support_id else [self._support_id])


@dataclass(slots=True)
class SplitSoilLayerCommand(GeoProjectDocumentCommand):
    z_level: float
    id: str = "split_soil_layer"
    name: str = "Split soil layer by horizontal line"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry", "soil", "topology", "phase")
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            from geoai_simkit.geoproject import GeometryVolume

            self._backup = document.to_dict()
            generated: list[str] = []
            for volume in list(document.geometry_model.volumes.values()):
                if volume.bounds is None or volume.role not in {"soil", "excavation", "rock", "unknown"}:
                    continue
                xmin, xmax, ymin, ymax, zmin, zmax = volume.bounds
                if not (zmin < self.z_level < zmax):
                    continue
                document.geometry_model.volumes.pop(volume.id, None)
                lower_id = f"{volume.id}_below_{abs(int(self.z_level*100)):04d}"
                upper_id = f"{volume.id}_above_{abs(int(self.z_level*100)):04d}"
                lower = GeometryVolume(lower_id, f"{volume.name} below {self.z_level:g}", (xmin, xmax, ymin, ymax, zmin, self.z_level), role=volume.role, material_id=volume.material_id, metadata={**volume.metadata, "split_from": volume.id})
                upper = GeometryVolume(upper_id, f"{volume.name} above {self.z_level:g}", (xmin, xmax, ymin, ymax, self.z_level, zmax), role=volume.role, material_id=volume.material_id, metadata={**volume.metadata, "split_from": volume.id})
                document.geometry_model.volumes[lower_id] = lower
                document.geometry_model.volumes[upper_id] = upper
                generated.extend([lower_id, upper_id])
                for phase_id in document.phase_ids():
                    phase = document.get_phase(phase_id)
                    was_active = volume.id not in phase.inactive_blocks
                    phase.active_blocks.discard(volume.id)
                    phase.inactive_blocks.discard(volume.id)
                    if was_active:
                        phase.active_blocks.update([lower_id, upper_id])
                    document.refresh_phase_snapshot(phase_id)
            document.rebuild_generated_by_relations()
            self.mark_changed(document, action=self.id, affected_entities=generated)
            return CommandResult(self.id, self.name, affected_entities=generated, message=f"Split soil volumes at z={self.z_level:g}", metadata={"generated_block_ids": generated})
        import copy as _copy
        from geoai_simkit.geometry.engineering_tools import split_soil_by_horizontal_level

        self._backup = {"geometry": _copy.deepcopy(document.geometry), "topology": _copy.deepcopy(document.topology)}
        row = split_soil_by_horizontal_level(document, self.z_level)
        return CommandResult(self.id, self.name, affected_entities=list(row.get("generated_block_ids", [])), message=f"Split soil blocks at z={self.z_level:g}", metadata=row)

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document) and self._backup is not None:
            restored = document.from_dict(self._backup)
            for field_name in document.__dataclass_fields__:
                setattr(document, field_name, getattr(restored, field_name))
            return CommandResult(self.id, f"Undo {self.name}", message="Restored GeoProjectDocument before soil split")
        if self._backup is not None and isinstance(self._backup, dict):
            document.geometry = self._backup.get("geometry", document.geometry)
            document.topology = self._backup.get("topology", document.topology)
            _legacy_dirty(document)
        return CommandResult(self.id, f"Undo {self.name}", message="Restored geometry before soil split")


@dataclass(slots=True)
class SplitExcavationPolygonCommand(GeoProjectDocumentCommand):
    vertices: tuple[tuple[float, float, float], ...]
    stage_id: str | None = None
    id: str = "split_excavation_polygon"
    name: str = "Split excavation polygon"
    transaction_scope: ClassVar[tuple[str, ...]] = ("geometry", "phase", "topology")
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            from geoai_simkit.geoproject import GeometryVolume

            self._backup = document.to_dict()
            if not self.vertices:
                return CommandResult(self.id, self.name, ok=False, message="No excavation polygon vertices")
            xs = [float(v[0]) for v in self.vertices]
            ys = [float(v[1]) for v in self.vertices]
            zs = [float(v[2]) for v in self.vertices]
            excavation_id = _next_id("excavation", document.geometry_model.volumes)
            volume = GeometryVolume(excavation_id, excavation_id, (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)), role="excavation", material_id=None, metadata={"polygon_vertices": [list(v) for v in self.vertices]})
            document.geometry_model.volumes[excavation_id] = volume
            target_stage = self.stage_id or document.phase_manager.active_phase_id
            if target_stage:
                document.set_phase_volume_activation(target_stage, excavation_id, False)
            self.mark_changed(document, action=self.id, affected_entities=[excavation_id])
            return CommandResult(self.id, self.name, affected_entities=[excavation_id], message="Created excavation placeholder volume", metadata=volume.to_dict())
        import copy as _copy
        from geoai_simkit.geometry.engineering_tools import split_excavation_by_polygon

        self._backup = {"geometry": _copy.deepcopy(document.geometry), "topology": _copy.deepcopy(document.topology), "stages": _copy.deepcopy(document.stages)}
        row = split_excavation_by_polygon(document, list(self.vertices), stage_id=self.stage_id)
        affected = [*list(row.get("excavation_block_ids", [])), *list(row.get("residual_soil_block_ids", []))]
        return CommandResult(self.id, self.name, affected_entities=affected, message=f"Created excavation split with {len(row.get('excavation_block_ids', []))} excavation block(s)", metadata=row)

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document) and self._backup is not None:
            restored = document.from_dict(self._backup)
            for field_name in document.__dataclass_fields__:
                setattr(document, field_name, getattr(restored, field_name))
            return CommandResult(self.id, f"Undo {self.name}", message="Restored GeoProjectDocument before excavation split")
        if self._backup is not None:
            document.geometry = self._backup.get("geometry", document.geometry)
            document.topology = self._backup.get("topology", document.topology)
            document.stages = self._backup.get("stages", document.stages)
            _legacy_dirty(document)
        return CommandResult(self.id, f"Undo {self.name}", message="Restored geometry before excavation split")


@dataclass(slots=True)
class SetInterfaceReviewStatusCommand(GeoProjectDocumentCommand):
    contact_id: str
    status: str = "accepted"
    contact_type: str | None = None
    id: str = "set_interface_review_status"
    name: str = "Set interface review status"
    transaction_scope: ClassVar[tuple[str, ...]] = ("topology", "structure", "phase")
    _previous: Any | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            interface = document.structure_model.structural_interfaces.get(self.contact_id)
            self._previous = copy.deepcopy(interface)
            if interface is None:
                return CommandResult(self.id, self.name, ok=False, message=f"Interface not found: {self.contact_id}")
            interface.metadata["review_status"] = self.status
            if self.contact_type:
                interface.metadata["contact_type"] = self.contact_type
            self.mark_changed(document, action=self.id, affected_entities=[self.contact_id])
            return CommandResult(self.id, self.name, affected_entities=[self.contact_id], message=f"Interface {self.contact_id} -> {self.status}", metadata=interface.to_dict())
        from geoai_simkit.geometry.engineering_tools import InterfaceReviewService

        self._previous = dict(document.interfaces.get(self.contact_id, {})) if self.contact_id in document.interfaces else None
        row = InterfaceReviewService(document).set_status(self.contact_id, status=self.status, contact_type=self.contact_type)
        return CommandResult(self.id, self.name, affected_entities=[self.contact_id], message=f"Interface {self.contact_id} -> {self.status}", metadata=row)

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            if self._previous is None:
                document.structure_model.structural_interfaces.pop(self.contact_id, None)
            else:
                document.structure_model.structural_interfaces[self.contact_id] = self._previous
            self.mark_changed(document, action=f"undo_{self.id}", affected_entities=[self.contact_id])
        else:
            if self._previous is None:
                document.interfaces.pop(self.contact_id, None)
                for stage in document.stages.stages.values():
                    stage.active_interfaces.discard(self.contact_id)
            else:
                document.interfaces[self.contact_id] = self._previous
            _legacy_dirty(document)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.contact_id])


@dataclass(slots=True)
class UpdateSoilLayerSplitCommand(SplitSoilLayerCommand):
    feature_id: str = ""
    id: str = "update_soil_layer_split"
    name: str = "Update soil layer split"


@dataclass(slots=True)
class UpdateExcavationPolygonCommand(SplitExcavationPolygonCommand):
    feature_id: str = ""
    id: str = "update_excavation_polygon"
    name: str = "Update excavation polygon"


@dataclass(slots=True)
class UpdateSupportParametersCommand(GeoProjectDocumentCommand):
    support_id: str
    start: tuple[float, float, float] | None = None
    end: tuple[float, float, float] | None = None
    support_type: str | None = None
    material_id: str | None = None
    stage_id: str | None = None
    id: str = "update_support_parameters"
    name: str = "Update support parameters"
    transaction_scope: ClassVar[tuple[str, ...]] = ("structure", "geometry", "phase", "solver")
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            self._backup = document.to_dict()
            record = document.get_structure_record(self.support_id)
            if record is None:
                return CommandResult(self.id, self.name, ok=False, message=f"Support not found: {self.support_id}")
            if self.material_id:
                document.set_structure_material(self.support_id, self.material_id)
            if self.support_type:
                record.metadata["support_type"] = self.support_type
            if self.stage_id:
                document.set_phase_structure_activation(self.stage_id, self.support_id, True)
            self.mark_changed(document, action=self.id, affected_entities=[self.support_id])
            return CommandResult(self.id, self.name, affected_entities=[self.support_id], message=f"Updated support {self.support_id}", metadata=record.to_dict())
        import copy as _copy
        from geoai_simkit.geometry.parametric_editing import ParametricEditingService

        self._backup = {"geometry": _copy.deepcopy(document.geometry), "topology": _copy.deepcopy(document.topology), "stages": _copy.deepcopy(document.stages), "supports": _copy.deepcopy(document.supports), "materials": _copy.deepcopy(document.materials)}
        row = ParametricEditingService(document).update_support_parameters(self.support_id, start=self.start, end=self.end, support_type=self.support_type, material_id=self.material_id, stage_id=self.stage_id)
        return CommandResult(self.id, self.name, affected_entities=[self.support_id], message=f"Updated support {self.support_id}", metadata=row)

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document) and self._backup is not None:
            restored = document.from_dict(self._backup)
            for field_name in document.__dataclass_fields__:
                setattr(document, field_name, getattr(restored, field_name))
            return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.support_id], message="Restored support before parameter update")
        if self._backup is not None:
            document.geometry = self._backup.get("geometry", document.geometry)
            document.topology = self._backup.get("topology", document.topology)
            document.stages = self._backup.get("stages", document.stages)
            document.supports = self._backup.get("supports", document.supports)
            document.materials = self._backup.get("materials", document.materials)
            _legacy_dirty(document)
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.support_id], message="Restored support before parameter update")
