from __future__ import annotations
from typing import Callable
from geoai_simkit.pipeline.specs import GeometrySource
_REGISTRY: dict[str, Callable[..., GeometrySource]] = {}
def geometry_source_from_parametric_pit(**parameters): return GeometrySource(kind='parametric_pit', parameters=dict(parameters))
def geometry_source_from_mesh(mesh=None, **metadata): return GeometrySource(kind='mesh', parameters={'mesh': mesh}, metadata=dict(metadata))
def geometry_source_from_mesh_file(path: str, **metadata): return GeometrySource(kind='mesh_file', path=path, metadata=dict(metadata))
def geometry_source_from_ifc(path: str, **metadata): return GeometrySource(kind='ifc', path=path, metadata=dict(metadata))
def geometry_source_from_editable_blocks(blocks=None, **metadata): return GeometrySource(kind='editable_blocks', parameters={'blocks': blocks or []}, metadata=dict(metadata))
def register_geometry_source(key: str, factory): _REGISTRY[str(key)] = factory; return factory
def registered_geometry_sources(): return dict(_REGISTRY)
def resolve_registered_geometry_source(key: str, **kwargs): return _REGISTRY[str(key)](**kwargs)
