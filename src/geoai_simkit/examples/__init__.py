"""Example builders for GeoAI SimKit.

Keep this package import lightweight. Heavy examples may import PyVista/Gmsh and
should be imported from their concrete modules when needed.
"""
from __future__ import annotations

from typing import Any


def build_foundation_pit_showcase_case(*args: Any, **kwargs: Any):
    """Lazy compatibility wrapper for the original showcase builder."""
    from geoai_simkit.examples.foundation_pit_showcase import build_foundation_pit_showcase_case as _impl

    return _impl(*args, **kwargs)


__all__ = ['build_foundation_pit_showcase_case']

from .verified_3d import build_multi_region_project, build_tetra_column_project, run_verified_multi_region, run_verified_tetra_column, write_tetra_stl
