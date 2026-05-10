from __future__ import annotations

"""GeoProjectDocument-native visual modeling system facade.

The facade now treats GeoProjectDocument as the single source of truth.  Legacy
EngineeringDocument objects can still be converted by geoproject_source, but all
interactive edits, selection, stage activation, meshing, compiling and result
preview actions mutate the GeoProjectDocument root directly.
"""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.app.panels import build_object_tree, build_property_payload, build_stage_timeline, object_tree_to_rows
from geoai_simkit.app.panels.material_editor import assign_structure_material, assign_volume_material, build_material_editor
from geoai_simkit.app.panels.solver_compiler import build_solver_compiler, compile_phase_models, run_incremental_solver
from geoai_simkit.app.panels.stage_editor import build_stage_editor, set_interface_activation, set_load_activation, set_structure_activation, set_volume_activation, set_water_condition
from geoai_simkit.app.viewport import HeadlessViewport
from geoai_simkit.commands import (
    AssignMaterialCommand,
    CommandStack,
    CreateBlockCommand,
    CreateLineCommand,
    CreatePointCommand,
    CreateSurfaceCommand,
    CreateSupportCommand,
    DeleteGeometryEntityCommand,
    GeneratePreviewMeshCommand,
    MovePointCommand,
    RunPreviewStageResultsCommand,
    SetBlockVisibilityCommand,
    SetInterfaceReviewStatusCommand,
    SetStageBlockActivationCommand,
    SplitExcavationPolygonCommand,
    SplitSoilLayerCommand,
    UpdateExcavationPolygonCommand,
    UpdateSoilLayerSplitCommand,
    UpdateSupportParametersCommand,
)
from geoai_simkit.document import SelectionRef
from geoai_simkit.document.selection import SelectionSet
from geoai_simkit.geoproject import GeoProjectDocument


@dataclass(slots=True)
class WorkbenchValidationIssue:
    severity: str
    code: str
    message: str
    entity_id: str | None = None
    hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "entity_id": self.entity_id,
            "hint": self.hint,
        }


