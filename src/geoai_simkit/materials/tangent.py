from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from geoai_simkit.materials.base import MaterialState


@dataclass(frozen=True, slots=True)
class ConsistentTangentConfig:
    """Controls the local algorithmic tangent evaluation.

    The finite-difference path is intentionally local to the constitutive update:
    it differentiates the return-mapping stress update with respect to a strain
    increment.  This gives the global Newton solver a material-consistent tangent
    even for compact material models that do not yet expose a closed-form Jacobian.
    """

    perturbation: float = 1.0e-7
    central_difference: bool = True
    symmetrize: bool = True
    min_diagonal_ratio: float = 1.0e-10
    max_condition_number: float = 1.0e14


def _clone_state(state: MaterialState) -> MaterialState:
    return MaterialState(
        stress=np.asarray(state.stress, dtype=float).reshape(6).copy(),
        strain=np.asarray(state.strain, dtype=float).reshape(6).copy(),
        plastic_strain=np.asarray(state.plastic_strain, dtype=float).reshape(6).copy(),
        internal={**dict(state.internal or {})},
    )


def _safe_update_stress(model: Any, dstrain: np.ndarray, state: MaterialState) -> np.ndarray:
    trial = model.update(np.asarray(dstrain, dtype=float).reshape(6), _clone_state(state))
    return np.asarray(trial.stress, dtype=float).reshape(6)


def algorithmic_tangent_matrix(
    model: Any,
    state: MaterialState,
    *,
    config: ConsistentTangentConfig | None = None,
    fallback: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return a local algorithmic tangent for ``model.update``.

    The method first honors a material-provided ``consistent_tangent_matrix``. If
    the material does not provide one, it uses a bounded finite-difference
    derivative of the stress update at the current material state.
    """

    cfg = config or ConsistentTangentConfig()
    meta: dict[str, Any] = {
        'source': 'finite_difference_update',
        'central_difference': bool(cfg.central_difference),
        'perturbation': float(cfg.perturbation),
        'regularized': False,
    }
    direct = getattr(model, 'consistent_tangent_matrix', None)
    if callable(direct):
        try:
            D = np.asarray(direct(state), dtype=float).reshape(6, 6)
            if np.all(np.isfinite(D)):
                meta['source'] = 'material_consistent_tangent_matrix'
                return _regularize_tangent(D, cfg, fallback=fallback, meta=meta), meta
        except Exception as exc:
            meta['direct_error'] = str(exc)

    h_base = max(float(cfg.perturbation), 1.0e-12)
    stress0 = np.asarray(state.stress, dtype=float).reshape(6)
    D = np.zeros((6, 6), dtype=float)
    for j in range(6):
        h = h_base * max(1.0, abs(float(np.asarray(state.strain, dtype=float).reshape(6)[j])))
        inc = np.zeros(6, dtype=float)
        inc[j] = h
        try:
            if cfg.central_difference:
                sp = _safe_update_stress(model, inc, state)
                sm = _safe_update_stress(model, -inc, state)
                D[:, j] = (sp - sm) / (2.0 * h)
            else:
                sp = _safe_update_stress(model, inc, state)
                D[:, j] = (sp - stress0) / h
        except Exception as exc:
            meta.setdefault('column_errors', []).append({'column': int(j), 'message': str(exc)})
            if fallback is not None:
                D[:, j] = np.asarray(fallback, dtype=float).reshape(6, 6)[:, j]
    return _regularize_tangent(D, cfg, fallback=fallback, meta=meta), meta


def _regularize_tangent(
    D: np.ndarray,
    cfg: ConsistentTangentConfig,
    *,
    fallback: np.ndarray | None,
    meta: dict[str, Any],
) -> np.ndarray:
    out = np.asarray(D, dtype=float).reshape(6, 6)
    if cfg.symmetrize:
        out = 0.5 * (out + out.T)
    if not np.all(np.isfinite(out)):
        if fallback is None:
            out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
        else:
            out = np.asarray(fallback, dtype=float).reshape(6, 6).copy()
            meta['regularized'] = True
            meta['regularization_reason'] = 'non_finite_entries'
    try:
        cond = float(np.linalg.cond(out))
    except Exception:
        cond = float('inf')
    min_diag = float(np.max(np.abs(np.diag(out))) if out.size else 1.0) * float(cfg.min_diagonal_ratio)
    if not np.isfinite(cond) or cond > float(cfg.max_condition_number):
        eye = np.eye(6, dtype=float) * max(min_diag, 1.0e-9)
        if fallback is not None:
            out = 0.98 * out + 0.02 * np.asarray(fallback, dtype=float).reshape(6, 6)
        out = out + eye
        meta['regularized'] = True
        meta['condition_number_before_regularization'] = cond
    meta['condition_number'] = float(np.linalg.cond(out)) if np.all(np.isfinite(out)) else float('inf')
    return out


__all__ = ['ConsistentTangentConfig', 'algorithmic_tangent_matrix']
