from __future__ import annotations

import json
import multiprocessing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
try:
    import pyvista as pv
except ModuleNotFoundError:  # pragma: no cover
    class _DummyPolyData:
        def __init__(self, *args, **kwargs):
            self.field_data = {}
    class _DummyMultiBlock(dict):
        def keys(self):
            return super().keys()
    class _PVStub:
        PolyData = _DummyPolyData
        MultiBlock = _DummyMultiBlock
    pv = _PVStub()

from geoai_simkit.core.model import GeometryObjectRecord
from geoai_simkit.utils import optional_import


@dataclass(slots=True)
class IfcImportOptions:
    include_entities: tuple[str, ...] = ()
    apply_default_materials: bool = True
    store_metadata: bool = True
    region_strategy: str = 'type_and_name'
    use_world_coords: bool = True
    weld_vertices: bool = False
    include_openings: bool = False
    extract_property_sets: bool = True


def _safe_str(value: Any) -> str:
    if value is None:
        return ''
    return str(value)


def _sanitize_name(value: str, fallback: str) -> str:
    text = (value or '').strip()
    if not text:
        text = fallback
    text = text.replace('/', '_').replace('\\', '_').replace('|', '_')
    return text[:120]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


class IfcImporter:
    def __init__(self, path: str | Path, options: IfcImportOptions | None = None) -> None:
        self.path = Path(path)
        self.options = options or IfcImportOptions()

    def _settings(self, geom: Any) -> Any:
        settings = geom.settings()
        settings.set('apply-default-materials', self.options.apply_default_materials)
        if hasattr(settings, 'USE_WORLD_COORDS'):
            settings.set(settings.USE_WORLD_COORDS, self.options.use_world_coords)
        if hasattr(settings, 'WELD_VERTICES'):
            settings.set(settings.WELD_VERTICES, self.options.weld_vertices)
        if hasattr(settings, 'DISABLE_OPENING_SUBTRACTIONS'):
            settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, not self.options.include_openings)
        return settings

    def _region_name(self, entity_type: str, entity_name: str, parent_name: str | None) -> str:
        strategy = self.options.region_strategy
        if strategy == 'ifc_type':
            return _sanitize_name(entity_type, entity_type)
        if strategy == 'storey':
            return _sanitize_name(parent_name or entity_type, entity_type)
        if strategy == 'name':
            return _sanitize_name(entity_name, entity_type)
        return _sanitize_name(f'{entity_type}::{entity_name or parent_name or entity_type}', entity_type)

    def load_mesh_blocks(self):
        blocks, _, _ = self.load_model_data()
        return blocks

    def load_model_data(self):
        ifcopenshell = optional_import('ifcopenshell')
        geom = optional_import('ifcopenshell.geom')
        util_element = optional_import('ifcopenshell.util.element')

        model = ifcopenshell.open(str(self.path))
        settings = self._settings(geom)

        include = None
        if self.options.include_entities:
            include = []
            for entity in self.options.include_entities:
                include.extend(model.by_type(entity))

        worker_count = max(1, min(multiprocessing.cpu_count(), 8))
        iterator = geom.iterator(settings, model, worker_count, include=include)
        blocks = pv.MultiBlock()
        records: list[GeometryObjectRecord] = []
        summary: dict[str, Any] = {'path': str(self.path), 'schema': getattr(model, 'schema', None), 'counts_by_type': {}}
        name_counts: dict[str, int] = {}

        if iterator.initialize():
            while True:
                shape = iterator.get()
                product = model.by_id(shape.id)
                entity_type = getattr(product, 'is_a', lambda: getattr(shape, 'ifc_type', None) or 'IfcProduct')()
                entity_name = _safe_str(getattr(product, 'Name', None) or getattr(shape, 'name', None) or getattr(shape, 'guid', None) or shape.id)
                guid = _safe_str(getattr(product, 'GlobalId', None) or getattr(shape, 'guid', None) or shape.id)
                parent = util_element.get_container(product) if hasattr(util_element, 'get_container') else None
                parent_name = _safe_str(getattr(parent, 'Name', None)) if parent else ''
                region_name = self._region_name(entity_type, entity_name, parent_name)
                name_counts[region_name] = name_counts.get(region_name, 0) + 1
                if name_counts[region_name] > 1:
                    region_name_unique = f'{region_name}#{name_counts[region_name]}'
                else:
                    region_name_unique = region_name

                if not getattr(shape, 'geometry', None) or not getattr(shape.geometry, 'verts', None) or not getattr(shape.geometry, 'faces', None):
                    if not iterator.next():
                        break
                    continue
                verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
                faces = np.asarray(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
                if verts.size == 0 or faces.size == 0:
                    if not iterator.next():
                        break
                    continue
                cells = np.hstack([np.full((faces.shape[0], 1), 3), faces]).ravel()
                poly = pv.PolyData(verts, cells)
                if hasattr(poly, 'clean') and self.options.weld_vertices:
                    poly = poly.clean()
                poly.field_data['region_name'] = np.array([region_name_unique])
                block_key = _sanitize_name(f'{entity_type}/{entity_name or guid}', guid or entity_type)
                if self.options.store_metadata:
                    poly.field_data['object_key'] = np.array([block_key])
                    poly.field_data['ifc_guid'] = np.array([guid])
                    poly.field_data['ifc_type'] = np.array([entity_type])
                    poly.field_data['ifc_name'] = np.array([entity_name])
                    role = ''
                    if 'Wall' in entity_type:
                        role = 'wall'
                    elif 'Slab' in entity_type:
                        role = 'slab'
                    elif 'Beam' in entity_type:
                        role = 'beam'
                    elif 'Column' in entity_type:
                        role = 'column'
                    elif 'Proxy' in entity_type:
                        role = 'soil' if 'Excavation' in entity_name else 'support'
                    if role:
                        poly.field_data['role'] = np.array([role])
                        poly.field_data['suggested_role'] = np.array([role])
                    if parent_name:
                        poly.field_data['ifc_parent'] = np.array([parent_name])

                blocks[block_key] = poly

                properties: dict[str, Any] = {}
                if self.options.extract_property_sets and hasattr(util_element, 'get_psets'):
                    try:
                        properties = _jsonable(util_element.get_psets(product, psets_only=False, qtos_only=False, should_inherit=True))
                    except Exception:
                        properties = {}
                material_names: list[str] = []
                if hasattr(util_element, 'get_material'):
                    try:
                        mat = util_element.get_material(product, should_skip_usage=True)
                        if isinstance(mat, (list, tuple)):
                            material_names = [_safe_str(getattr(m, 'Name', m)) for m in mat]
                        elif mat is not None:
                            material_names = [_safe_str(getattr(mat, 'Name', mat))]
                    except Exception:
                        material_names = []

                bbox_min = verts.min(axis=0).tolist() if verts.size else [0.0, 0.0, 0.0]
                bbox_max = verts.max(axis=0).tolist() if verts.size else [0.0, 0.0, 0.0]
                record = GeometryObjectRecord(
                    key=block_key,
                    name=entity_name or guid,
                    object_type=entity_type,
                    guid=guid,
                    region_name=region_name_unique,
                    source_block=block_key,
                    parent=parent_name or None,
                    metadata={
                        'ifc_id': int(shape.id),
                        'material_names': material_names,
                        'suggested_role': role if 'role' in locals() else '',
                        'bbox_min': bbox_min,
                        'bbox_max': bbox_max,
                        'n_points': int(len(verts)),
                        'n_faces': int(len(faces)),
                    },
                    properties=properties,
                )
                records.append(record)
                summary['counts_by_type'][entity_type] = summary['counts_by_type'].get(entity_type, 0) + 1
                if not iterator.next():
                    break

        summary['n_objects'] = len(records)
        summary['workers'] = worker_count
        summary['region_strategy'] = self.options.region_strategy
        return blocks, records, summary
