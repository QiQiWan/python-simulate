from __future__ import annotations

"""Undoable commands for CAD facade feature execution."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.commands.command import Command, CommandResult
from geoai_simkit.services.cad_facade_kernel import build_cad_topology_index, execute_deferred_cad_features, probe_cad_facade_kernel


def _restore_document(document: Any, backup: dict[str, Any] | None) -> None:
    if backup is None:
        return
    restored = document.__class__.from_dict(backup)
    for field_name in document.__dataclass_fields__:
        setattr(document, field_name, getattr(restored, field_name))


@dataclass(slots=True)
class BuildCadTopologyIndexCommand(Command):
    id: str = "build_cad_topology_index"
    name: str = "Build CAD facade persistent topology index"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "geometry_model"):
            return CommandResult(self.id, self.name, ok=False, message="CAD topology indexing requires GeoProjectDocument")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        capability = probe_cad_facade_kernel().to_dict()
        report = build_cad_topology_index(document, attach=True)
        return CommandResult(
            self.id,
            self.name,
            ok=report.ok,
            affected_entities=[row["source_entity_id"] for row in report.records if row.get("kind") == "solid"],
            message=f"CAD topology index built: solids={report.solid_count}, faces={report.face_count}, edges={report.edge_count}",
            metadata={"capability": capability, "topology_index": report.to_dict()},
        )

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)


@dataclass(slots=True)
class ExecuteCadFeaturesCommand(Command):
    require_native: bool = False
    allow_fallback: bool = True
    id: str = "execute_cad_features"
    name: str = "Execute CAD facade features"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "geometry_model"):
            return CommandResult(self.id, self.name, ok=False, message="CAD feature execution requires GeoProjectDocument")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        try:
            report = execute_deferred_cad_features(document, require_native=self.require_native, allow_fallback=self.allow_fallback, attach_topology_index=True)
        except Exception as exc:
            return CommandResult(self.id, self.name, ok=False, message=f"CAD facade feature execution failed: {type(exc).__name__}: {exc}")
        return CommandResult(
            self.id,
            self.name,
            ok=report.ok,
            affected_entities=[*report.generated_volume_ids, *report.consumed_volume_ids],
            message=f"CAD facade features executed: {report.executed_feature_count}/{report.feature_count} using {report.backend}",
            metadata=report.to_dict(),
        )

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)


__all__ = ["BuildCadTopologyIndexCommand", "ExecuteCadFeaturesCommand"]

@dataclass(slots=True)
class ExecuteGmshOccBooleanMeshRoundtripCommand(Command):
    """Execute boolean features and build a physical-group Tet4 mesh roundtrip."""

    output_dir: str | None = None
    stem: str = "release_1_4_2c_gmsh_occ"
    element_size: float | None = None
    require_native: bool = False
    allow_contract_fallback: bool = True
    id: str = "execute_gmsh_occ_boolean_mesh_roundtrip"
    name: str = "Execute Gmsh/OCC boolean mesh roundtrip"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "geometry_model") or not hasattr(document, "mesh_model"):
            return CommandResult(self.id, self.name, ok=False, message="Gmsh/OCC roundtrip requires GeoProjectDocument")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        try:
            from geoai_simkit.services.gmsh_occ_boolean_roundtrip import execute_gmsh_occ_boolean_mesh_roundtrip
            report = execute_gmsh_occ_boolean_mesh_roundtrip(
                document,
                output_dir=self.output_dir,
                stem=self.stem,
                element_size=self.element_size,
                require_native=self.require_native,
                allow_contract_fallback=self.allow_contract_fallback,
                execute_boolean_features=True,
                attach=True,
            )
        except Exception as exc:
            return CommandResult(self.id, self.name, ok=False, message=f"Gmsh/OCC boolean mesh roundtrip failed: {type(exc).__name__}: {exc}")
        return CommandResult(
            self.id,
            self.name,
            ok=report.ok,
            affected_entities=[*report.generated_volume_ids, *report.consumed_volume_ids],
            message=f"Gmsh/OCC boolean mesh roundtrip: {report.status} backend={report.backend} cells={report.cell_count}",
            metadata=report.to_dict(),
        )

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)


__all__.append("ExecuteGmshOccBooleanMeshRoundtripCommand")


@dataclass(slots=True)
class BuildCadShapeStoreCommand(Command):
    output_dir: str | None = None
    include_roundtrip: bool = True
    export_references: bool = False
    id: str = "build_cad_shape_store"
    name: str = "Build CadShapeStore / BRep references"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "geometry_model") or not hasattr(document, "cad_shape_store"):
            return CommandResult(self.id, self.name, ok=False, message="CadShapeStore build requires GeoProjectDocument 1.4.2d+")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        try:
            from geoai_simkit.services.cad_shape_store_service import build_cad_shape_store
            report = build_cad_shape_store(document, output_dir=self.output_dir, attach=True, include_roundtrip=self.include_roundtrip, export_references=self.export_references)
        except Exception as exc:
            return CommandResult(self.id, self.name, ok=False, message=f"CadShapeStore build failed: {type(exc).__name__}: {exc}")
        return CommandResult(self.id, self.name, ok=report.ok, affected_entities=list(getattr(document.cad_shape_store, "shapes", {}).keys()), message=f"CadShapeStore built: shapes={report.shape_count}, topology={report.topology_record_count}, refs={report.serialized_ref_count}", metadata=report.to_dict())

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)


__all__.append("BuildCadShapeStoreCommand")

@dataclass(slots=True)
class ImportStepIfcSolidTopologyCommand(Command):
    source_path: str = ""
    output_dir: str | None = None
    source_format: str | None = None
    require_native: bool = False
    export_references: bool = True
    id: str = "import_step_ifc_solid_topology"
    name: str = "Import STEP/IFC solid topology and bind CadShapeStore"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "geometry_model") or not hasattr(document, "cad_shape_store"):
            return CommandResult(self.id, self.name, ok=False, message="STEP/IFC import requires GeoProjectDocument with CadShapeStore")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        try:
            from geoai_simkit.services.step_ifc_shape_import import import_step_ifc_solid_topology
            report = import_step_ifc_solid_topology(
                document,
                self.source_path,
                output_dir=self.output_dir,
                source_format=self.source_format,
                attach=True,
                require_native=self.require_native,
                export_references=self.export_references,
            )
        except Exception as exc:
            return CommandResult(self.id, self.name, ok=False, message=f"STEP/IFC solid import failed: {type(exc).__name__}: {exc}")
        return CommandResult(
            self.id,
            self.name,
            ok=report.ok,
            affected_entities=list(report.imported_volume_ids),
            message=f"STEP/IFC solid import: {report.status} solids={report.imported_solid_count} backend={report.backend}",
            metadata=report.to_dict(),
        )

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)

__all__.append("ImportStepIfcSolidTopologyCommand")

@dataclass(slots=True)
class BindTopologyMaterialPhaseCommand(Command):
    include_faces: bool = True
    include_edges: bool = True
    include_solids: bool = True
    overwrite: bool = True
    id: str = "bind_topology_material_phase"
    name: str = "Bind face/edge topology to material and phase"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "cad_shape_store"):
            return CommandResult(self.id, self.name, ok=False, message="Topology binding requires GeoProjectDocument with CadShapeStore")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        try:
            from geoai_simkit.services.topology_material_phase_binding import bind_topology_material_phase
            report = bind_topology_material_phase(
                document,
                include_faces=self.include_faces,
                include_edges=self.include_edges,
                include_solids=self.include_solids,
                overwrite=self.overwrite,
            )
        except Exception as exc:
            return CommandResult(self.id, self.name, ok=False, message=f"Topology material/phase binding failed: {type(exc).__name__}: {exc}")
        return CommandResult(
            self.id,
            self.name,
            ok=report.ok,
            affected_entities=list(getattr(document.cad_shape_store, "topology_bindings", {}).keys()),
            message=f"Topology material/phase bindings: {report.binding_count} (faces={report.face_binding_count}, edges={report.edge_binding_count})",
            metadata=report.to_dict(),
        )

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)

__all__.append("BindTopologyMaterialPhaseCommand")

@dataclass(slots=True)
class AssignTopologyMaterialPhaseCommand(Command):
    topology_id: str = ""
    material_id: str | None = None
    phase_ids: list[str] | None = None
    role: str | None = None
    id: str = "assign_topology_material_phase"
    name: str = "Assign selected topology material/phase"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "cad_shape_store"):
            return CommandResult(self.id, self.name, ok=False, message="Topology assignment requires GeoProjectDocument with CadShapeStore")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        try:
            from geoai_simkit.services.topology_material_phase_binding import assign_topology_material_phase
            report = assign_topology_material_phase(document, self.topology_id, material_id=self.material_id, phase_ids=self.phase_ids, role=self.role)
        except Exception as exc:
            return CommandResult(self.id, self.name, ok=False, message=f"Topology assignment failed: {type(exc).__name__}: {exc}")
        return CommandResult(self.id, self.name, ok=bool(report.get("ok")), affected_entities=[self.topology_id], message=f"Topology assignment: {report.get('status')}", metadata=report)

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)

__all__.append("AssignTopologyMaterialPhaseCommand")
