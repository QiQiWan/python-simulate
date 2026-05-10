"""Core finite-element namespace.

This package is the stable mental model for the ordinary FEM workflow:
geometry -> mesh -> material -> element -> assembly -> solver -> result.
Advanced GPU/OCC/UQ experiments live under :mod:`geoai_simkit.advanced` and
:mod:`geoai_simkit.research` instead of being mixed into the core FEM path.
"""
from .registry import CORE_FEM_MODULES, FEMModuleStatus, core_fem_matrix, core_fem_navigation_cards

__all__ = ["CORE_FEM_MODULES", "FEMModuleStatus", "core_fem_matrix", "core_fem_navigation_cards"]

from .api import FEMAPIContract, get_core_fem_api_contracts, run_core_fem_api_smoke

__all__ = [*__all__, 'FEMAPIContract', 'get_core_fem_api_contracts', 'run_core_fem_api_smoke']

from .linear_static import LinearElasticMaterial, SparseLinearStaticResult, run_hex8_linear_patch_benchmark, solve_sparse_linear_static

__all__ = [
    *__all__,
    "LinearElasticMaterial",
    "SparseLinearStaticResult",
    "run_hex8_linear_patch_benchmark",
    "solve_sparse_linear_static",
]
