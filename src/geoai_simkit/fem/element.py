from __future__ import annotations
from .api import CORE_FEM_API_CONTRACTS, run_core_fem_module_smoke
MODULE_KEY = "element"
TARGET_NAMESPACE = "geoai_simkit.solver"
STATUS = "core_fem_facade"
def describe_api() -> dict[str, object]:
    for contract in CORE_FEM_API_CONTRACTS:
        if contract.key == MODULE_KEY: return contract.to_dict()
    raise KeyError(MODULE_KEY)
def smoke_check() -> dict[str, object]: return run_core_fem_module_smoke(MODULE_KEY)
