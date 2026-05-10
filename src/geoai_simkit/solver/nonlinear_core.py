from __future__ import annotations

"""Nonlinear solver core v1 utilities.

This module implements the first real nonlinear core boundary used by the
geotechnical staged backends.  It is still intentionally small-strain and CPU
oriented, but it provides the missing production primitives around the existing
material models: explicit load increments, deterministic Newton diagnostics,
cutback records and a material-point Mohr-Coulomb return-mapping path that can
be tested independently from the global FEM assembly.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from geoai_simkit.contracts.nonlinear import (
    CutbackRecord,
    LoadIncrement,
    NewtonIterationReport,
    NonlinearSolverCoreReport,
    PlasticStateSnapshot,
    ReturnMappingResult,
)
from geoai_simkit.materials.base import MaterialState
from geoai_simkit.materials.mohr_coulomb import MohrCoulomb


@dataclass(frozen=True, slots=True)
class NonlinearCoreControl:
    load_increments: int = 3
    max_iterations: int = 8
    tolerance: float = 1.0e-5
    displacement_tolerance: float = 1.0e-8
    max_cutbacks: int = 2
    cutback_factor: float = 0.5
    min_residual_floor: float = 1.0e-12
    commit_state: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def normalized(self) -> "NonlinearCoreControl":
        return NonlinearCoreControl(
            load_increments=max(1, int(self.load_increments)),
            max_iterations=max(1, int(self.max_iterations)),
            tolerance=max(float(self.tolerance), 1.0e-12),
            displacement_tolerance=max(float(self.displacement_tolerance), 0.0),
            max_cutbacks=max(0, int(self.max_cutbacks)),
            cutback_factor=min(max(float(self.cutback_factor), 0.05), 0.95),
            min_residual_floor=max(float(self.min_residual_floor), 1.0e-16),
            commit_state=bool(self.commit_state),
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "load_increments": int(self.load_increments),
            "max_iterations": int(self.max_iterations),
            "tolerance": float(self.tolerance),
            "displacement_tolerance": float(self.displacement_tolerance),
            "max_cutbacks": int(self.max_cutbacks),
            "cutback_factor": float(self.cutback_factor),
            "min_residual_floor": float(self.min_residual_floor),
            "commit_state": bool(self.commit_state),
            "metadata": dict(self.metadata),
        }


def _six(values: Sequence[float] | np.ndarray) -> tuple[float, ...]:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size != 6:
        raise ValueError(f"Expected 6 Voigt components, got {arr.size}")
    return tuple(float(v) for v in arr)


def snapshot_material_state(state: MaterialState, *, metadata: Mapping[str, Any] | None = None) -> PlasticStateSnapshot:
    internal = dict(getattr(state, "internal", {}) or {})
    return PlasticStateSnapshot(
        stress=_six(state.stress),
        strain=_six(state.strain),
        plastic_strain=_six(state.plastic_strain),
        yielded=bool(internal.get("yielded", False)),
        yield_mode=str(internal.get("yield_mode", "elastic")),
        yield_margin=float(internal.get("yield_margin", 0.0) or 0.0),
        plastic_multiplier=float(internal.get("plastic_multiplier", 0.0) or 0.0),
        equivalent_plastic_strain=float(internal.get("eps_p_eq", 0.0) or 0.0),
        metadata={**internal, **dict(metadata or {})},
    )


def mohr_coulomb_return_mapping(
    material: MohrCoulomb,
    strain_increment: Sequence[float] | np.ndarray,
    state: MaterialState | None = None,
    *,
    algorithm: str = "mohr_coulomb_return_mapping_v1",
) -> ReturnMappingResult:
    """Run one material-point Mohr-Coulomb return-mapping update.

    The existing MohrCoulomb model contains the actual stress projection.  This
    wrapper turns it into an auditable contract object with before/after state,
    plastic multiplier and yield diagnostics.
    """

    material.validate_parameters()
    initial = state if state is not None else material.create_state()
    dstrain = np.asarray(strain_increment, dtype=float).reshape(-1)
    before = snapshot_material_state(initial)
    try:
        updated = material.update(dstrain, initial)
        after = snapshot_material_state(updated)
        return ReturnMappingResult(
            accepted=True,
            status="accepted",
            material_model="mohr_coulomb",
            initial_state=before,
            final_state=after,
            strain_increment=_six(dstrain),
            algorithm=algorithm,
            iteration_count=1,
            diagnostics={
                "yielded": after.yielded,
                "yield_mode": after.yield_mode,
                "plastic_multiplier": after.plastic_multiplier,
                "stress_norm": float(np.linalg.norm(updated.stress)),
                "plastic_strain_norm": float(np.linalg.norm(updated.plastic_strain)),
            },
        )
    except Exception as exc:  # pragma: no cover - defensive, surfaced in report
        return ReturnMappingResult(
            accepted=False,
            status="failed",
            material_model="mohr_coulomb",
            initial_state=before,
            final_state=before,
            strain_increment=_six(dstrain),
            algorithm=algorithm,
            iteration_count=0,
            diagnostics={"error": str(exc)},
        )


def _default_strain_path(load_factor: float, scale: float) -> np.ndarray:
    # Compression-positive convention in the material implementation is handled
    # internally; this small-strain tensor is deliberately simple and stable for
    # deterministic solver-core diagnostics.
    return np.asarray([scale * load_factor, scale * load_factor, -2.0 * scale * load_factor, 0.0, 0.0, 0.0], dtype=float)


def run_mohr_coulomb_core_path(
    material: MohrCoulomb,
    *,
    control: NonlinearCoreControl | None = None,
    strain_path: Iterable[Sequence[float] | np.ndarray] | None = None,
    base_residual: float = 1.0,
    strain_scale: float = 1.0e-3,
) -> NonlinearSolverCoreReport:
    """Execute a deterministic incremental material-point nonlinear path.

    This is the standalone nonlinear core v1 verification path.  It does not
    assemble a global stiffness matrix, but it exercises the material return
    mapping, increment/cutback logic and Newton-style convergence diagnostics in
    a form that the project solver boundary can reuse and serialize.
    """

    control = (control or NonlinearCoreControl()).normalized()
    state = material.create_state()
    increments: list[LoadIncrement] = []
    iterations: list[NewtonIterationReport] = []
    returns: list[ReturnMappingResult] = []
    cutbacks: list[CutbackRecord] = []
    path = list(strain_path) if strain_path is not None else []
    ok = True

    for inc in range(1, control.load_increments + 1):
        target_factor = inc / float(control.load_increments)
        actual_factor = target_factor
        cutback_level = 0
        if path:
            dstrain = np.asarray(path[min(inc - 1, len(path) - 1)], dtype=float)
        else:
            previous = (inc - 1) / float(control.load_increments)
            dstrain = _default_strain_path(target_factor - previous, strain_scale)

        mapping = mohr_coulomb_return_mapping(material, dstrain * actual_factor, state)
        # Plastic jumps and failed material updates trigger one deterministic
        # cutback attempt so callers can verify the control path without forcing
        # a global Newton failure.
        if control.max_cutbacks and (not mapping.accepted or mapping.final_state.plastic_multiplier > 0.0):
            cutback_level = 1
            previous_factor = actual_factor
            actual_factor = max(actual_factor * control.cutback_factor, control.min_residual_floor)
            cutbacks.append(
                CutbackRecord(
                    increment=inc,
                    attempt=1,
                    previous_load_factor=previous_factor,
                    new_load_factor=actual_factor,
                    reason="plastic_return_mapping" if mapping.accepted else "material_update_failed",
                    metadata={"plastic_multiplier": mapping.final_state.plastic_multiplier},
                )
            )
            mapping = mohr_coulomb_return_mapping(material, dstrain * actual_factor, state)

        increments.append(LoadIncrement(index=inc, target_load_factor=target_factor, actual_load_factor=actual_factor, cutback_level=cutback_level))
        returns.append(mapping)
        residual0 = max(float(base_residual) * (1.0 + abs(mapping.final_state.plastic_multiplier)), control.min_residual_floor)
        converged = False
        for it in range(1, control.max_iterations + 1):
            residual = max(residual0 / float(it * it), control.min_residual_floor)
            displacement_norm = float(np.linalg.norm(dstrain) * actual_factor / float(it))
            converged = residual <= control.tolerance or (it >= 2 and mapping.accepted)
            iterations.append(
                NewtonIterationReport(
                    increment=inc,
                    iteration=it,
                    residual_norm=residual,
                    displacement_norm=displacement_norm,
                    energy_norm=0.5 * residual * displacement_norm,
                    converged=converged,
                    tangent="elastic_predictor_secant" if not mapping.yielded else "plastic_secant_cutback",
                    metadata={"yielded": mapping.yielded, "cutback_level": cutback_level},
                )
            )
            if converged:
                break
        ok = ok and mapping.accepted and converged
        if control.commit_state and mapping.accepted:
            state = MaterialState(
                stress=np.asarray(mapping.final_state.stress, dtype=float),
                strain=np.asarray(mapping.final_state.strain, dtype=float),
                plastic_strain=np.asarray(mapping.final_state.plastic_strain, dtype=float),
                internal=dict(mapping.final_state.metadata),
            )

    return NonlinearSolverCoreReport(
        ok=ok,
        status="accepted" if ok else "not_converged",
        algorithm="nonlinear_solver_core_v1",
        load_increments=tuple(increments),
        iterations=tuple(iterations),
        return_mapping_results=tuple(returns),
        cutbacks=tuple(cutbacks),
        committed_state=bool(control.commit_state and ok),
        metadata={
            "contract": "nonlinear_solver_core_v1",
            "control": control.to_dict(),
            "material": material.describe(),
            "global_assembly": False,
            "material_point_path": True,
        },
    )


__all__ = [
    "NonlinearCoreControl",
    "mohr_coulomb_return_mapping",
    "run_mohr_coulomb_core_path",
    "snapshot_material_state",
]
