from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from .base import MaterialModel, MaterialState
from .invariants import mc_nphi, mc_npsi, principal_decomposition, reconstruct_from_principal
from .linear_elastic import LinearElastic
from .registry import registry


@dataclass(slots=True)
class MohrCoulomb(MaterialModel):
    E: float
    nu: float
    cohesion: float
    friction_deg: float
    dilation_deg: float = 0.0
    tensile_strength: float = 0.0
    rho: float = 0.0
    name: str = "mohr_coulomb"

    def validate_parameters(self) -> None:
        if self.E <= 0:
            raise ValueError("E must be positive")
        if self.cohesion < 0:
            raise ValueError("cohesion must be non-negative")
        if not (0.0 <= self.friction_deg < 90.0):
            raise ValueError("friction_deg must be in [0, 90)")

    def create_state(self) -> MaterialState:
        return MaterialState(internal={
            "yielded": False,
            "yield_mode": "elastic",
            "eps_p_eq": 0.0,
            "yield_margin": 0.0,
            "plastic_multiplier": 0.0,
            "algorithm": "principal-space-mc-active-set",
            "active_planes": (),
        })

    def _elastic(self) -> LinearElastic:
        return LinearElastic(E=self.E, nu=self.nu, rho=self.rho)

    def tangent_matrix(self, state: MaterialState | None = None) -> np.ndarray:
        Ce = self._elastic().elastic_matrix()
        if state is None or not bool(state.internal.get("yielded", False)):
            return Ce
        mode = str(state.internal.get("yield_mode", "shear-single"))
        out = Ce.copy()
        if mode == "tension":
            out[:3, :3] *= 0.22
            out[3:, 3:] *= 0.45
        elif mode == "shear-apex":
            out[:3, :3] *= 0.20
            out[3:, 3:] *= 0.15
        elif mode == "shear-edge":
            out[:3, :3] *= 0.28
            out[3:, 3:] *= 0.18
        else:
            out[:3, :3] *= 0.35
            out[3:, 3:] *= 0.22
        return out

    @staticmethod
    def _plane_defs(Nphi: float, Npsi: float) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        m = {
            "f12": np.array([1.0, -Nphi, 0.0], dtype=float),
            "f23": np.array([0.0, 1.0, -Nphi], dtype=float),
            "f13": np.array([1.0, 0.0, -Nphi], dtype=float),
        }
        a = {
            "f12": np.array([1.0, -Npsi, 0.0], dtype=float),
            "f23": np.array([0.0, 1.0, -Npsi], dtype=float),
            "f13": np.array([1.0, 0.0, -Npsi], dtype=float),
        }
        return m, a

    def _principal_shear_return(self, sig_c_tr: np.ndarray, Cn: np.ndarray) -> tuple[np.ndarray, str, tuple[str, ...], float]:
        Nphi = mc_nphi(self.friction_deg)
        Npsi = mc_npsi(self.dilation_deg)
        rootN = float(np.sqrt(max(Nphi, 1e-12)))
        cbar = 2.0 * self.cohesion * rootN
        m_defs, a_defs = self._plane_defs(Nphi, Npsi)
        f = {
            "f12": float(sig_c_tr[0] - Nphi * sig_c_tr[1] - cbar),
            "f23": float(sig_c_tr[1] - Nphi * sig_c_tr[2] - cbar),
            "f13": float(sig_c_tr[0] - Nphi * sig_c_tr[2] - cbar),
        }
        fmax = max(f.values())
        if fmax <= 0.0:
            return sig_c_tr.copy(), "elastic", tuple(), 0.0

        ordered_candidates = [k for k, _ in sorted(f.items(), key=lambda kv: kv[1], reverse=True) if f[k] > 0.0]
        tol_act = max(1e-6, 0.05 * fmax)
        active_pref = tuple(k for k in ordered_candidates if f[k] >= fmax - tol_act)
        candidate_sets: list[tuple[str, ...]] = []
        if active_pref:
            candidate_sets.append(active_pref)
        for k in ordered_candidates:
            if (k,) not in candidate_sets:
                candidate_sets.append((k,))
        for r in (2, 3):
            for combo in combinations(ordered_candidates[:3], r):
                if combo not in candidate_sets:
                    candidate_sets.append(combo)

        best = (sig_c_tr.copy(), "shear-single", (ordered_candidates[0],), fmax)
        best_res = np.inf
        for active in candidate_sets:
            A = np.column_stack([a_defs[k] for k in active])
            M = np.vstack([m_defs[k] for k in active])
            ff = np.array([f[k] for k in active], dtype=float)
            H = M @ Cn @ A
            try:
                dg = np.linalg.solve(H + np.eye(len(active)) * 1e-12, ff)
            except np.linalg.LinAlgError:
                dg = np.linalg.lstsq(H + np.eye(len(active)) * 1e-10, ff, rcond=None)[0]
            if np.any(dg < -1e-10):
                continue
            sig_new = sig_c_tr - Cn @ A @ dg
            # preserve ordering in compression-positive principal stresses
            if np.any(np.diff(sig_new) > 1e-8):
                continue
            fres = np.array([sig_new[0] - Nphi * sig_new[1] - cbar,
                             sig_new[1] - Nphi * sig_new[2] - cbar,
                             sig_new[0] - Nphi * sig_new[2] - cbar], dtype=float)
            res = float(np.max(np.maximum(fres, 0.0)))
            if res < best_res:
                mode = "shear-single" if len(active) == 1 else ("shear-edge" if len(active) == 2 else "shear-apex")
                best = (sig_new, mode, tuple(active), float(np.sum(dg)))
                best_res = res
                if res < 1e-7:
                    break
        sig_c_new, mode, active, dgam = best
        return sig_c_new, mode, active, float(dgam)

    def update(self, dstrain: np.ndarray, state: MaterialState) -> MaterialState:
        elastic = self._elastic()
        Ce = elastic.elastic_matrix()
        trial = elastic.update(dstrain, state)
        sigma_trial = np.asarray(trial.stress, dtype=float)
        vals_t, vecs_t = principal_decomposition(sigma_trial)
        sig_c_tr = -vals_t[::-1]
        vecs_c = vecs_t[:, ::-1]

        Nphi = mc_nphi(self.friction_deg)
        rootN = float(np.sqrt(max(Nphi, 1e-12)))
        cbar = 2.0 * self.cohesion * rootN
        f_tr = max(
            sig_c_tr[0] - Nphi * sig_c_tr[1] - cbar,
            sig_c_tr[1] - Nphi * sig_c_tr[2] - cbar,
            sig_c_tr[0] - Nphi * sig_c_tr[2] - cbar,
        )

        new_state = MaterialState(
            stress=sigma_trial.copy(),
            strain=state.strain + np.asarray(dstrain, dtype=float),
            plastic_strain=state.plastic_strain.copy(),
            internal=dict(state.internal),
        )
        new_state.internal["yielded"] = False
        new_state.internal["yield_mode"] = "elastic"
        new_state.internal["yield_margin"] = float(f_tr)
        new_state.internal["plastic_multiplier"] = 0.0
        new_state.internal["active_planes"] = tuple()

        # Tension cutoff on tension-positive principal stresses; supports multi-principal clipping.
        if self.tensile_strength > 0.0 and np.any(vals_t > self.tensile_strength):
            vals_tc = np.minimum(vals_t, self.tensile_strength)
            sigma_cut = reconstruct_from_principal(vals_tc, vecs_t)
            de_el = np.linalg.solve(Ce, sigma_cut - state.stress)
            deps_p = np.asarray(dstrain, dtype=float) - de_el
            new_state.stress = sigma_cut
            new_state.plastic_strain = state.plastic_strain + deps_p
            new_state.internal["yielded"] = True
            new_state.internal["yield_mode"] = "tension"
            new_state.internal["eps_p_eq"] = float(state.internal.get("eps_p_eq", 0.0) + np.linalg.norm(deps_p))
            return new_state

        if f_tr <= 0.0:
            return new_state

        lam = self.E * self.nu / ((1.0 + self.nu) * (1.0 - 2.0 * self.nu))
        mu = self.E / (2.0 * (1.0 + self.nu))
        Cn = np.array([
            [lam + 2.0 * mu, lam, lam],
            [lam, lam + 2.0 * mu, lam],
            [lam, lam, lam + 2.0 * mu],
        ], dtype=float)
        sig_c_new, mode, active, dgamma = self._principal_shear_return(sig_c_tr, Cn)
        if self.tensile_strength > 0.0:
            sig_c_new[2] = max(sig_c_new[2], -self.tensile_strength)
        vals_t_new = -sig_c_new[::-1]
        sigma_new = reconstruct_from_principal(vals_t_new, vecs_c[:, ::-1])

        de_el = np.linalg.solve(Ce, sigma_new - state.stress)
        deps_p = np.asarray(dstrain, dtype=float) - de_el
        new_state.stress = sigma_new
        new_state.plastic_strain = state.plastic_strain + deps_p
        new_state.internal["yielded"] = True
        new_state.internal["yield_mode"] = mode
        new_state.internal["active_planes"] = active
        new_state.internal["plastic_multiplier"] = float(dgamma)
        new_state.internal["eps_p_eq"] = float(state.internal.get("eps_p_eq", 0.0) + np.linalg.norm(deps_p))
        return new_state

    def describe(self) -> dict[str, float]:
        return {
            "E": self.E,
            "nu": self.nu,
            "cohesion": self.cohesion,
            "friction_deg": self.friction_deg,
            "dilation_deg": self.dilation_deg,
            "tensile_strength": self.tensile_strength,
            "rho": self.rho,
        }


registry.register("mohr_coulomb", MohrCoulomb)
