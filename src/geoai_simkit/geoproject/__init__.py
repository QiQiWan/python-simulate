from __future__ import annotations

from .document import *
from .transaction import DirtyGraph, GeoProjectTransaction, InvalidationGraph, get_dirty_graph, get_invalidation_graph, mark_geoproject_changed


def run_geoproject_incremental_solve(*args, **kwargs):
    """Lazy wrapper so GUI imports do not require NumPy until solving starts."""
    from .runtime_solver import run_geoproject_incremental_solve as _run

    return _run(*args, **kwargs)
