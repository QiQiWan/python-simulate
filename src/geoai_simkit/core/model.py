from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
try:
    import pyvista as pv
except ModuleNotFoundError:  # optional for non-visual kernel tests
    class _DummyDataSet:  # pragma: no cover
        pass
    class _DummyMultiBlock:  # pragma: no cover
        pass
    class _DummyUnstructuredGrid:  # pragma: no cover
        pass
    class _PVStub:  # pragma: no cover
        DataSet = _DummyDataSet
        MultiBlock = _DummyMultiBlock
        UnstructuredGrid = _DummyUnstructuredGrid
    pv = _PVStub()

from geoai_simkit.geometry.regioning import build_region_tags_from_mesh

from .types import RegionTag, ResultField


@dataclass(slots=True)
class MaterialBinding:
    region_name: str
    material_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MaterialDefinition:
    name: str
    model_type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GeometryObjectRecord:
    key: str
    name: str
    object_type: str
    guid: str = ''
    region_name: str | None = None
    source_block: str | None = None
    parent: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
    visible: bool = True
    pickable: bool = True
    locked: bool = False


@dataclass(slots=True)
class BoundaryCondition:
    name: str
    kind: str
    target: str
    components: tuple[int, ...] = (0, 1, 2)
    values: tuple[float, ...] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoadDefinition:
    name: str
    kind: str
    target: str
    values: tuple[float, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StructuralElementDefinition:
    name: str
    kind: str
    point_ids: tuple[int, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    active_stages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceDefinition:
    name: str
    kind: str
    slave_point_ids: tuple[int, ...]
    master_point_ids: tuple[int, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    active_stages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisStage:
    name: str
    activate_regions: tuple[str, ...] = ()
    deactivate_regions: tuple[str, ...] = ()
    boundary_conditions: tuple[BoundaryCondition, ...] = ()
    loads: tuple[LoadDefinition, ...] = ()
    steps: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SimulationModel:
    name: str
    mesh: pv.DataSet | pv.MultiBlock
    region_tags: list[RegionTag] = field(default_factory=list)
    materials: list[MaterialBinding] = field(default_factory=list)
    material_library: list[MaterialDefinition] = field(default_factory=list)
    object_records: list[GeometryObjectRecord] = field(default_factory=list)
    boundary_conditions: list[BoundaryCondition] = field(default_factory=list)
    stages: list[AnalysisStage] = field(default_factory=list)
    structures: list[StructuralElementDefinition] = field(default_factory=list)
    interfaces: list[InterfaceDefinition] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    results: list[ResultField] = field(default_factory=list)

    def ensure_regions(self) -> None:
        if not self.region_tags:
            self.region_tags = build_region_tags_from_mesh(self.mesh)

    def clear_results(self) -> None:
        self.results.clear()
        data = self.mesh
        field_names: list[str] = []
        if isinstance(data, pv.MultiBlock):
            try:
                grid = data.combine().cast_to_unstructured_grid()
                field_names.extend(list(grid.point_data.keys()))
                field_names.extend(list(grid.cell_data.keys()))
            except Exception:
                pass
        else:
            field_names.extend(list(getattr(data, 'point_data', {}).keys()))
            field_names.extend(list(getattr(data, 'cell_data', {}).keys()))
        for name in list(field_names):
            if any(tok in name for tok in ('@', 'U', 'stress', 'yield', 'eq_plastic', 'von_mises', 'R_struct', 'X0', 'Z0')):
                try:
                    if isinstance(data, pv.MultiBlock):
                        grid = data.combine().cast_to_unstructured_grid()
                        if name in grid.point_data:
                            del grid.point_data[name]
                        if name in grid.cell_data:
                            del grid.cell_data[name]
                    else:
                        if name in data.point_data:
                            del data.point_data[name]
                        if name in data.cell_data:
                            del data.cell_data[name]
                except Exception:
                    pass

    def add_result(self, result: ResultField) -> None:
        self.results = [r for r in self.results if not (r.name == result.name and r.stage == result.stage)]
        self.results.append(result)
        self.apply_result_to_mesh(result)

    def add_material(self, region_name: str, material_name: str, **parameters: Any) -> None:
        self.set_material(region_name, material_name, **parameters)

    def set_material(self, region_name: str, material_name: str, **parameters: Any) -> None:
        existing = self.material_for_region(region_name)
        payload = dict(parameters)
        if existing is None:
            self.materials.append(MaterialBinding(region_name=region_name, material_name=material_name, parameters=payload))
        else:
            existing.material_name = material_name
            existing.parameters = payload

    def assign_material_definition(self, region_names: Iterable[str], definition_name: str) -> None:
        definition = self.material_definition(definition_name)
        if definition is None:
            raise KeyError(f'Material definition not found: {definition_name}')
        for region_name in region_names:
            self.set_material(region_name, definition.model_type, **definition.parameters)
            binding = self.material_for_region(region_name)
            if binding is not None:
                binding.metadata['library_name'] = definition.name

    def remove_material(self, region_name: str) -> None:
        self.materials = [m for m in self.materials if m.region_name != region_name]

    def upsert_material_definition(self, definition: MaterialDefinition) -> None:
        for idx, item in enumerate(self.material_library):
            if item.name == definition.name:
                self.material_library[idx] = definition
                return
        self.material_library.append(definition)

    def material_definition(self, name: str) -> MaterialDefinition | None:
        for item in self.material_library:
            if item.name == name:
                return item
        return None

    def remove_material_definition(self, name: str) -> None:
        self.material_library = [m for m in self.material_library if m.name != name]

    def add_region(self, name: str, cell_ids: Iterable[int], **metadata: Any) -> None:
        arr = np.asarray(list(cell_ids), dtype=np.int64)
        self.region_tags.append(RegionTag(name=name, cell_ids=arr, metadata=metadata))

    def rename_region(self, old_name: str, new_name: str) -> None:
        if not new_name or old_name == new_name:
            return
        for region in self.region_tags:
            if region.name == old_name:
                region.name = new_name
        for mat in self.materials:
            if mat.region_name == old_name:
                mat.region_name = new_name
        for obj in self.object_records:
            if obj.region_name == old_name:
                obj.region_name = new_name
        for stage in self.stages:
            stage.activate_regions = tuple(new_name if r == old_name else r for r in stage.activate_regions)
            stage.deactivate_regions = tuple(new_name if r == old_name else r for r in stage.deactivate_regions)

    def add_boundary_condition(self, bc: BoundaryCondition) -> None:
        self.boundary_conditions.append(bc)

    def add_stage(self, stage: AnalysisStage) -> None:
        self.stages.append(stage)

    def upsert_stage(self, stage: AnalysisStage) -> None:
        for idx, item in enumerate(self.stages):
            if item.name == stage.name:
                self.stages[idx] = stage
                return
        self.stages.append(stage)

    def remove_stage(self, stage_name: str) -> None:
        self.stages = [s for s in self.stages if s.name != stage_name]

    def add_structure(self, structure: StructuralElementDefinition) -> None:
        self.structures.append(structure)

    def add_interface(self, interface: InterfaceDefinition) -> None:
        self.interfaces.append(interface)

    def add_object_record(self, record: GeometryObjectRecord) -> None:
        self.object_records.append(record)

    def assign_objects_to_region(self, object_keys: Iterable[str], region_name: str, create_region: bool = False) -> None:
        keys = set(object_keys)
        if not keys:
            return
        for item in self.object_records:
            if item.key in keys:
                item.region_name = region_name
        if create_region and self.get_region(region_name) is None:
            self.region_tags.append(RegionTag(name=region_name, cell_ids=np.asarray([], dtype=np.int64), metadata={'source': 'object_assignment'}))


    def set_object_visibility(self, object_keys: Iterable[str], visible: bool, pickable: bool | None = None) -> None:
        keys = set(object_keys)
        for item in self.object_records:
            if item.key in keys:
                item.visible = bool(visible)
                if pickable is None:
                    item.pickable = bool(visible) and (not item.locked)
                else:
                    item.pickable = bool(pickable) and (not item.locked)

    def set_object_locked(self, object_keys: Iterable[str], locked: bool) -> None:
        keys = set(object_keys)
        for item in self.object_records:
            if item.key in keys:
                item.locked = bool(locked)
                if item.locked:
                    item.pickable = False
                elif item.visible:
                    item.pickable = True

    def show_all_objects(self) -> None:
        for item in self.object_records:
            item.visible = True
            item.pickable = not item.locked

    def visible_object_keys(self) -> set[str]:
        return {item.key for item in self.object_records if item.visible}

    def pickable_object_keys(self) -> set[str]:
        return {item.key for item in self.object_records if item.pickable and item.visible and not item.locked}

    def translate_object_blocks(self, object_keys: Iterable[str], offset: tuple[float, float, float]) -> int:
        """Translate selected object-backed blocks in-place.

        This starter implementation supports MultiBlock-backed scene objects where
        records keep a source_block name. It is intended for interactive micro-
        adjustment from the 3D view/inspector without deleting or recreating the
        object. Returns the number of translated blocks.
        """
        if not isinstance(self.mesh, pv.MultiBlock):
            return 0
        keys = {str(k) for k in object_keys}
        if not keys:
            return 0
        vec = np.asarray(offset, dtype=float).reshape(1, 3)
        moved = 0
        for rec in self.object_records:
            if rec.key not in keys:
                continue
            candidates = [rec.source_block, rec.key, rec.name]
            block = None
            chosen_name = None
            for name in candidates:
                if not name:
                    continue
                try:
                    if name in self.mesh.keys():
                        block = self.mesh[name]
                        chosen_name = name
                        break
                except Exception:
                    continue
            if block is None:
                continue
            try:
                pts = np.asarray(block.points)
                if pts.size == 0:
                    continue
                block.points = pts + vec
                rec.metadata['translation'] = [float(x) for x in (np.asarray(rec.metadata.get('translation', [0.0, 0.0, 0.0]), dtype=float) + vec.ravel())]
                moved += 1
                # keep some discoverable hint on the block itself for debugging/export
                try:
                    block.field_data['translation'] = np.asarray(rec.metadata['translation'], dtype=float)
                except Exception:
                    pass
            except Exception:
                continue
        return moved

    def set_object_role(self, object_keys: Iterable[str], role: str) -> None:
        keys = set(object_keys)
        for item in self.object_records:
            if item.key in keys:
                item.metadata['role'] = role

    def merge_regions(self, region_names: Iterable[str], target_name: str) -> None:
        names = [name for name in dict.fromkeys(region_names) if name]
        if not names:
            return
        target_name = target_name or names[0]
        merged_cells: list[np.ndarray] = []
        merged_meta: dict[str, Any] = {'merged_from': names}
        kept: list[RegionTag] = []
        for region in self.region_tags:
            if region.name in names:
                merged_cells.append(np.asarray(region.cell_ids, dtype=np.int64))
                merged_meta.update(region.metadata)
            else:
                kept.append(region)
        merged = np.unique(np.concatenate(merged_cells)) if merged_cells else np.asarray([], dtype=np.int64)
        kept.append(RegionTag(name=target_name, cell_ids=merged, metadata=merged_meta))
        self.region_tags = kept
        for obj in self.object_records:
            if obj.region_name in names:
                obj.region_name = target_name
        for mat in self.materials:
            if mat.region_name in names:
                mat.region_name = target_name
        dedup: dict[str, MaterialBinding] = {}
        for mat in self.materials:
            dedup[mat.region_name] = mat
        self.materials = list(dedup.values())
        for stage in self.stages:
            stage.activate_regions = tuple(target_name if r in names else r for r in stage.activate_regions)
            stage.deactivate_regions = tuple(target_name if r in names else r for r in stage.deactivate_regions)

    def object_record(self, key: str) -> GeometryObjectRecord | None:
        for item in self.object_records:
            if item.key == key:
                return item
        return None

    def objects_for_region(self, region_name: str) -> list[GeometryObjectRecord]:
        return [obj for obj in self.object_records if obj.region_name == region_name]

    def get_region(self, name: str) -> RegionTag | None:
        self.ensure_regions()
        for region in self.region_tags:
            if region.name == name:
                return region
        return None

    def material_for_region(self, region_name: str) -> MaterialBinding | None:
        for item in self.materials:
            if item.region_name == region_name:
                return item
        return None

    def stage_by_name(self, name: str) -> AnalysisStage | None:
        for item in self.stages:
            if item.name == name:
                return item
        return None

    def structures_for_stage(self, stage_name: str | None) -> list[StructuralElementDefinition]:
        if stage_name is None:
            return list(self.structures)
        out = []
        for item in self.structures:
            if not item.active_stages or stage_name in item.active_stages:
                out.append(item)
        return out

    def interfaces_for_stage(self, stage_name: str | None) -> list[InterfaceDefinition]:
        if stage_name is None:
            return list(self.interfaces)
        out = []
        for item in self.interfaces:
            if not item.active_stages or stage_name in item.active_stages:
                out.append(item)
        return out

    def list_result_labels(self) -> list[str]:
        labels: list[str] = []
        for field in self.results:
            label = field.name if field.stage is None else f"{field.name}@{field.stage}"
            if label not in labels:
                labels.append(label)
        return labels

    def list_result_base_names(self) -> list[str]:
        out: list[str] = []
        for field in self.results:
            if field.name not in out:
                out.append(field.name)
        return out

    def list_stages(self) -> list[str]:
        names: list[str] = []
        for field in self.results:
            if field.stage and field.stage not in names:
                names.append(field.stage)
        if not names:
            names = [stage.name for stage in self.stages]
        return names

    def results_for_stage(self, stage: str | None) -> list[ResultField]:
        return [field for field in self.results if field.stage == stage]

    def result_lookup(self) -> dict[str, ResultField]:
        out: dict[str, ResultField] = {}
        for field in self.results:
            key = field.name if field.stage is None else f"{field.name}@{field.stage}"
            out[key] = field
        return out

    def field_for(self, field_name: str, stage_name: str | None = None) -> ResultField | None:
        for field in self.results:
            if field.name == field_name and field.stage == stage_name:
                return field
        return None

    def to_unstructured_grid(self) -> pv.UnstructuredGrid:
        data = self.mesh
        if isinstance(data, pv.MultiBlock):
            return data.combine().cast_to_unstructured_grid()
        return data.cast_to_unstructured_grid() if hasattr(data, 'cast_to_unstructured_grid') else data

    def apply_result_to_mesh(self, result: ResultField) -> None:
        stage_suffix = f"@{result.stage}" if result.stage else ''
        name = f"{result.name}{stage_suffix}"
        grid = self.to_unstructured_grid()
        if result.association == 'point':
            grid.point_data[name] = result.values
        else:
            grid.cell_data[name] = result.values

    def result_stage_names(self) -> list[str]:
        names = [s.name for s in self.stages]
        for r in self.results:
            if r.stage and r.stage not in names:
                names.append(r.stage)
        return names