@dataclass(slots=True)
class VisualModelingSystem:
    document: GeoProjectDocument = field(default_factory=lambda: GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="integrated-geoproject-pit"))
    viewport: HeadlessViewport = field(default_factory=HeadlessViewport)
    command_stack: CommandStack = field(default_factory=CommandStack)
    selection: SelectionSet = field(default_factory=SelectionSet)
    active_tool_name: str = "select"
    operation_log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.document, GeoProjectDocument):
            from geoai_simkit.app.geoproject_source import get_geoproject_document

            self.document = get_geoproject_document(self.document)
        self.selection = self.document.selection
        self.document.populate_default_framework_content()
        if self.document.mesh_model.mesh_document is None:
            self.command_stack.execute(GeneratePreviewMeshCommand(), self.document)
        self.refresh_viewport()

    @classmethod
    def create_default(cls, parameters: dict[str, Any] | None = None) -> "VisualModelingSystem":
        return cls(document=GeoProjectDocument.create_foundation_pit(parameters or {"dimension": "3d"}, name="integrated-geoproject-pit"))

    @property
    def active_phase_id(self) -> str:
        return self.document.phase_manager.active_phase_id

    def log(self, action: str, **metadata: Any) -> None:
        self.operation_log.append({"action": action, **metadata})
        self.operation_log[:] = self.operation_log[-100:]

    def refresh_viewport(self, stage_id: str | None = None) -> dict[str, Any]:
        self.viewport.load_document(self.document, stage_id=stage_id or self.document.phase_manager.active_phase_id)
        self.viewport.state.selection = self.selection
        return self.viewport.render_payload()

    def set_active_stage(self, stage_id: str) -> dict[str, Any]:
        self.document.set_active_phase(stage_id)
        self.refresh_viewport(stage_id)
        self.log("set_active_stage", stage_id=stage_id)
        return self.stage_timeline()

    def make_selection_ref(self, entity_id: str, entity_type: str = "block") -> SelectionRef | None:
        entity_type = "block" if entity_type == "volume" else str(entity_type)
        if entity_type == "stage":
            try:
                stage = self.document.get_phase(entity_id)
            except KeyError:
                return None
            return SelectionRef(entity_id=entity_id, entity_type="stage", source="stage", display_name=stage.name, metadata=stage.to_dict())
        if entity_type == "point" and entity_id in self.document.geometry_model.points:
            item = self.document.geometry_model.points[entity_id]
            return SelectionRef(entity_id=entity_id, entity_type="point", source="geometry", display_name=entity_id, metadata=item.to_dict())
        if entity_type in {"edge", "curve"} and entity_id in self.document.geometry_model.curves:
            item = self.document.geometry_model.curves[entity_id]
            return SelectionRef(entity_id=entity_id, entity_type="edge", source="geometry", display_name=item.name, metadata=item.to_dict())
        if entity_type == "surface" and entity_id in self.document.geometry_model.surfaces:
            item = self.document.geometry_model.surfaces[entity_id]
            return SelectionRef(entity_id=entity_id, entity_type="surface", source="geometry", display_name=item.name, metadata=item.to_dict())
        if entity_type == "block" and entity_id in self.document.geometry_model.volumes:
            item = self.document.geometry_model.volumes[entity_id]
            return SelectionRef(entity_id=entity_id, entity_type="block", source="geometry", display_name=item.name, metadata=item.to_dict())
        if entity_type == "support":
            record = self.document.get_structure_record(entity_id)
            if record is None:
                return None
            return SelectionRef(entity_id=entity_id, entity_type="support", source="geometry", display_name=record.name, metadata=record.to_dict())
        if entity_type == "interface" and entity_id in self.document.structure_model.structural_interfaces:
            item = self.document.structure_model.structural_interfaces[entity_id]
            return SelectionRef(entity_id=entity_id, entity_type="interface", source="geometry", display_name=item.name, metadata=item.to_dict())
        if entity_type == "result" and entity_id in self.document.result_store.phase_results:
            return SelectionRef(entity_id=entity_id, entity_type="result", source="result", display_name=entity_id)
        return None

    def apply_selection(self, ref: SelectionRef | None, *, modifier: str = "replace") -> SelectionRef | None:
        if ref is None:
            if modifier == "replace":
                self.clear_selection()
            return None
        if modifier == "add":
            self.selection.add(ref)
        elif modifier == "toggle":
            if any(item.key == ref.key for item in self.selection.items):
                self.selection.remove(ref)
            else:
                self.selection.add(ref)
        else:
            self.selection.set_single(ref)
        self.viewport.state.selection = self.selection
        self.log("apply_selection", entity_id=ref.entity_id, entity_type=ref.entity_type, modifier=modifier, count=len(self.selection.items))
        return ref

    def apply_selection_many(self, refs: list[SelectionRef], *, modifier: str = "replace") -> list[SelectionRef]:
        if modifier == "replace":
            self.selection.clear()
        for ref in refs:
            if modifier == "toggle" and any(item.key == ref.key for item in self.selection.items):
                self.selection.remove(ref)
            else:
                self.selection.add(ref, make_active=False)
        self.selection.active = self.selection.items[-1] if self.selection.items else None
        self.viewport.state.selection = self.selection
        self.log("apply_selection_many", count=len(refs), modifier=modifier, selected=len(self.selection.items))
        return refs

    def select_entity(self, entity_id: str, entity_type: str = "block") -> SelectionRef | None:
        ref = self.make_selection_ref(entity_id, entity_type)
        if ref is not None:
            self.apply_selection(ref)
            self.viewport.select_entity(entity_id, entity_type="block" if entity_type == "volume" else entity_type)
        self.log(f"select_{entity_type}", entity_id=entity_id, selected=ref is not None)
        return ref

    def clear_selection(self) -> None:
        self.selection.clear()
        self.viewport.state.selection.clear()
        self.log("clear_selection")

    def locate_point(self, x: float, y: float, z: float, *, snap: bool = True) -> dict[str, Any]:
        grid = float(self.document.metadata.get("snap_grid", 0.5))
        if snap and grid > 0:
            x, y, z = round(x / grid) * grid, round(y / grid) * grid, round(z / grid) * grid
        located = {"x": float(x), "y": float(y), "z": float(z), "snapped": bool(snap), "grid": grid}
        self.log("locate_point", **located)
        return located

    def create_point(self, x: float, y: float, z: float, *, snap: bool = True) -> dict[str, Any]:
        result = self.command_stack.execute(CreatePointCommand(x=x, y=y, z=z, snap=snap), self.document)
        point_id = result.affected_entities[0] if result.affected_entities else None
        if point_id:
            self.select_entity(point_id, "point")
        self.refresh_viewport()
        self.log("create_point", x=x, y=y, z=z, ok=result.ok)
        return result.to_dict()

    def move_selected_point(self, x: float, y: float, z: float, *, snap: bool = True) -> dict[str, Any] | None:
        ref = self.selection.active
        if ref is None or ref.entity_type != "point":
            self.log("move_selected_point", ok=False, reason="no point selected")
            return None
        result = self.command_stack.execute(MovePointCommand(point_id=ref.entity_id, x=x, y=y, z=z, snap=snap), self.document)
        self.select_entity(ref.entity_id, "point")
        self.refresh_viewport()
        self.log("move_selected_point", point_id=ref.entity_id, ok=result.ok)
        return result.to_dict()

    def create_line(self, start: tuple[float, float, float], end: tuple[float, float, float], *, snap: bool = True) -> dict[str, Any]:
        result = self.command_stack.execute(CreateLineCommand(start=start, end=end, snap=snap), self.document)
        edge_id = result.affected_entities[0] if result.affected_entities else None
        if edge_id:
            self.select_entity(edge_id, "edge")
        self.refresh_viewport()
        self.log("create_line", start=start, end=end, ok=result.ok)
        return result.to_dict()

    def create_surface(self, coords: list[tuple[float, float, float]], *, snap: bool = True) -> dict[str, Any]:
        result = self.command_stack.execute(CreateSurfaceCommand(coords=tuple(coords), snap=snap), self.document)
        surface_id = result.affected_entities[0] if result.affected_entities else None
        if surface_id:
            self.select_entity(surface_id, "surface")
        self.refresh_viewport()
        self.log("create_surface", point_count=len(coords), ok=result.ok)
        return result.to_dict()

    def create_block(self, bounds: tuple[float, float, float, float, float, float], *, role: str = "structure", material_id: str | None = None) -> dict[str, Any]:
        result = self.command_stack.execute(CreateBlockCommand(bounds=bounds, role=role, material_id=material_id), self.document)
        block_id = result.affected_entities[0] if result.affected_entities else None
        if block_id:
            self.select_entity(block_id, "block")
        self.refresh_viewport()
        self.log("create_block", bounds=bounds, role=role, ok=result.ok)
        return result.to_dict()

    def create_support(self, start: tuple[float, float, float], end: tuple[float, float, float], *, support_type: str = "strut", stage_id: str | None = None) -> dict[str, Any]:
        result = self.command_stack.execute(CreateSupportCommand(start=start, end=end, support_type=support_type, stage_id=stage_id or self.active_phase_id), self.document)
        support_id = result.affected_entities[0] if result.affected_entities else None
        if support_id:
            self.select_entity(support_id, "support")
        self.refresh_viewport()
        self.log("create_support", support_type=support_type, ok=result.ok)
        return result.to_dict()

    def geometry_editor_panel(self) -> dict[str, Any]:
        return {
            "contract": "geoproject_geometry_editor_v1",
            "data_source": "GeoProjectDocument.GeometryModel",
            "counts": {
                "points": len(self.document.geometry_model.points),
                "curves": len(self.document.geometry_model.curves),
                "surfaces": len(self.document.geometry_model.surfaces),
                "volumes": len(self.document.geometry_model.volumes),
                "blocks": len(self.document.geometry_model.volumes),
                "parametric_features": len(self.document.geometry_model.parametric_features),
            },
            "tools": ["point", "line", "surface", "volume", "support_axis", "soil_layer_split", "excavation_polygon"],
        }

    def assign_material(self, block_id: str, material_id: str) -> dict[str, Any]:
        result = self.command_stack.execute(AssignMaterialCommand(block_id=block_id, material_id=material_id), self.document)
        self.refresh_viewport()
        self.log("assign_material", block_id=block_id, material_id=material_id, ok=result.ok)
        return result.to_dict()

    def assign_structure_material(self, structure_id: str, material_id: str, *, category: str | None = None) -> dict[str, Any]:
        result = assign_structure_material(self.document, structure_id, material_id, category=category)
        self.refresh_viewport()
        self.log("assign_structure_material", structure_id=structure_id, material_id=material_id, ok=result.get("ok"))
        return result

    def set_block_visibility(self, block_id: str, visible: bool) -> dict[str, Any]:
        result = self.command_stack.execute(SetBlockVisibilityCommand(block_id=block_id, visible=visible), self.document)
        self.refresh_viewport()
        self.log("set_block_visibility", block_id=block_id, visible=visible, ok=result.ok)
        return result.to_dict()

    def selected_block_ids(self) -> list[str]:
        return [ref.entity_id for ref in self.selection.items if ref.entity_type == "block" and ref.entity_id in self.document.geometry_model.volumes]

    def set_selected_blocks_visibility(self, visible: bool) -> list[dict[str, Any]]:
        results = [self.set_block_visibility(block_id, visible) for block_id in self.selected_block_ids()]
        self.log("set_selected_blocks_visibility", visible=visible, count=len(results))
        return results

    def set_selected_blocks_activation(self, stage_id: str, active: bool) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for block_id in self.selected_block_ids():
            result = self.command_stack.execute(SetStageBlockActivationCommand(stage_id=stage_id, block_id=block_id, active=active), self.document)
            results.append(result.to_dict())
        self.refresh_viewport(stage_id)
        self.log("set_selected_blocks_activation", stage_id=stage_id, active=active, count=len(results))
        return results

    def set_selected_block_activation(self, stage_id: str, active: bool) -> dict[str, Any] | None:
        ids = self.selected_block_ids()
        if not ids:
            self.log("set_selected_block_activation", ok=False, reason="no block selected")
            return None
        result = self.command_stack.execute(SetStageBlockActivationCommand(stage_id=stage_id, block_id=ids[-1], active=active), self.document)
        self.refresh_viewport(stage_id)
        self.log("set_selected_block_activation", stage_id=stage_id, active=active, result=result.to_dict())
        return result.to_dict()

    def set_structure_activation(self, stage_id: str, structure_id: str, active: bool) -> dict[str, Any]:
        result = set_structure_activation(self.document, stage_id, structure_id, active)
        self.refresh_viewport(stage_id)
        return result

    def set_interface_activation(self, stage_id: str, interface_id: str, active: bool) -> dict[str, Any]:
        result = set_interface_activation(self.document, stage_id, interface_id, active)
        self.refresh_viewport(stage_id)
        return result

    def set_load_activation(self, stage_id: str, load_id: str, active: bool) -> dict[str, Any]:
        result = set_load_activation(self.document, stage_id, load_id, active)
        self.refresh_viewport(stage_id)
        return result

    def set_water_condition(self, stage_id: str, water_condition_id: str | None = None, *, water_level: float | None = None) -> dict[str, Any]:
        result = set_water_condition(self.document, stage_id, water_condition_id, water_level=water_level)
        self.refresh_viewport(stage_id)
        return result

    def delete_selected_geometry_entities(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        refs = list(self.selection.items)
        priority = {"surface": 0, "edge": 1, "point": 2, "block": 3}
        refs.sort(key=lambda ref: priority.get(ref.entity_type, 99))
        for ref in refs:
            if ref.entity_type not in {"point", "edge", "surface", "block"}:
                continue
            result = self.command_stack.execute(DeleteGeometryEntityCommand(entity_type=ref.entity_type, entity_id=ref.entity_id), self.document)
            results.append(result.to_dict())
        self.selection.clear()
        self.refresh_viewport()
        self.log("delete_selected_geometry_entities", count=len(results))
        return results

    def snap_contract(self) -> dict[str, Any]:
        return {"enabled": True, "grid": float(self.document.metadata.get("snap_grid", 0.5)), "source": "GeoProjectDocument"}

    def locate_with_snap(self, x: float, y: float, z: float) -> dict[str, Any]:
        return self.locate_point(x, y, z, snap=True)

    def split_soil_layer_at(self, z_level: float) -> dict[str, Any]:
        result = self.command_stack.execute(SplitSoilLayerCommand(z_level=float(z_level)), self.document)
        self.refresh_viewport()
        self.log("split_soil_layer_at", z_level=z_level, ok=result.ok)
        return result.to_dict()

    def split_excavation_polygon(self, vertices: list[tuple[float, float, float]], *, stage_id: str | None = None) -> dict[str, Any]:
        result = self.command_stack.execute(SplitExcavationPolygonCommand(vertices=tuple(vertices), stage_id=stage_id or self.active_phase_id), self.document)
        self.refresh_viewport()
        self.log("split_excavation_polygon", vertex_count=len(vertices), ok=result.ok)
        return result.to_dict()

    def interface_review_panel(self) -> dict[str, Any]:
        return {
            "contract": "geoproject_interface_review_v1",
            "summary": {"interfaces": len(self.document.structure_model.structural_interfaces)},
            "rows": [row.to_dict() for row in self.document.structure_model.structural_interfaces.values()],
        }

    def rebuild_interface_candidates(self) -> dict[str, Any]:
        self.document.populate_default_framework_content()
        self.refresh_viewport()
        self.log("rebuild_interface_candidates", count=len(self.document.structure_model.structural_interfaces))
        return self.interface_review_panel()

    def set_interface_review_status(self, contact_id: str, *, status: str = "accepted", contact_type: str | None = None) -> dict[str, Any]:
        result = self.command_stack.execute(SetInterfaceReviewStatusCommand(contact_id=contact_id, status=status, contact_type=contact_type), self.document)
        self.refresh_viewport()
        self.log("set_interface_review_status", contact_id=contact_id, status=status, ok=result.ok)
        return result.to_dict()

    def accept_first_interface_candidate(self) -> dict[str, Any] | None:
        rows = self.interface_review_panel().get("rows", [])
        for row in rows:
            if str(row.get("metadata", {}).get("review_status", "candidate")) != "accepted":
                return self.set_interface_review_status(str(row["id"]), status="accepted", contact_type=str(row.get("contact_mode") or "interface"))
        return None

    def parametric_editing_panel(self) -> dict[str, Any]:
        return {"contract": "geoproject_parametric_editing_v1", "features": [row.to_dict() for row in self.document.geometry_model.parametric_features.values()]}

    def feature_id_for_selection(self, preferred_type: str | None = None) -> str | None:
        ref = self.selection.active
        if ref is None or ref.entity_type != "block":
            return None
        volume = self.document.geometry_model.volumes.get(ref.entity_id)
        feature_id = None if volume is None else volume.metadata.get("split_feature_id") or volume.metadata.get("feature_id")
        if feature_id and preferred_type:
            feature = self.document.geometry_model.parametric_features.get(str(feature_id))
            return str(feature_id) if feature is not None and feature.type == preferred_type else None
        return None if feature_id is None else str(feature_id)

    def update_soil_layer_feature(self, feature_id: str, z_level: float) -> dict[str, Any]:
        result = self.command_stack.execute(UpdateSoilLayerSplitCommand(z_level=float(z_level), feature_id=feature_id), self.document)
        self.refresh_viewport()
        self.log("update_soil_layer_feature", feature_id=feature_id, z_level=z_level, ok=result.ok)
        return result.to_dict()

    def update_selected_soil_layer_z(self, z_level: float) -> dict[str, Any] | None:
        feature_id = self.feature_id_for_selection("horizontal_layer")
        return None if not feature_id else self.update_soil_layer_feature(feature_id, z_level)

    def update_excavation_feature(self, feature_id: str, vertices: list[tuple[float, float, float]], *, stage_id: str | None = None) -> dict[str, Any]:
        result = self.command_stack.execute(UpdateExcavationPolygonCommand(vertices=tuple(vertices), stage_id=stage_id or self.active_phase_id, feature_id=feature_id), self.document)
        self.refresh_viewport()
        self.log("update_excavation_feature", feature_id=feature_id, vertex_count=len(vertices), ok=result.ok)
        return result.to_dict()

    def update_selected_excavation_polygon(self, vertices: list[tuple[float, float, float]], *, stage_id: str | None = None) -> dict[str, Any] | None:
        feature_id = self.feature_id_for_selection("excavation_surface")
        return None if not feature_id else self.update_excavation_feature(feature_id, vertices, stage_id=stage_id)

    def update_support_parameters(self, support_id: str, **kwargs: Any) -> dict[str, Any]:
        result = self.command_stack.execute(UpdateSupportParametersCommand(support_id=support_id, **kwargs), self.document)
        self.refresh_viewport()
        self.log("update_support_parameters", support_id=support_id, ok=result.ok)
        return result.to_dict()

    def update_selected_support_parameters(self, **kwargs: Any) -> dict[str, Any] | None:
        ref = self.selection.active
        if ref is None or ref.entity_type != "support":
            self.log("update_selected_support_parameters", ok=False, reason="no support selected")
            return None
        return self.update_support_parameters(ref.entity_id, **kwargs)

    def generate_mesh(self) -> dict[str, Any]:
        result = self.command_stack.execute(GeneratePreviewMeshCommand(), self.document)
        self.refresh_viewport()
        self.log("generate_mesh", ok=result.ok)
        return result.to_dict()

    def compile_solver(self) -> dict[str, Any]:
        result = compile_phase_models(self.document)
        self.log("compile_solver", ok=result.get("ok"))
        return result

    def run_results(self) -> dict[str, Any]:
        result = self.command_stack.execute(RunPreviewStageResultsCommand(), self.document)
        self.refresh_viewport()
        self.log("run_results", ok=result.ok)
        return result.to_dict()

    def run_incremental_solver(self) -> dict[str, Any]:
        result = run_incremental_solver(self.document)
        self.refresh_viewport()
        self.log("run_incremental_solver", ok=result.get("ok"), phase_count=len(result.get("summary", {}).get("phase_records", [])))
        return result

    def undo(self) -> dict[str, Any]:
        result = self.command_stack.undo(self.document)
        self.refresh_viewport()
        self.log("undo", ok=result.ok, message=result.message)
        return result.to_dict()

    def redo(self) -> dict[str, Any]:
        result = self.command_stack.redo(self.document)
        self.refresh_viewport()
        self.log("redo", ok=result.ok, message=result.message)
        return result.to_dict()

    def object_tree(self) -> dict[str, Any]:
        tree = build_object_tree(self.document)
        return {"tree": tree.to_dict(), "rows": object_tree_to_rows(tree)}

    def property_panel(self) -> dict[str, Any]:
        return build_property_payload(self.document, self.selection.active)

    def stage_timeline(self) -> dict[str, Any]:
        return build_stage_timeline(self.document)

    def stage_editor(self) -> dict[str, Any]:
        return build_stage_editor(self.document)

    def material_editor(self) -> dict[str, Any]:
        return build_material_editor(self.document)

    def solver_compiler(self) -> dict[str, Any]:
        return build_solver_compiler(self.document)

    def mesh_panel(self) -> dict[str, Any]:
        mesh = self.document.mesh_model.mesh_document
        if mesh is None:
            return {"available": False, "message": "Mesh has not been generated.", "settings": self.document.mesh_model.mesh_settings.to_dict()}
        return {
            "available": True,
            "node_count": mesh.node_count,
            "cell_count": mesh.cell_count,
            "cell_tags": list(mesh.cell_tags.keys()),
            "face_tags": list(mesh.face_tags.keys()),
            "block_to_cells": {k: list(v) for k, v in mesh.entity_map.block_to_cells.items()},
            "quality": mesh.quality.to_dict(),
            "metadata": dict(mesh.metadata),
        }

    def result_panel(self) -> dict[str, Any]:
        return {
            "available": bool(self.document.result_store.phase_results),
            "phase_results": [row.to_dict() for row in self.document.result_store.phase_results.values()],
            "engineering_metrics": [row.to_dict() for row in self.document.result_store.engineering_metrics.values()],
            "curves": [row.to_dict() for row in self.document.result_store.curves.values()],
            "sections": [row.to_dict() for row in self.document.result_store.sections.values()],
        }

    def validate(self) -> list[WorkbenchValidationIssue]:
        issues: list[WorkbenchValidationIssue] = []
        validation = self.document.validate_framework()
        if not self.document.geometry_model.volumes:
            issues.append(WorkbenchValidationIssue("error", "geometry.empty", "No geometry volumes are available."))
        for ref in validation.get("missing_material_refs", [])[:20]:
            issues.append(WorkbenchValidationIssue("warning", "material.missing", "Missing material reference.", str(ref)))
        if not self.document.topology_graph.contact_edges():
            issues.append(WorkbenchValidationIssue("warning", "topology.no_contacts", "No contact pairs were detected.", hint="Run contact detection or inspect geometry tolerance."))
        if self.document.mesh_model.mesh_document is None:
            issues.append(WorkbenchValidationIssue("info", "mesh.not_generated", "Preview mesh has not been generated."))
        if not self.document.result_store.phase_results:
            issues.append(WorkbenchValidationIssue("info", "results.not_available", "Stage results have not been generated."))
        return issues

    def operation_pages(self) -> dict[str, Any]:
        return {
            "modeling": {
                "title": "Modeling",
                "tools": ["select", "point", "line", "surface", "volume", "move_point", "box_select", "multi_select", "context_menu", "soil_layer", "excavation_polygon", "wall", "strut", "anchor", "interface_review", "stage_activation", "parametric_edit"],
                "object_tree_count": len(self.object_tree()["rows"]),
                "active_selection": self.selection.to_dict(),
                "geometry_editor": self.geometry_editor_panel(),
                "snap": self.snap_contract(),
                "interface_review": self.interface_review_panel().get("summary", {}),
                "parametric_editing": self.parametric_editing_panel(),
            },
            "mesh": self.mesh_panel(),
            "solve": self.solver_compiler(),
            "results": self.result_panel(),
            "benchmark": {"architecture_smoke": "available", "expected_reports": ["reports/visual_modeling_system_smoke.json", "reports/geoproject_native_workflow_smoke.json"]},
            "advanced": {
                "data_source": "GeoProjectDocument",
                "contract": self.document.metadata.get("contract"),
                "dirty_graph": self.document.metadata.get("DirtyGraph", {}),
                "invalidation_graph": self.document.metadata.get("InvalidationGraph", {}),
                "heavy_backends_optional": ["PyVista", "OpenCascade", "CUDA"],
            },
        }

    def to_payload(self) -> dict[str, Any]:
        validation = self.document.validate_framework()
        return {
            "contract": "integrated_visual_modeling_system_v1",
            "native_contract": "geoproject_native_visual_modeling_system_v2",
            "document": {
                "name": self.document.project_settings.name,
                "project_id": self.document.project_settings.project_id,
                "volumes": len(self.document.geometry_model.volumes),
                "surfaces": len(self.document.geometry_model.surfaces),
                "curves": len(self.document.geometry_model.curves),
                "points": len(self.document.geometry_model.points),
                "contacts": len(self.document.topology_graph.contact_edges()),
                "phases": len(self.document.phase_ids()),
                "structures": len(list(self.document.iter_structure_records())),
                "interfaces": len(self.document.structure_model.structural_interfaces),
                "active_phase_id": self.document.phase_manager.active_phase_id,
                "framework_ok": validation.get("ok"),
            },
            "viewport": self.refresh_viewport(),
            "object_tree": self.object_tree(),
            "property_panel": self.property_panel(),
            "geometry_editor": self.geometry_editor_panel(),
            "stage_editor": self.stage_editor(),
            "material_editor": self.material_editor(),
            "solver_compiler": self.solver_compiler(),
            "stage_timeline": self.stage_timeline(),
            "mesh_panel": self.mesh_panel(),
            "result_panel": self.result_panel(),
            "operation_pages": self.operation_pages(),
            "selection": self.selection.to_dict(),
            "command_stack": self.command_stack.to_dict(),
            "validation": [issue.to_dict() for issue in self.validate()],
            "dirty_graph": self.document.metadata.get("DirtyGraph", {}),
            "invalidation_graph": self.document.metadata.get("InvalidationGraph", {}),
            "operation_log": list(self.operation_log[-50:]),
        }


__all__ = ["VisualModelingSystem", "WorkbenchValidationIssue"]
