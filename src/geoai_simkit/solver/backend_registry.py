from __future__ import annotations

"""Default solver backend registry."""

from geoai_simkit.adapters import ContactInterfaceCPUSolverBackend, LinearStaticCPUSolverBackend, NonlinearMohrCoulombCPUSolverBackend, ReferenceCPUSolverBackend, SolidLinearStaticCPUSolverBackend, StagedMohrCoulombCPUSolverBackend
from geoai_simkit.contracts import SolverBackend, SolverBackendRegistry

_DEFAULT_REGISTRY: SolverBackendRegistry | None = None


def get_default_solver_backend_registry() -> SolverBackendRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = SolverBackendRegistry()
        registry.register(ReferenceCPUSolverBackend())
        registry.register(LinearStaticCPUSolverBackend())
        registry.register(SolidLinearStaticCPUSolverBackend())
        registry.register(NonlinearMohrCoulombCPUSolverBackend())
        registry.register(StagedMohrCoulombCPUSolverBackend())
        registry.register(ContactInterfaceCPUSolverBackend())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def register_solver_backend(backend: SolverBackend, *, replace: bool = False) -> None:
    get_default_solver_backend_registry().register(backend, replace=replace)


def solver_backend_capabilities() -> list[dict[str, object]]:
    return get_default_solver_backend_registry().capabilities()


__all__ = ["get_default_solver_backend_registry", "register_solver_backend", "solver_backend_capabilities"]
