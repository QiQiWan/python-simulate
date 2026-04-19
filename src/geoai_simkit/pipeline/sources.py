from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyvista as pv

from geoai_simkit.geometry.ifc_import import IfcImportOptions, IfcImporter
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.pipeline.specs import GeometrySource

GeometryFactory = Callable[[dict[str, Any]], pv.DataSet | pv.MultiBlock]

_GEOMETRY_SOURCE_REGISTRY: dict[str, GeometryFactory] = {}


def register_geometry_source(kind: str, factory: GeometryFactory) -> None:
    key = str(kind).strip().lower()
    if not key:
        raise ValueError('Geometry source kind must be non-empty.')
    _GEOMETRY_SOURCE_REGISTRY[key] = factory


def registered_geometry_sources() -> tuple[str, ...]:
    return tuple(sorted(_GEOMETRY_SOURCE_REGISTRY))


def resolve_registered_geometry_source(kind: str, parameters: dict[str, Any] | None = None) -> pv.DataSet | pv.MultiBlock:
    key = str(kind).strip().lower()
    try:
        factory = _GEOMETRY_SOURCE_REGISTRY[key]
    except KeyError as exc:
        raise ValueError(f'Unknown geometry source kind: {kind!r}. Registered kinds: {", ".join(registered_geometry_sources()) or "<none>"}') from exc
    return factory(dict(parameters or {}))


def geometry_source_from_mesh(data: pv.DataSet | pv.MultiBlock, **metadata) -> GeometrySource:
    return GeometrySource(data=data, metadata=dict(metadata), kind='mesh_data')


def geometry_source_from_mesh_file(path: str | Path, **metadata) -> GeometrySource:
    path = Path(path)
    return GeometrySource(kind='mesh_file', parameters={'path': str(path)}, metadata={'source': 'mesh_file', 'path': str(path), **dict(metadata)})


def geometry_source_from_ifc(path: str | Path, options: IfcImportOptions | None = None, **metadata) -> GeometrySource:
    path = Path(path)
    params: dict[str, Any] = {'path': str(path)}
    if options is not None:
        params['options'] = options
    return GeometrySource(kind='ifc_file', parameters=params, metadata={'source': 'ifc', 'path': str(path), **dict(metadata)})


def geometry_source_from_parametric_pit(**parameters: Any) -> GeometrySource:
    return GeometrySource(kind='parametric_pit', parameters=dict(parameters), metadata={'source': 'parametric_pit', **({} if not parameters else {'parameters': dict(parameters)})})


def _mesh_file_factory(parameters: dict[str, Any]) -> pv.DataSet | pv.MultiBlock:
    path = Path(parameters.get('path') or '')
    if not str(path):
        raise ValueError('mesh_file geometry source requires a path parameter.')
    return pv.read(path)


def _ifc_file_factory(parameters: dict[str, Any]) -> pv.DataSet | pv.MultiBlock:
    path = Path(parameters.get('path') or '')
    if not str(path):
        raise ValueError('ifc_file geometry source requires a path parameter.')
    options = parameters.get('options')
    if options is not None and not isinstance(options, IfcImportOptions):
        options = IfcImportOptions(**dict(options))
    return IfcImporter(path, options).load_model_data()[0]


def _parametric_pit_factory(parameters: dict[str, Any]) -> pv.DataSet | pv.MultiBlock:
    return ParametricPitScene(**dict(parameters)).build()


register_geometry_source('mesh_file', _mesh_file_factory)
register_geometry_source('ifc_file', _ifc_file_factory)
register_geometry_source('parametric_pit', _parametric_pit_factory)
