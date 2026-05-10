from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base import MaterialModel, MaterialState
from .invariants import dp_alpha_k_from_mc, dp_beta_from_dilation, mean_pressure_compression, q_invariant
from .registry import registry


@dataclass(slots=True)
class HSS(MaterialModel):
    E50ref: float
    Eoedref: float
    Eurref: float
    nu_ur: float
    pref: float
    m: float
    c: float
    phi_deg: float
    psi_deg: float
    G0ref: float | None = None
    gamma07: float | None = None
    Rf: float = 0.9
    rho: float = 0.0
    name: str = "hss"

    def validate_parameters(self) -> None:
        if min(self.E50ref, self.Eoedref, self.Eurref, self.pref) <= 0:
            raise ValueError("HSS reference stiffness and pref must be positive")
        if self.G0ref is not None and self.G0ref <= 0:
            raise ValueError("G0ref must be positive")
        if self.gamma07 is not None and self.gamma07 <= 0:
            raise ValueError("gamma07 must be positive")

    def create_state(self) -> MaterialState:
        return MaterialState(
            internal={
                "eps_p_shear": 0.0,
                "eps_p_vol": 0.0,
                "eps_p_eq": 0.0,
                "eps_p_cap": 0.0,
                "eps_p_unload": 0.0,
                "p_ref_state": self.pref,
                "q_ref_state": 0.0,
                "p_cap": 1.5 * self.pref,
                "preconsolidation_pressure": 1.5 * self.pref,
                "ocr": 1.5,
                "small_strain_active": self.G0ref is not None,
                "shear_mod_reduction": 1.0,
                "Gsec": self.G0ref if self.G0ref is not None else self.E50ref / (2.0 * (1.0 + self.nu_ur)),
                "E_loading": self.E50ref,
                "E_oedometer": self.Eoedref,
                "E_unloading": self.Eurref,
                "gamma_hist": 0.0,
                "gamma_rev": 0.0,
                "gamma_max": 0.0,
                "yield_margin": 0.0,
                "yielded": False,
                "yield_mode": "elastic",
                "mode_branch": "loading",
                "last_dgamma_s": 0.0,
                "last_dgamma_c": 0.0,
                "last_plastic_multiplier": 0.0,
                "state_schema_version": 2.0,
                "algorithm": "hs-small-dp-cap-consistent-state-v2",
                "backstress": np.zeros(6, dtype=float),
                "plastic_strain_tensor": np.zeros(6, dtype=float),
                "reversal_strain": np.zeros(6, dtype=float),
            }
        )

    def tangent_modulus(self, p_eff: float, mode: str = "loading") -> float:
        p_eff = max(float(p_eff), 1.0)
        if mode == "unloading":
            base = self.Eurref
        elif mode == "oedometer":
            base = self.Eoedref
        else:
            base = self.E50ref
        return base * (p_eff / self.pref) ** self.m

    def _small_strain_reduction(self, gamma_ref: float) -> float:
        if self.G0ref is None or self.gamma07 is None:
            return 1.0
        g = abs(float(gamma_ref))
        return 1.0 / (1.0 + g / self.gamma07)

    def _elastic_constants(self, p_eff: float, reduction: float, mode: str = "loading") -> tuple[float, float, np.ndarray]:
        E_t = max(1e3, self.tangent_modulus(p_eff, mode=mode))
        if self.G0ref is not None:
            Gss = self.G0ref * (max(p_eff, 1.0) / self.pref) ** self.m * reduction
            E_from_G = 2.0 * (1.0 + self.nu_ur) * Gss
            E_t = max(E_t, min(E_from_G, max(self.Eurref * 3.0, E_t)))
        nu = min(max(self.nu_ur, 1.0e-3), 0.49)
        lam = E_t * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
        mu = E_t / (2.0 * (1.0 + nu))
        C = np.array([
            [lam + 2.0 * mu, lam, lam, 0, 0, 0],
            [lam, lam + 2.0 * mu, lam, 0, 0, 0],
            [lam, lam, lam + 2.0 * mu, 0, 0, 0],
            [0, 0, 0, mu, 0, 0],
            [0, 0, 0, 0, mu, 0],
            [0, 0, 0, 0, 0, mu],
        ], dtype=float)
        return lam, mu, C

    def tangent_matrix(self, state: MaterialState | None = None) -> np.ndarray:
        if state is None:
            p_eff = self.pref
            reduction = 1.0
            mode = "loading"
        else:
            p_eff = float(state.internal.get("p_ref_state", self.pref))
            reduction = float(state.internal.get("shear_mod_reduction", 1.0))
            mode = str(state.internal.get("mode_branch", "loading"))
        _, _, C = self._elastic_constants(p_eff, reduction, mode=mode)
        if state is not None and bool(state.internal.get("yielded", False)):
            mode_y = str(state.internal.get("yield_mode", "shear"))
            C = C.copy()
            if mode_y == "cap":
                C[:3, :3] *= 0.45
                C[3:, 3:] *= 0.80
            elif mode_y == "double":
                C[:3, :3] *= 0.35
                C[3:, 3:] *= 0.40
            else:
                C[:3, :3] *= 0.55
                C[3:, 3:] *= 0.45
        return C

    def consistent_tangent_matrix(self, state: MaterialState | None = None) -> np.ndarray:
        C = self.tangent_matrix(state)
        if state is None:
            return C
        internal = dict(state.internal or {})
        mode = str(internal.get("yield_mode", "elastic"))
        if mode == "elastic":
            return C
        p_eff = max(1.0, float(internal.get("p_ref_state", self.pref)))
        reduction = float(internal.get("shear_mod_reduction", 1.0))
        branch = str(internal.get("mode_branch", "loading"))
        _, mu, Ce = self._elastic_constants(p_eff, reduction, mode=branch)
        Kbulk = float((Ce[0, 0] + 2.0 * Ce[0, 1]) / 3.0)
        alpha, _ = dp_alpha_k_from_mc(self.c * self.Rf * (1.0 + 3.0 * float(internal.get("eps_p_shear", 0.0))), self.phi_deg)
        beta = dp_beta_from_dilation(self.psi_deg)
        Hs = max(1.0e-9, 0.15 * self.E50ref * (1.0 + 1.5 * float(internal.get("eps_p_shear", 0.0))))
        Hc = max(1.0e-9, 0.10 * self.Eoedref * (1.0 + 1.0 * float(internal.get("eps_p_vol", 0.0))))
        Ct = Ce.copy()
        if mode in {"shear", "double"}:
            shear_factor = Hs / max(Hs + 3.0 * mu + alpha * beta * Kbulk, 1.0e-12)
            Ct[3:, 3:] *= max(0.05, min(1.0, shear_factor))
            Ct[:3, :3] *= max(0.20, min(1.0, 0.5 + 0.5 * shear_factor))
        if mode in {"cap", "double"}:
            cap_factor = Hc / max(Hc + Kbulk, 1.0e-12)
            Ct[:3, :3] *= max(0.05, min(1.0, cap_factor))
        return 0.5 * (Ct + Ct.T)

    def update(self, dstrain: np.ndarray, state: MaterialState) -> MaterialState:
        dstrain = np.asarray(dstrain, dtype=float)
        gamma_step = float(np.linalg.norm(dstrain[3:]))
        work = float(np.dot(state.stress, dstrain))
        prev_branch = str(state.internal.get("mode_branch", "loading"))
        branch = "unloading" if work < 0.0 else "loading"
        gamma_hist = float(state.internal.get("gamma_hist", 0.0) + gamma_step)
        gamma_rev = float(state.internal.get("gamma_rev", 0.0) + gamma_step) if branch == prev_branch else gamma_step
        gamma_max = max(float(state.internal.get("gamma_max", 0.0)), gamma_hist)
        reduction = self._small_strain_reduction(gamma_rev)
        p_state = float(state.internal.get("p_ref_state", self.pref))
        _, _, C = self._elastic_constants(p_state, reduction, mode=branch)
        sigma_trial = state.stress + C @ dstrain
        p_tr = mean_pressure_compression(sigma_trial)
        q_tr = q_invariant(sigma_trial)
        alpha, k = dp_alpha_k_from_mc(self.c * self.Rf * (1.0 + 3.0 * float(state.internal.get("eps_p_shear", 0.0))), self.phi_deg)
        beta = dp_beta_from_dilation(self.psi_deg)
        p_cap = float(state.internal.get("p_cap", 1.5 * self.pref))
        fs = q_tr + alpha * p_tr - k
        fc = p_tr - p_cap

        internal = dict(state.internal)
        internal["yield_margin"] = float(max(fs, fc))
        internal["yielded"] = False
        internal["yield_mode"] = "elastic"
        internal["gamma_hist"] = gamma_hist
        internal["gamma_rev"] = gamma_rev
        internal["gamma_max"] = gamma_max
        internal["shear_mod_reduction"] = reduction
        internal["mode_branch"] = branch
        internal["E_loading"] = float(self.tangent_modulus(max(1.0, p_tr), mode="loading"))
        internal["E_oedometer"] = float(self.tangent_modulus(max(1.0, p_tr), mode="oedometer"))
        internal["E_unloading"] = float(self.tangent_modulus(max(1.0, p_tr), mode="unloading"))
        internal["Gsec"] = float(C[3, 3])

        if fs <= 0.0 and fc <= 0.0:
            internal["p_ref_state"] = max(1.0, p_tr)
            internal["q_ref_state"] = float(q_tr)
            return MaterialState(
                stress=sigma_trial,
                strain=state.strain + dstrain,
                plastic_strain=state.plastic_strain.copy(),
                internal=internal,
            )

        sdev = sigma_trial.copy()
        sdev[:3] += p_tr
        q_safe = max(q_tr, 1.0e-12)
        n_dev = sdev / q_safe
        Hs = max(1.0e-9, 0.15 * self.E50ref * (1.0 + 1.5 * float(state.internal.get("eps_p_shear", 0.0))))
        Hc = max(1.0e-9, 0.10 * self.Eoedref * (1.0 + 1.0 * float(state.internal.get("eps_p_vol", 0.0))))
        mu_eff = C[3, 3]
        Kbulk = (C[0, 0] + 2.0 * C[0, 1]) / 3.0

        sigma_new = sigma_trial.copy()
        deps_p = np.zeros(6, dtype=float)
        dgamma_s = 0.0
        dgamma_c = 0.0
        mode = "elastic"

        if fs > 0.0:
            denom_s = 3.0 * mu_eff + alpha * beta * Kbulk + Hs
            dgamma_s = fs / max(denom_s, 1.0e-12)
            p_new = p_tr - dgamma_s * beta * Kbulk
            q_new = max(0.0, q_tr - dgamma_s * 3.0 * mu_eff)
            sigma_new = q_new * n_dev
            sigma_new[:3] -= p_new
            mode = "shear"
            deps_p += dgamma_s * np.array([beta / 3.0, beta / 3.0, beta / 3.0, 0.0, 0.0, 0.0])
            deps_p += dgamma_s * n_dev
            p_tr, q_tr = p_new, q_new

        if fc > 0.0 or p_tr > p_cap:
            over = max(fc, p_tr - p_cap)
            denom_c = Kbulk + Hc
            dgamma_c = over / max(denom_c, 1.0e-12)
            p_new = p_tr - dgamma_c * Kbulk
            sigma_new = sigma_new.copy()
            sigma_new[:3] += (p_tr - p_new)
            deps_p += dgamma_c * np.array([1/3, 1/3, 1/3, 0, 0, 0], dtype=float)
            p_tr = p_new
            mode = "double" if mode == "shear" else "cap"
            p_cap = p_cap + dgamma_c * Hc

        try:
            de_el = np.linalg.solve(C, sigma_new - state.stress)
        except np.linalg.LinAlgError:
            de_el = np.linalg.pinv(C) @ (sigma_new - state.stress)
        deps_p = dstrain - de_el if np.linalg.norm(deps_p) < 1e-14 else deps_p
        new_plastic = np.asarray(state.plastic_strain + deps_p, dtype=float).reshape(6)
        internal["yielded"] = True
        internal["yield_mode"] = mode
        internal["eps_p_shear"] = float(state.internal.get("eps_p_shear", 0.0) + abs(dgamma_s))
        internal["eps_p_vol"] = float(state.internal.get("eps_p_vol", 0.0) + abs(dgamma_c) + abs(beta * dgamma_s) * 0.5)
        internal["eps_p_cap"] = float(state.internal.get("eps_p_cap", 0.0) + abs(dgamma_c))
        internal["eps_p_unload"] = float(state.internal.get("eps_p_unload", 0.0) + (gamma_step if branch == "unloading" else 0.0))
        internal["eps_p_eq"] = float(state.internal.get("eps_p_eq", 0.0) + np.linalg.norm(deps_p))
        internal["p_ref_state"] = max(1.0, p_tr)
        internal["q_ref_state"] = float(q_tr)
        internal["p_cap"] = max(p_cap, self.pref)
        internal["preconsolidation_pressure"] = float(internal["p_cap"])
        internal["ocr"] = float(max(1.0, internal["p_cap"] / max(1.0, p_tr)))
        internal["last_dgamma_s"] = float(dgamma_s)
        internal["last_dgamma_c"] = float(dgamma_c)
        internal["last_plastic_multiplier"] = float(abs(dgamma_s) + abs(dgamma_c))
        internal["plastic_strain_tensor"] = new_plastic.copy()
        internal["backstress"] = 0.20 * new_plastic.copy()
        internal["reversal_strain"] = np.asarray(state.strain + dstrain, dtype=float).reshape(6).copy() if branch != prev_branch else np.asarray(state.internal.get("reversal_strain", np.zeros(6)), dtype=float).reshape(6).copy()
        return MaterialState(
            stress=sigma_new,
            strain=state.strain + dstrain,
            plastic_strain=new_plastic,
            internal=internal,
        )

    def describe(self) -> dict[str, float | None]:
        return {
            "E50ref": self.E50ref,
            "Eoedref": self.Eoedref,
            "Eurref": self.Eurref,
            "nu_ur": self.nu_ur,
            "pref": self.pref,
            "m": self.m,
            "c": self.c,
            "phi_deg": self.phi_deg,
            "psi_deg": self.psi_deg,
            "G0ref": self.G0ref,
            "gamma07": self.gamma07,
            "Rf": self.Rf,
            "rho": self.rho,
        }


@dataclass(slots=True)
class HSSmall(HSS):
    name: str = "hs_small"


registry.register("hss", HSS)
registry.register("hs_small", HSSmall)
