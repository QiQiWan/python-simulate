from __future__ import annotations


"""Coarse project module facades.

Use these stable entrypoints when updating one subsystem at a time.  The older
implementation packages remain available for backward compatibility, while new
code should prefer contracts + modules + services.
"""

from .plugin_catalog import module_plugin_catalog, module_plugin_catalog_smoke, validate_plugin_catalog
from .registry import get_project_module, list_project_modules, module_update_map, run_project_module_smokes

__all__ = [
    "get_project_module",
    "list_project_modules",
    "module_plugin_catalog",
    "module_plugin_catalog_smoke",
    "validate_plugin_catalog",
    "module_update_map",
    "run_project_module_smokes",
]
