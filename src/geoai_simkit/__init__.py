from __future__ import annotations

from importlib import import_module
from typing import Any

from ._version import __version__
from .config import AppConfig

_LAZY_EXPORTS = {
    'SimulationModel': ('geoai_simkit.core.model', 'SimulationModel'),
    'AnalysisCaseBuilder': ('geoai_simkit.pipeline', 'AnalysisCaseBuilder'),
    'AnalysisCaseSpec': ('geoai_simkit.pipeline', 'AnalysisCaseSpec'),
    'GeneralFEMSolver': ('geoai_simkit.pipeline', 'GeneralFEMSolver'),
    'CompileConfig': ('geoai_simkit.runtime', 'CompileConfig'),
    'RuntimeCompiler': ('geoai_simkit.runtime', 'RuntimeCompiler'),
    'RuntimeConfig': ('geoai_simkit.runtime', 'RuntimeConfig'),
    'GeoProjectDocument': ('geoai_simkit.geoproject', 'GeoProjectDocument'),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'geoai_simkit' has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    'AppConfig',
    'SimulationModel',
    'AnalysisCaseBuilder',
    'AnalysisCaseSpec',
    'CompileConfig',
    'GeneralFEMSolver',
    'RuntimeCompiler',
    'RuntimeConfig',
    'GeoProjectDocument',
    '__version__',
]
