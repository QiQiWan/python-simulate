from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

from geoai_simkit.materials.base import MaterialState
from geoai_simkit.materials.hss import HSS, HSSmall
from geoai_simkit.materials.mohr_coulomb import MohrCoulomb
from geoai_simkit.solver.gpu_runtime import choose_cuda_device
from geoai_simkit.solver.linear_algebra import _optional_import
from geoai_simkit.solver.warp_hex8 import BlockSparsePattern, WarpBlockSparseMatrix, block_values_to_csr, build_block_sparse_pattern


@dataclass(slots=True)
class WarpNonlinearConfig:
    enabled: bool = True
    force: bool = False
    min_cells: int = 128
    fallback_to_cpu: bool = True
    mc_surrogate: bool = True


@dataclass(slots=True)
class WarpNonlinearAssemblyInfo:
    enabled: bool
    used: bool
    device: str
    backend: str
    warnings: list[str] = field(default_factory=list)
    element_count: int = 0
    material_family: str = "unsupported"


DEFAULT_WARP_NL_CONFIG = WarpNonlinearConfig()
_WARP_NONLINEAR_FAILURES: dict[str, str] = {}
_WARP_NL_DEVICE_CACHE: dict[tuple[str, tuple[Any, ...]], tuple[Any, ...]] = {}
_WARP_NL_MATERIAL_CACHE: dict[tuple[str, str, tuple[Any, ...]], tuple[Any, ...]] = {}


def _array_signature(arr: np.ndarray) -> tuple[Any, ...]:
    a = np.asarray(arr)
    if a.size == 0:
        return (str(a.dtype), tuple(a.shape), 0.0, 0.0)
    flat = a.reshape(-1)
    head = flat[: min(16, flat.size)]
    tail = flat[-min(16, flat.size):]
    return (str(a.dtype), tuple(a.shape), float(np.sum(head, dtype=np.float64)), float(np.sum(tail, dtype=np.float64)))


def _nl_cache_key(device: str, *arrays: np.ndarray) -> tuple[str, tuple[Any, ...]]:
    return (str(device), tuple(_array_signature(a) for a in arrays))




def _material_signature(materials: list[Any], family: str) -> tuple[Any, ...]:
    sig: list[Any] = [family, len(materials)]
    if family == "hss":
        for m in materials:
            sig.extend([float(m.E50ref), float(m.Eoedref), float(m.Eurref), float(m.nu_ur), float(m.pref), float(m.m), float(m.c), float(m.phi_deg), float(m.psi_deg), float(m.G0ref or 0.0), float(m.gamma07 or 0.0), float(m.Rf)])
    elif family == "mohr-coulomb":
        for m in materials:
            sig.extend([float(m.E), float(m.nu), float(m.cohesion), float(m.friction_deg), float(m.dilation_deg)])
    return tuple(sig)


def _prune_small_cache(cache: dict[Any, Any], max_items: int = 16) -> None:
    while len(cache) > max_items:
        try:
            cache.pop(next(iter(cache)))
        except Exception:
            break

def resolve_warp_nonlinear_config(metadata: dict[str, Any] | None = None) -> WarpNonlinearConfig:
    meta = metadata or {}
    return WarpNonlinearConfig(
        enabled=bool(meta.get('warp_nonlinear_enabled', DEFAULT_WARP_NL_CONFIG.enabled)),
        force=bool(meta.get('warp_nonlinear_force', DEFAULT_WARP_NL_CONFIG.force)),
        min_cells=max(1, int(meta.get('warp_nonlinear_min_cells', DEFAULT_WARP_NL_CONFIG.min_cells))),
        fallback_to_cpu=bool(meta.get('warp_nonlinear_fallback_to_cpu', DEFAULT_WARP_NL_CONFIG.fallback_to_cpu)),
        mc_surrogate=bool(meta.get('warp_mc_surrogate', DEFAULT_WARP_NL_CONFIG.mc_surrogate)),
    )


def _pick_warp_device(requested_device: str, *, round_robin_index: int = 0) -> str:
    return choose_cuda_device(requested_device, round_robin_index=round_robin_index)


def _detect_material_family(materials: list[Any], cfg: WarpNonlinearConfig) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if materials and all(isinstance(m, (HSS, HSSmall)) for m in materials):
        return 'hss', warnings
    if materials and all(isinstance(m, MohrCoulomb) for m in materials):
        if any(float(m.tensile_strength) > 0.0 for m in materials):
            warnings.append('warp mohr-coulomb path currently requires tensile_strength <= 0; using CPU fallback')
            return 'unsupported', warnings
        if not cfg.mc_surrogate:
            warnings.append('warp mohr-coulomb path is disabled because mc surrogate mode is off')
            return 'unsupported', warnings
        warnings.append('warp mohr-coulomb path uses a Drucker-Prager surrogate return mapping on GPU for speed')
        return 'mohr-coulomb', warnings
    return 'unsupported', warnings


@lru_cache(maxsize=1)
def _get_warp_nonlinear_bundle() -> Any | None:
    wp = _optional_import('warp')
    if wp is None:
        return None

    vec6f = getattr(wp, 'vec6f', None) or getattr(wp, 'vec6', None)
    vec8f = getattr(wp, 'vec8f', None) or getattr(wp, 'vec8', None)
    if vec6f is None or vec8f is None:
        vector_factory = getattr(getattr(wp, "types", wp), "vector", None)
        if vector_factory is None:
            vector_factory = wp.vec
        vec6f = vec6f or vector_factory(length=6, dtype=wp.float32)
        vec8f = vec8f or vector_factory(length=8, dtype=wp.float32)

    @wp.func
    def _gauss_coord(i: int):
        a = wp.float32(0.5773502691896257)
        if i == 0:
            return -a
        if i == 1:
            return a
        if i == 2:
            return -a
        if i == 3:
            return a
        if i == 4:
            return -a
        if i == 5:
            return a
        if i == 6:
            return -a
        return a

    @wp.func
    def _gauss_eta(i: int):
        a = wp.float32(0.5773502691896257)
        if i == 0 or i == 1:
            return -a
        if i == 2 or i == 3:
            return a
        if i == 4 or i == 5:
            return -a
        return a

    @wp.func
    def _gauss_zeta(i: int):
        a = wp.float32(0.5773502691896257)
        if i <= 3:
            return -a
        return a

    @wp.func
    def _shape_grad_ref(a: int, xi: float, eta: float, zeta: float):
        c = wp.float32(0.125)
        if a == 0:
            return wp.vec3(-(1.0 - eta) * (1.0 - zeta), -(1.0 - xi) * (1.0 - zeta), -(1.0 - xi) * (1.0 - eta)) * c
        if a == 1:
            return wp.vec3(+(1.0 - eta) * (1.0 - zeta), -(1.0 + xi) * (1.0 - zeta), -(1.0 + xi) * (1.0 - eta)) * c
        if a == 2:
            return wp.vec3(+(1.0 + eta) * (1.0 - zeta), +(1.0 + xi) * (1.0 - zeta), -(1.0 + xi) * (1.0 + eta)) * c
        if a == 3:
            return wp.vec3(-(1.0 + eta) * (1.0 - zeta), +(1.0 - xi) * (1.0 - zeta), -(1.0 - xi) * (1.0 + eta)) * c
        if a == 4:
            return wp.vec3(-(1.0 - eta) * (1.0 + zeta), -(1.0 - xi) * (1.0 + zeta), +(1.0 - xi) * (1.0 - eta)) * c
        if a == 5:
            return wp.vec3(+(1.0 - eta) * (1.0 + zeta), -(1.0 + xi) * (1.0 + zeta), +(1.0 + xi) * (1.0 - eta)) * c
        if a == 6:
            return wp.vec3(+(1.0 + eta) * (1.0 + zeta), +(1.0 + xi) * (1.0 + zeta), +(1.0 + xi) * (1.0 + eta)) * c
        return wp.vec3(-(1.0 + eta) * (1.0 + zeta), +(1.0 - xi) * (1.0 + zeta), +(1.0 - xi) * (1.0 + eta)) * c

    @wp.func
    def _strain_col(gx: float, gy: float, gz: float, comp: int):
        if comp == 0:
            return vec6f(gx, 0.0, 0.0, gy, 0.0, gz)
        if comp == 1:
            return vec6f(0.0, gy, 0.0, gx, gz, 0.0)
        return vec6f(0.0, 0.0, gz, 0.0, gy, gx)

    @wp.func
    def _dot6(a: vec6f, b: vec6f):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4] + a[5] * b[5]

    @wp.func
    def _norm6(a: vec6f):
        return wp.sqrt(_dot6(a, a))

    @wp.func
    def _deg_to_rad(v: float):
        return v * wp.float32(0.017453292519943295)

    @wp.func
    def _mc_alpha(phi_deg: float):
        phi = _deg_to_rad(phi_deg)
        sphi = wp.sin(phi)
        denom = wp.sqrt(3.0) * wp.max(1.0e-12, 3.0 - sphi)
        return 6.0 * sphi / denom

    @wp.func
    def _mc_k(c: float, phi_deg: float):
        phi = _deg_to_rad(phi_deg)
        sphi = wp.sin(phi)
        cphi = wp.cos(phi)
        denom = wp.sqrt(3.0) * wp.max(1.0e-12, 3.0 - sphi)
        return 6.0 * c * cphi / denom

    @wp.func
    def _mc_beta(psi_deg: float):
        psi = _deg_to_rad(psi_deg)
        spsi = wp.sin(psi)
        denom = wp.sqrt(3.0) * wp.max(1.0e-12, 3.0 - spsi)
        return 6.0 * spsi / denom

    @wp.func
    def _mean_pressure_comp(s: vec6f):
        return -(s[0] + s[1] + s[2]) / 3.0

    @wp.func
    def _q_invariant(s: vec6f):
        p = _mean_pressure_comp(s)
        sx = s[0] + p
        sy = s[1] + p
        sz = s[2] + p
        j2 = 0.5 * (sx * sx + sy * sy + sz * sz + 2.0 * (s[3] * s[3] + s[4] * s[4] + s[5] * s[5]))
        return wp.sqrt(wp.max(0.0, 3.0 * j2))

    @wp.func
    def _deviator_dir(s: vec6f):
        p = _mean_pressure_comp(s)
        q = _q_invariant(s)
        q_safe = wp.max(q, 1.0e-12)
        return vec6f(
            (s[0] + p) / q_safe,
            (s[1] + p) / q_safe,
            (s[2] + p) / q_safe,
            s[3] / q_safe,
            s[4] / q_safe,
            s[5] / q_safe,
        )

    @wp.func
    def _apply_scaled_isotropic(e: vec6f, lam: float, mu: float, normal_scale: float, shear_scale: float):
        return vec6f(
            normal_scale * ((lam + 2.0 * mu) * e[0] + lam * e[1] + lam * e[2]),
            normal_scale * (lam * e[0] + (lam + 2.0 * mu) * e[1] + lam * e[2]),
            normal_scale * (lam * e[0] + lam * e[1] + (lam + 2.0 * mu) * e[2]),
            shear_scale * mu * e[3],
            shear_scale * mu * e[4],
            shear_scale * mu * e[5],
        )

    @wp.func
    def _shape_value(a: int, xi: float, eta: float, zeta: float):
        if a == 0:
            return wp.float32(0.125) * (1.0 - xi) * (1.0 - eta) * (1.0 - zeta)
        if a == 1:
            return wp.float32(0.125) * (1.0 + xi) * (1.0 - eta) * (1.0 - zeta)
        if a == 2:
            return wp.float32(0.125) * (1.0 + xi) * (1.0 + eta) * (1.0 - zeta)
        if a == 3:
            return wp.float32(0.125) * (1.0 - xi) * (1.0 + eta) * (1.0 - zeta)
        if a == 4:
            return wp.float32(0.125) * (1.0 - xi) * (1.0 - eta) * (1.0 + zeta)
        if a == 5:
            return wp.float32(0.125) * (1.0 + xi) * (1.0 - eta) * (1.0 + zeta)
        if a == 6:
            return wp.float32(0.125) * (1.0 + xi) * (1.0 + eta) * (1.0 + zeta)
        return wp.float32(0.125) * (1.0 - xi) * (1.0 + eta) * (1.0 + zeta)

    @wp.kernel
    def _assemble_hss_kernel(
        points: wp.array(dtype=wp.vec3),
        elements: wp.array2d(dtype=wp.int32),
        block_slots: wp.array2d(dtype=wp.int32),
        u_nodes: wp.array(dtype=wp.vec3),
        E50ref: wp.array(dtype=wp.float32),
        Eoedref: wp.array(dtype=wp.float32),
        Eurref: wp.array(dtype=wp.float32),
        nu_ur: wp.array(dtype=wp.float32),
        pref: wp.array(dtype=wp.float32),
        mexp: wp.array(dtype=wp.float32),
        cohesion: wp.array(dtype=wp.float32),
        phi_deg: wp.array(dtype=wp.float32),
        psi_deg: wp.array(dtype=wp.float32),
        G0ref: wp.array(dtype=wp.float32),
        gamma07: wp.array(dtype=wp.float32),
        Rf: wp.array(dtype=wp.float32),
        base_stress: wp.array3d(dtype=wp.float32),
        base_strain: wp.array3d(dtype=wp.float32),
        base_pstrain: wp.array3d(dtype=wp.float32),
        base_aux: wp.array3d(dtype=wp.float32),
        assemble_tangent: int,
        block_values: wp.array3d(dtype=wp.float32),
        global_force: wp.array(dtype=wp.float32),
        out_stress: wp.array3d(dtype=wp.float32),
        out_strain: wp.array3d(dtype=wp.float32),
        out_pstrain: wp.array3d(dtype=wp.float32),
        out_aux: wp.array3d(dtype=wp.float32),
        out_yielded: wp.array2d(dtype=wp.int32),
        out_mode: wp.array2d(dtype=wp.int32),
        out_branch: wp.array2d(dtype=wp.int32),
        cell_stress: wp.array2d(dtype=wp.float32),
        cell_yield: wp.array(dtype=wp.float32),
        cell_eqp: wp.array(dtype=wp.float32),
    ):
        eidx = wp.tid()
        E50 = E50ref[eidx]
        Eoed = Eoedref[eidx]
        Eur = Eurref[eidx]
        nuv = nu_ur[eidx]
        pref_i = wp.max(pref[eidx], 1.0)
        m_i = mexp[eidx]
        c_i = cohesion[eidx]
        phi_i = phi_deg[eidx]
        psi_i = psi_deg[eidx]
        G0_i = G0ref[eidx]
        gamma07_i = gamma07[eidx]
        Rf_i = Rf[eidx]
        stress_sum = vec6f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        yielded_count = wp.float32(0.0)
        eqp_sum = wp.float32(0.0)

        for gp in range(8):
            xi = _gauss_coord(gp)
            eta = _gauss_eta(gp)
            zeta = _gauss_zeta(gp)
            j00 = wp.float32(0.0)
            j01 = wp.float32(0.0)
            j02 = wp.float32(0.0)
            j10 = wp.float32(0.0)
            j11 = wp.float32(0.0)
            j12 = wp.float32(0.0)
            j20 = wp.float32(0.0)
            j21 = wp.float32(0.0)
            j22 = wp.float32(0.0)
            for a in range(8):
                pid = elements[eidx, a]
                p = points[pid]
                gref = _shape_grad_ref(a, xi, eta, zeta)
                j00 += p[0] * gref[0]
                j01 += p[0] * gref[1]
                j02 += p[0] * gref[2]
                j10 += p[1] * gref[0]
                j11 += p[1] * gref[1]
                j12 += p[1] * gref[2]
                j20 += p[2] * gref[0]
                j21 += p[2] * gref[1]
                j22 += p[2] * gref[2]
            detj = j00 * (j11 * j22 - j12 * j21) - j01 * (j10 * j22 - j12 * j20) + j02 * (j10 * j21 - j11 * j20)
            inv_detj = 1.0 / wp.max(detj, 1.0e-12)
            i00 = (j11 * j22 - j12 * j21) * inv_detj
            i01 = (j02 * j21 - j01 * j22) * inv_detj
            i02 = (j01 * j12 - j02 * j11) * inv_detj
            i10 = (j12 * j20 - j10 * j22) * inv_detj
            i11 = (j00 * j22 - j02 * j20) * inv_detj
            i12 = (j02 * j10 - j00 * j12) * inv_detj
            i20 = (j10 * j21 - j11 * j20) * inv_detj
            i21 = (j01 * j20 - j00 * j21) * inv_detj
            i22 = (j00 * j11 - j01 * j10) * inv_detj
            grad_x = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            grad_y = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            grad_z = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            dstrain = vec6f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            for a in range(8):
                gref = _shape_grad_ref(a, xi, eta, zeta)
                gx_a = i00 * gref[0] + i10 * gref[1] + i20 * gref[2]
                gy_a = i01 * gref[0] + i11 * gref[1] + i21 * gref[2]
                gz_a = i02 * gref[0] + i12 * gref[1] + i22 * gref[2]
                grad_x[a] = gx_a
                grad_y[a] = gy_a
                grad_z[a] = gz_a
                u = u_nodes[elements[eidx, a]]
                dstrain = dstrain + _strain_col(gx_a, gy_a, gz_a, 0) * u[0] + _strain_col(gx_a, gy_a, gz_a, 1) * u[1] + _strain_col(gx_a, gy_a, gz_a, 2) * u[2]

            s_old = vec6f(
                base_stress[eidx, gp, 0], base_stress[eidx, gp, 1], base_stress[eidx, gp, 2],
                base_stress[eidx, gp, 3], base_stress[eidx, gp, 4], base_stress[eidx, gp, 5],
            )
            strain_old = vec6f(
                base_strain[eidx, gp, 0], base_strain[eidx, gp, 1], base_strain[eidx, gp, 2],
                base_strain[eidx, gp, 3], base_strain[eidx, gp, 4], base_strain[eidx, gp, 5],
            )
            pstrain_old = vec6f(
                base_pstrain[eidx, gp, 0], base_pstrain[eidx, gp, 1], base_pstrain[eidx, gp, 2],
                base_pstrain[eidx, gp, 3], base_pstrain[eidx, gp, 4], base_pstrain[eidx, gp, 5],
            )
            eps_p_shear = base_aux[eidx, gp, 0]
            eps_p_vol = base_aux[eidx, gp, 1]
            eps_p_eq = base_aux[eidx, gp, 2]
            p_state = wp.max(base_aux[eidx, gp, 3], 1.0)
            q_state = base_aux[eidx, gp, 4]
            p_cap = wp.max(base_aux[eidx, gp, 5], pref_i)
            reduction_old = base_aux[eidx, gp, 6]
            gamma_hist = base_aux[eidx, gp, 7]
            gamma_rev = base_aux[eidx, gp, 8]
            gamma_max = base_aux[eidx, gp, 9]

            gamma_step = wp.sqrt(dstrain[3] * dstrain[3] + dstrain[4] * dstrain[4] + dstrain[5] * dstrain[5])
            work = _dot6(s_old, dstrain)
            prev_branch = 1 if base_aux[eidx, gp, 10] > 0.5 else 0
            branch = 1 if work < 0.0 else 0
            gamma_hist_new = gamma_hist + gamma_step
            gamma_rev_new = gamma_rev + gamma_step if branch == prev_branch else gamma_step
            gamma_max_new = wp.max(gamma_max, gamma_hist_new)
            reduction = 1.0
            if G0_i > 0.0 and gamma07_i > 0.0:
                reduction = 1.0 / (1.0 + wp.abs(gamma_rev_new) / gamma07_i)
            baseE = Eur if branch == 1 else E50
            Et = wp.max(1.0e3, baseE * wp.pow(wp.max(p_state, 1.0) / pref_i, m_i))
            if G0_i > 0.0:
                Gss = G0_i * wp.pow(wp.max(p_state, 1.0) / pref_i, m_i) * reduction
                E_from_G = 2.0 * (1.0 + nuv) * Gss
                Et = wp.max(Et, wp.min(E_from_G, wp.max(Eur * 3.0, Et)))
            nu_eff = wp.min(wp.max(nuv, 1.0e-3), 0.49)
            lam = Et * nu_eff / ((1.0 + nu_eff) * (1.0 - 2.0 * nu_eff))
            mu = Et / (2.0 * (1.0 + nu_eff))
            sigma_trial = s_old + _apply_scaled_isotropic(dstrain, lam, mu, 1.0, 1.0)
            p_tr = _mean_pressure_comp(sigma_trial)
            q_tr = _q_invariant(sigma_trial)
            alpha = _mc_alpha(phi_i)
            k = _mc_k(c_i * Rf_i * (1.0 + 3.0 * eps_p_shear), phi_i)
            beta = _mc_beta(psi_i)
            fs = q_tr + alpha * p_tr - k
            fc = p_tr - p_cap
            sigma_new = sigma_trial
            deps_p = vec6f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            dgamma_s = wp.float32(0.0)
            dgamma_c = wp.float32(0.0)
            yielded = 0
            mode_code = 0
            normal_scale = wp.float32(1.0)
            shear_scale = wp.float32(1.0)
            n_dev = _deviator_dir(sigma_trial)
            Hs = wp.max(1.0e-9, 0.15 * E50 * (1.0 + 1.5 * eps_p_shear))
            Hc = wp.max(1.0e-9, 0.10 * Eoed * (1.0 + eps_p_vol))
            Kbulk = (lam + 2.0 * mu + 2.0 * lam) / 3.0
            if fs > 0.0:
                denom_s = 3.0 * mu + alpha * beta * Kbulk + Hs
                dgamma_s = fs / wp.max(denom_s, 1.0e-12)
                p_new = p_tr - dgamma_s * beta * Kbulk
                q_new = wp.max(0.0, q_tr - dgamma_s * 3.0 * mu)
                sigma_new = n_dev * q_new
                sigma_new = vec6f(sigma_new[0] - p_new, sigma_new[1] - p_new, sigma_new[2] - p_new, sigma_new[3], sigma_new[4], sigma_new[5])
                deps_p = deps_p + vec6f(beta / 3.0, beta / 3.0, beta / 3.0, 0.0, 0.0, 0.0) * dgamma_s + n_dev * dgamma_s
                yielded = 1
                mode_code = 1
                p_tr = p_new
                q_tr = q_new
                normal_scale = 0.55
                shear_scale = 0.45
            if fc > 0.0 or p_tr > p_cap:
                over = wp.max(fc, p_tr - p_cap)
                dgamma_c = over / wp.max(Kbulk + Hc, 1.0e-12)
                p_new = p_tr - dgamma_c * Kbulk
                sigma_new = vec6f(
                    sigma_new[0] + (p_tr - p_new), sigma_new[1] + (p_tr - p_new), sigma_new[2] + (p_tr - p_new),
                    sigma_new[3], sigma_new[4], sigma_new[5],
                )
                deps_p = deps_p + vec6f(1.0/3.0, 1.0/3.0, 1.0/3.0, 0.0, 0.0, 0.0) * dgamma_c
                p_tr = p_new
                p_cap = wp.max(pref_i, p_cap + dgamma_c * Hc)
                yielded = 1
                mode_code = 3 if mode_code == 1 else 2
                if mode_code == 2:
                    normal_scale = 0.45
                    shear_scale = 0.80
                else:
                    normal_scale = 0.35
                    shear_scale = 0.40
            strain_new = strain_old + dstrain
            pstrain_new = pstrain_old + deps_p
            eps_p_shear_new = eps_p_shear + wp.abs(dgamma_s)
            eps_p_vol_new = eps_p_vol + wp.abs(dgamma_c) + wp.abs(beta * dgamma_s) * 0.5
            eps_p_eq_new = eps_p_eq + _norm6(deps_p)
            for c in range(6):
                out_stress[eidx, gp, c] = sigma_new[c]
                out_strain[eidx, gp, c] = strain_new[c]
                out_pstrain[eidx, gp, c] = pstrain_new[c]
                stress_sum[c] = stress_sum[c] + sigma_new[c]
            out_aux[eidx, gp, 0] = eps_p_shear_new
            out_aux[eidx, gp, 1] = eps_p_vol_new
            out_aux[eidx, gp, 2] = eps_p_eq_new
            out_aux[eidx, gp, 3] = wp.max(1.0, p_tr)
            out_aux[eidx, gp, 4] = q_tr
            out_aux[eidx, gp, 5] = p_cap
            out_aux[eidx, gp, 6] = reduction
            out_aux[eidx, gp, 7] = gamma_hist_new
            out_aux[eidx, gp, 8] = gamma_rev_new
            out_aux[eidx, gp, 9] = gamma_max_new
            out_aux[eidx, gp, 10] = wp.float32(branch)
            out_aux[eidx, gp, 11] = wp.max(fs, fc)
            out_yielded[eidx, gp] = yielded
            out_mode[eidx, gp] = mode_code
            out_branch[eidx, gp] = branch
            yielded_count = yielded_count + wp.float32(yielded)
            eqp_sum = eqp_sum + eps_p_eq_new
            for a in range(8):
                ea0 = _strain_col(grad_x[a], grad_y[a], grad_z[a], 0)
                ea1 = _strain_col(grad_x[a], grad_y[a], grad_z[a], 1)
                ea2 = _strain_col(grad_x[a], grad_y[a], grad_z[a], 2)
                node_a = elements[eidx, a]
                wp.atomic_add(global_force, 3 * node_a + 0, _dot6(ea0, sigma_new) * detj)
                wp.atomic_add(global_force, 3 * node_a + 1, _dot6(ea1, sigma_new) * detj)
                wp.atomic_add(global_force, 3 * node_a + 2, _dot6(ea2, sigma_new) * detj)
                if assemble_tangent != 0:
                    for b in range(8):
                        slot = block_slots[eidx, a * 8 + b]
                        for ib in range(3):
                            eb = _strain_col(grad_x[b], grad_y[b], grad_z[b], ib)
                            dcol = _apply_scaled_isotropic(eb, lam, mu, normal_scale, shear_scale)
                            wp.atomic_add(block_values, slot, 0, ib, _dot6(ea0, dcol) * detj)
                            wp.atomic_add(block_values, slot, 1, ib, _dot6(ea1, dcol) * detj)
                            wp.atomic_add(block_values, slot, 2, ib, _dot6(ea2, dcol) * detj)
        for c in range(6):
            cell_stress[eidx, c] = stress_sum[c] / 8.0
        cell_yield[eidx] = yielded_count / 8.0
        cell_eqp[eidx] = eqp_sum / 8.0

    @wp.kernel
    def _assemble_mc_kernel(
        points: wp.array(dtype=wp.vec3),
        elements: wp.array2d(dtype=wp.int32),
        block_slots: wp.array2d(dtype=wp.int32),
        u_nodes: wp.array(dtype=wp.vec3),
        young: wp.array(dtype=wp.float32),
        nu: wp.array(dtype=wp.float32),
        cohesion: wp.array(dtype=wp.float32),
        phi_deg: wp.array(dtype=wp.float32),
        psi_deg: wp.array(dtype=wp.float32),
        base_stress: wp.array3d(dtype=wp.float32),
        base_strain: wp.array3d(dtype=wp.float32),
        base_pstrain: wp.array3d(dtype=wp.float32),
        base_aux: wp.array3d(dtype=wp.float32),
        assemble_tangent: int,
        block_values: wp.array3d(dtype=wp.float32),
        global_force: wp.array(dtype=wp.float32),
        out_stress: wp.array3d(dtype=wp.float32),
        out_strain: wp.array3d(dtype=wp.float32),
        out_pstrain: wp.array3d(dtype=wp.float32),
        out_aux: wp.array3d(dtype=wp.float32),
        out_yielded: wp.array2d(dtype=wp.int32),
        out_mode: wp.array2d(dtype=wp.int32),
        cell_stress: wp.array2d(dtype=wp.float32),
        cell_yield: wp.array(dtype=wp.float32),
        cell_eqp: wp.array(dtype=wp.float32),
    ):
        eidx = wp.tid()
        E = young[eidx]
        nui = nu[eidx]
        c_i = cohesion[eidx]
        phi_i = phi_deg[eidx]
        psi_i = psi_deg[eidx]
        lam = E * nui / ((1.0 + nui) * (1.0 - 2.0 * nui))
        mu = E / (2.0 * (1.0 + nui))
        Kbulk = (lam + 2.0 * mu + 2.0 * lam) / 3.0
        alpha = _mc_alpha(phi_i)
        k = _mc_k(c_i, phi_i)
        beta = _mc_beta(psi_i)
        stress_sum = vec6f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        yielded_count = wp.float32(0.0)
        eqp_sum = wp.float32(0.0)
        for gp in range(8):
            xi = _gauss_coord(gp)
            eta = _gauss_eta(gp)
            zeta = _gauss_zeta(gp)
            j00 = wp.float32(0.0)
            j01 = wp.float32(0.0)
            j02 = wp.float32(0.0)
            j10 = wp.float32(0.0)
            j11 = wp.float32(0.0)
            j12 = wp.float32(0.0)
            j20 = wp.float32(0.0)
            j21 = wp.float32(0.0)
            j22 = wp.float32(0.0)
            for a in range(8):
                pid = elements[eidx, a]
                p = points[pid]
                gref = _shape_grad_ref(a, xi, eta, zeta)
                j00 += p[0] * gref[0]
                j01 += p[0] * gref[1]
                j02 += p[0] * gref[2]
                j10 += p[1] * gref[0]
                j11 += p[1] * gref[1]
                j12 += p[1] * gref[2]
                j20 += p[2] * gref[0]
                j21 += p[2] * gref[1]
                j22 += p[2] * gref[2]
            detj = j00 * (j11 * j22 - j12 * j21) - j01 * (j10 * j22 - j12 * j20) + j02 * (j10 * j21 - j11 * j20)
            inv_detj = 1.0 / wp.max(detj, 1.0e-12)
            i00 = (j11 * j22 - j12 * j21) * inv_detj
            i01 = (j02 * j21 - j01 * j22) * inv_detj
            i02 = (j01 * j12 - j02 * j11) * inv_detj
            i10 = (j12 * j20 - j10 * j22) * inv_detj
            i11 = (j00 * j22 - j02 * j20) * inv_detj
            i12 = (j02 * j10 - j00 * j12) * inv_detj
            i20 = (j10 * j21 - j11 * j20) * inv_detj
            i21 = (j01 * j20 - j00 * j21) * inv_detj
            i22 = (j00 * j11 - j01 * j10) * inv_detj
            grad_x = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            grad_y = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            grad_z = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            dstrain = vec6f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            for a in range(8):
                gref = _shape_grad_ref(a, xi, eta, zeta)
                gx_a = i00 * gref[0] + i10 * gref[1] + i20 * gref[2]
                gy_a = i01 * gref[0] + i11 * gref[1] + i21 * gref[2]
                gz_a = i02 * gref[0] + i12 * gref[1] + i22 * gref[2]
                grad_x[a] = gx_a
                grad_y[a] = gy_a
                grad_z[a] = gz_a
                u = u_nodes[elements[eidx, a]]
                dstrain = dstrain + _strain_col(gx_a, gy_a, gz_a, 0) * u[0] + _strain_col(gx_a, gy_a, gz_a, 1) * u[1] + _strain_col(gx_a, gy_a, gz_a, 2) * u[2]
            s_old = vec6f(
                base_stress[eidx, gp, 0], base_stress[eidx, gp, 1], base_stress[eidx, gp, 2],
                base_stress[eidx, gp, 3], base_stress[eidx, gp, 4], base_stress[eidx, gp, 5],
            )
            strain_old = vec6f(
                base_strain[eidx, gp, 0], base_strain[eidx, gp, 1], base_strain[eidx, gp, 2],
                base_strain[eidx, gp, 3], base_strain[eidx, gp, 4], base_strain[eidx, gp, 5],
            )
            pstrain_old = vec6f(
                base_pstrain[eidx, gp, 0], base_pstrain[eidx, gp, 1], base_pstrain[eidx, gp, 2],
                base_pstrain[eidx, gp, 3], base_pstrain[eidx, gp, 4], base_pstrain[eidx, gp, 5],
            )
            eps_p_eq = base_aux[eidx, gp, 0]
            sigma_trial = s_old + _apply_scaled_isotropic(dstrain, lam, mu, 1.0, 1.0)
            p_tr = _mean_pressure_comp(sigma_trial)
            q_tr = _q_invariant(sigma_trial)
            f_tr = q_tr + alpha * p_tr - k
            sigma_new = sigma_trial
            deps_p = vec6f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            dgamma = wp.float32(0.0)
            yielded = 0
            mode_code = 0
            normal_scale = wp.float32(1.0)
            shear_scale = wp.float32(1.0)
            if f_tr > 0.0:
                n_dev = _deviator_dir(sigma_trial)
                H = wp.max(1.0e-9, 0.05 * E * (1.0 + eps_p_eq))
                denom = 3.0 * mu + alpha * beta * Kbulk + H
                dgamma = f_tr / wp.max(denom, 1.0e-12)
                p_new = p_tr - beta * Kbulk * dgamma
                q_new = wp.max(0.0, q_tr - 3.0 * mu * dgamma)
                sigma_new = n_dev * q_new
                sigma_new = vec6f(sigma_new[0] - p_new, sigma_new[1] - p_new, sigma_new[2] - p_new, sigma_new[3], sigma_new[4], sigma_new[5])
                deps_p = dgamma * (n_dev + vec6f(beta/3.0, beta/3.0, beta/3.0, 0.0, 0.0, 0.0))
                yielded = 1
                mode_code = 1
                normal_scale = 0.35
                shear_scale = 0.22
            strain_new = strain_old + dstrain
            pstrain_new = pstrain_old + deps_p
            eps_p_eq_new = eps_p_eq + _norm6(deps_p)
            for c in range(6):
                out_stress[eidx, gp, c] = sigma_new[c]
                out_strain[eidx, gp, c] = strain_new[c]
                out_pstrain[eidx, gp, c] = pstrain_new[c]
                stress_sum[c] = stress_sum[c] + sigma_new[c]
            out_aux[eidx, gp, 0] = eps_p_eq_new
            out_aux[eidx, gp, 1] = f_tr
            out_aux[eidx, gp, 2] = dgamma
            out_yielded[eidx, gp] = yielded
            out_mode[eidx, gp] = mode_code
            yielded_count = yielded_count + wp.float32(yielded)
            eqp_sum = eqp_sum + eps_p_eq_new
            for a in range(8):
                ea0 = _strain_col(grad_x[a], grad_y[a], grad_z[a], 0)
                ea1 = _strain_col(grad_x[a], grad_y[a], grad_z[a], 1)
                ea2 = _strain_col(grad_x[a], grad_y[a], grad_z[a], 2)
                node_a = elements[eidx, a]
                wp.atomic_add(global_force, 3 * node_a + 0, _dot6(ea0, sigma_new) * detj)
                wp.atomic_add(global_force, 3 * node_a + 1, _dot6(ea1, sigma_new) * detj)
                wp.atomic_add(global_force, 3 * node_a + 2, _dot6(ea2, sigma_new) * detj)
                if assemble_tangent != 0:
                    for b in range(8):
                        slot = block_slots[eidx, a * 8 + b]
                        for ib in range(3):
                            eb = _strain_col(grad_x[b], grad_y[b], grad_z[b], ib)
                            dcol = _apply_scaled_isotropic(eb, lam, mu, normal_scale, shear_scale)
                            wp.atomic_add(block_values, slot, 0, ib, _dot6(ea0, dcol) * detj)
                            wp.atomic_add(block_values, slot, 1, ib, _dot6(ea1, dcol) * detj)
                            wp.atomic_add(block_values, slot, 2, ib, _dot6(ea2, dcol) * detj)
        for c in range(6):
            cell_stress[eidx, c] = stress_sum[c] / 8.0
        cell_yield[eidx] = yielded_count / 8.0
        cell_eqp[eidx] = eqp_sum / 8.0

    return wp, _assemble_hss_kernel, _assemble_mc_kernel


def _states_to_core_arrays(base_states: list[list[MaterialState]], family: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ne = len(base_states)
    ngp = len(base_states[0]) if base_states else 0
    stress = np.zeros((ne, ngp, 6), dtype=np.float32)
    strain = np.zeros((ne, ngp, 6), dtype=np.float32)
    pstrain = np.zeros((ne, ngp, 6), dtype=np.float32)
    if family == 'hss':
        aux = np.zeros((ne, ngp, 12), dtype=np.float32)
    else:
        aux = np.zeros((ne, ngp, 3), dtype=np.float32)
    for eidx, elem_states in enumerate(base_states):
        for gp_idx, st in enumerate(elem_states):
            stress[eidx, gp_idx] = np.asarray(st.stress, dtype=np.float32)
            strain[eidx, gp_idx] = np.asarray(st.strain, dtype=np.float32)
            pstrain[eidx, gp_idx] = np.asarray(st.plastic_strain, dtype=np.float32)
            internal = st.internal
            if family == 'hss':
                aux[eidx, gp_idx, 0] = float(internal.get('eps_p_shear', 0.0))
                aux[eidx, gp_idx, 1] = float(internal.get('eps_p_vol', 0.0))
                aux[eidx, gp_idx, 2] = float(internal.get('eps_p_eq', 0.0))
                aux[eidx, gp_idx, 3] = float(internal.get('p_ref_state', 0.0))
                aux[eidx, gp_idx, 4] = float(internal.get('q_ref_state', 0.0))
                aux[eidx, gp_idx, 5] = float(internal.get('p_cap', 0.0))
                aux[eidx, gp_idx, 6] = float(internal.get('shear_mod_reduction', 1.0))
                aux[eidx, gp_idx, 7] = float(internal.get('gamma_hist', 0.0))
                aux[eidx, gp_idx, 8] = float(internal.get('gamma_rev', 0.0))
                aux[eidx, gp_idx, 9] = float(internal.get('gamma_max', 0.0))
                aux[eidx, gp_idx, 10] = 1.0 if str(internal.get('mode_branch', 'loading')) == 'unloading' else 0.0
                aux[eidx, gp_idx, 11] = float(internal.get('yield_margin', 0.0))
            else:
                aux[eidx, gp_idx, 0] = float(internal.get('eps_p_eq', 0.0))
                aux[eidx, gp_idx, 1] = float(internal.get('yield_margin', 0.0))
                aux[eidx, gp_idx, 2] = float(internal.get('plastic_multiplier', 0.0))
    return stress, strain, pstrain, aux


def _core_arrays_to_states(
    family: str,
    stress: np.ndarray,
    strain: np.ndarray,
    pstrain: np.ndarray,
    aux: np.ndarray,
    yielded: np.ndarray,
    mode: np.ndarray,
    branch: np.ndarray | None,
) -> list[list[MaterialState]]:
    out: list[list[MaterialState]] = []
    ne, ngp = stress.shape[:2]
    for eidx in range(ne):
        elem_states: list[MaterialState] = []
        for gp_idx in range(ngp):
            internal: dict[str, Any]
            if family == 'hss':
                mode_code = int(mode[eidx, gp_idx])
                mode_name = 'elastic' if mode_code == 0 else ('shear' if mode_code == 1 else ('cap' if mode_code == 2 else 'double'))
                branch_name = 'unloading' if int(branch[eidx, gp_idx]) == 1 else 'loading'
                internal = {
                    'eps_p_shear': float(aux[eidx, gp_idx, 0]),
                    'eps_p_vol': float(aux[eidx, gp_idx, 1]),
                    'eps_p_eq': float(aux[eidx, gp_idx, 2]),
                    'p_ref_state': float(aux[eidx, gp_idx, 3]),
                    'q_ref_state': float(aux[eidx, gp_idx, 4]),
                    'p_cap': float(aux[eidx, gp_idx, 5]),
                    'shear_mod_reduction': float(aux[eidx, gp_idx, 6]),
                    'gamma_hist': float(aux[eidx, gp_idx, 7]),
                    'gamma_rev': float(aux[eidx, gp_idx, 8]),
                    'gamma_max': float(aux[eidx, gp_idx, 9]),
                    'yield_margin': float(aux[eidx, gp_idx, 11]),
                    'yielded': bool(yielded[eidx, gp_idx]),
                    'yield_mode': mode_name,
                    'mode_branch': branch_name,
                    'algorithm': 'hs-small-dp-cap-approx-gpu',
                }
            else:
                mode_name = 'shear-single' if int(mode[eidx, gp_idx]) == 1 else 'elastic'
                internal = {
                    'yielded': bool(yielded[eidx, gp_idx]),
                    'yield_mode': mode_name,
                    'eps_p_eq': float(aux[eidx, gp_idx, 0]),
                    'yield_margin': float(aux[eidx, gp_idx, 1]),
                    'plastic_multiplier': float(aux[eidx, gp_idx, 2]),
                    'algorithm': 'mc-dp-surrogate-gpu',
                    'active_planes': ('f13',) if bool(yielded[eidx, gp_idx]) else tuple(),
                }
            elem_states.append(MaterialState(
                stress=np.asarray(stress[eidx, gp_idx], dtype=float),
                strain=np.asarray(strain[eidx, gp_idx], dtype=float),
                plastic_strain=np.asarray(pstrain[eidx, gp_idx], dtype=float),
                internal=internal,
            ))
        out.append(elem_states)
    return out


def try_warp_nonlinear_continuum_assembly(
    *,
    points: np.ndarray,
    elements: np.ndarray,
    materials: list[Any],
    du_step_trans: np.ndarray,
    base_states: list[list[MaterialState]],
    total_ndof: int,
    assemble_tangent: bool,
    requested_device: str,
    solver_metadata: dict[str, Any] | None,
    block_pattern: BlockSparsePattern | None = None,
    progress_callback=None,
) -> tuple[Any | None, np.ndarray | None, list[list[MaterialState]] | None, np.ndarray | None, np.ndarray | None, np.ndarray | None, WarpNonlinearAssemblyInfo]:
    cfg = resolve_warp_nonlinear_config(solver_metadata)
    family, family_warnings = _detect_material_family(materials, cfg)
    info = WarpNonlinearAssemblyInfo(
        enabled=bool(cfg.enabled),
        used=False,
        device=str(requested_device or 'cpu'),
        backend='cpu-fallback',
        warnings=list(family_warnings),
        element_count=int(np.asarray(elements).shape[0]),
        material_family=family,
    )
    if not cfg.enabled:
        info.warnings.append('warp nonlinear continuum path disabled by configuration')
        return None, None, None, None, None, None, info
    if family == 'unsupported':
        return None, None, None, None, None, None, info
    if np.asarray(elements).shape[0] < cfg.min_cells and not cfg.force:
        info.warnings.append(f'warp nonlinear continuum skipped because element_count={elements.shape[0]} < min_cells={cfg.min_cells}')
        return None, None, None, None, None, None, info
    device = _pick_warp_device(requested_device)
    if device in _WARP_NONLINEAR_FAILURES:
        info.warnings.append(f"warp nonlinear previously disabled on {device}: {_WARP_NONLINEAR_FAILURES[device]}")
        return None, None, None, None, None, None, info
    if not str(device).startswith('cuda') and not cfg.force:
        info.warnings.append('warp nonlinear continuum skipped because requested device is not CUDA')
        return None, None, None, None, None, None, info
    try:
        bundle = _get_warp_nonlinear_bundle()
    except Exception as exc:
        msg = f'failed to build Warp nonlinear kernels for {device}: {exc}'
        _WARP_NONLINEAR_FAILURES[device] = str(exc)
        info.warnings.append(msg)
        return None, None, None, None, None, None, info
    if bundle is None:
        info.warnings.append('warp-lang is not installed; using CPU nonlinear continuum path')
        return None, None, None, None, None, None, info
    wp, hss_kernel, mc_kernel = bundle
    try:
        wp.init()
        if hasattr(wp, 'set_device'):
            wp.set_device(device)
    except Exception as exc:
        msg = f'failed to initialize Warp device {device}: {exc}'
        _WARP_NONLINEAR_FAILURES[device] = str(exc)
        info.warnings.append(msg)
        return None, None, None, None, None, None, info

    pattern = block_pattern or build_block_sparse_pattern(np.asarray(elements, dtype=np.int32))
    pts = np.asarray(points, dtype=np.float32)
    elems = np.asarray(elements, dtype=np.int32)
    u_nodes_np = np.asarray(du_step_trans, dtype=np.float32).reshape(points.shape[0], 3)
    base_stress, base_strain, base_pstrain, base_aux = _states_to_core_arrays(base_states, family)
    n_nodes = int(points.shape[0])
    trans_ndof = n_nodes * 3
    try:
        cache_key = _nl_cache_key(device, pts, elems, np.asarray(pattern.elem_block_slots, dtype=np.int32))
        cached = _WARP_NL_DEVICE_CACHE.get(cache_key) if bool((solver_metadata or {}).get("warp_resident_cache", True)) else None
        if cached is None:
            if progress_callback is not None:
                try:
                    upload_mb = (pts.nbytes + elems.nbytes + np.asarray(pattern.elem_block_slots, dtype=np.int32).nbytes) / float(1024**2)
                    progress_callback({"phase": "gpu-data-upload", "message": f"Uploading nonlinear mesh data to {device}", "device": device, "upload_mb": float(upload_mb), "upload_scope": "nonlinear-continuum"})
                except Exception:
                    pass
            t0 = __import__('time').perf_counter()
            pts_wp = wp.from_numpy(pts, dtype=wp.vec3, device=device)
            elems_wp = wp.from_numpy(elems, dtype=wp.int32, device=device)
            slots_wp = wp.from_numpy(np.asarray(pattern.elem_block_slots, dtype=np.int32), dtype=wp.int32, device=device)
            _WARP_NL_DEVICE_CACHE[cache_key] = (pts_wp, elems_wp, slots_wp)
            _prune_small_cache(_WARP_NL_DEVICE_CACHE, max_items=16)
            if progress_callback is not None:
                try:
                    progress_callback({"phase": "gpu-data-ready", "message": f"Nonlinear mesh data ready on {device}", "device": device, "upload_scope": "nonlinear-continuum", "upload_seconds": float(__import__('time').perf_counter()-t0)})
                except Exception:
                    pass
        else:
            pts_wp, elems_wp, slots_wp = cached
            if progress_callback is not None:
                try:
                    progress_callback({"phase": "gpu-data-ready", "message": f"Reusing resident GPU cache on {device}", "device": device, "upload_scope": "nonlinear-continuum", "cache_hit": True})
                except Exception:
                    pass
        u_wp = wp.from_numpy(u_nodes_np, dtype=wp.vec3, device=device)
        base_stress_wp = wp.from_numpy(base_stress, dtype=wp.float32, device=device)
        base_strain_wp = wp.from_numpy(base_strain, dtype=wp.float32, device=device)
        base_pstrain_wp = wp.from_numpy(base_pstrain, dtype=wp.float32, device=device)
        base_aux_wp = wp.from_numpy(base_aux, dtype=wp.float32, device=device)
        block_vals_wp = wp.zeros((max(1, pattern.rows.shape[0]), 3, 3), dtype=wp.float32, device=device)
        fint_wp = wp.zeros(trans_ndof, dtype=wp.float32, device=device)
        out_stress_wp = wp.zeros(base_stress.shape, dtype=wp.float32, device=device)
        out_strain_wp = wp.zeros(base_strain.shape, dtype=wp.float32, device=device)
        out_pstrain_wp = wp.zeros(base_pstrain.shape, dtype=wp.float32, device=device)
        out_aux_wp = wp.zeros(base_aux.shape, dtype=wp.float32, device=device)
        out_yield_wp = wp.zeros((elems.shape[0], 8), dtype=wp.int32, device=device)
        out_mode_wp = wp.zeros((elems.shape[0], 8), dtype=wp.int32, device=device)
        out_branch_wp = wp.zeros((elems.shape[0], 8), dtype=wp.int32, device=device)
        cell_stress_wp = wp.zeros((elems.shape[0], 6), dtype=wp.float32, device=device)
        cell_yield_wp = wp.zeros(elems.shape[0], dtype=wp.float32, device=device)
        cell_eqp_wp = wp.zeros(elems.shape[0], dtype=wp.float32, device=device)

        mat_cache_key = (str(device), family, _material_signature(materials, family))
        mat_cached = _WARP_NL_MATERIAL_CACHE.get(mat_cache_key) if bool((solver_metadata or {}).get("warp_resident_cache", True)) else None
        if mat_cached is None:
            if progress_callback is not None:
                try:
                    progress_callback({"phase": "gpu-material-upload", "message": f"Uploading material constants to {device}", "device": device, "upload_scope": "nonlinear-materials"})
                except Exception:
                    pass
            mat_t0 = __import__('time').perf_counter()
            if family == 'hss':
                kernel = hss_kernel
                mat_cached = (
                    wp.from_numpy(np.asarray([float(m.E50ref) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.Eoedref) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.Eurref) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.nu_ur) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.pref) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.m) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.c) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.phi_deg) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.psi_deg) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.G0ref or 0.0) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.gamma07 or 0.0) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.Rf) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                )
            else:
                kernel = mc_kernel
                mat_cached = (
                    wp.from_numpy(np.asarray([float(m.E) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.nu) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.cohesion) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.friction_deg) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                    wp.from_numpy(np.asarray([float(m.dilation_deg) for m in materials], dtype=np.float32), dtype=wp.float32, device=device),
                )
            _WARP_NL_MATERIAL_CACHE[mat_cache_key] = mat_cached
            _prune_small_cache(_WARP_NL_MATERIAL_CACHE, max_items=16)
            if progress_callback is not None:
                try:
                    progress_callback({"phase": "gpu-material-ready", "message": f"Material constants ready on {device}", "device": device, "upload_scope": "nonlinear-materials", "upload_seconds": float(__import__('time').perf_counter()-mat_t0)})
                except Exception:
                    pass
        else:
            kernel = hss_kernel if family == 'hss' else mc_kernel
            if progress_callback is not None:
                try:
                    progress_callback({"phase": "gpu-material-ready", "message": f"Reusing resident material cache on {device}", "device": device, "upload_scope": "nonlinear-materials", "cache_hit": True})
                except Exception:
                    pass

        if family == 'hss':
            E50_wp, Eoed_wp, Eur_wp, nu_wp, pref_wp, m_wp, c_wp, phi_wp, psi_wp, G0_wp, g07_wp, Rf_wp = mat_cached
            wp.launch(
                kernel=kernel,
                dim=int(elems.shape[0]),
                inputs=[pts_wp, elems_wp, slots_wp, u_wp, E50_wp, Eoed_wp, Eur_wp, nu_wp, pref_wp, m_wp, c_wp, phi_wp, psi_wp, G0_wp, g07_wp, Rf_wp, base_stress_wp, base_strain_wp, base_pstrain_wp, base_aux_wp, int(bool(assemble_tangent))],
                outputs=[block_vals_wp, fint_wp, out_stress_wp, out_strain_wp, out_pstrain_wp, out_aux_wp, out_yield_wp, out_mode_wp, out_branch_wp, cell_stress_wp, cell_yield_wp, cell_eqp_wp],
                device=device,
            )
        else:
            E_wp, nu_wp, c_wp, phi_wp, psi_wp = mat_cached
            wp.launch(
                kernel=kernel,
                dim=int(elems.shape[0]),
                inputs=[pts_wp, elems_wp, slots_wp, u_wp, E_wp, nu_wp, c_wp, phi_wp, psi_wp, base_stress_wp, base_strain_wp, base_pstrain_wp, base_aux_wp, int(bool(assemble_tangent))],
                outputs=[block_vals_wp, fint_wp, out_stress_wp, out_strain_wp, out_pstrain_wp, out_aux_wp, out_yield_wp, out_mode_wp, cell_stress_wp, cell_yield_wp, cell_eqp_wp],
                device=device,
            )
        sync = getattr(wp, 'synchronize_device', None)
        if callable(sync):
            sync(device)
        elif hasattr(wp, 'synchronize'):
            wp.synchronize()
        fint = np.asarray(fint_wp.numpy(), dtype=float)
        K = None
        if assemble_tangent:
            if total_ndof == trans_ndof:
                K = WarpBlockSparseMatrix(pattern=pattern, ndof=trans_ndof, block_size=3, device=device, values_device=block_vals_wp)
            else:
                block_vals = np.asarray(block_vals_wp.numpy(), dtype=float)[: pattern.rows.shape[0]]
                K = block_values_to_csr(pattern, block_vals, ndof=trans_ndof)
        stress = np.asarray(out_stress_wp.numpy(), dtype=float)
        strain = np.asarray(out_strain_wp.numpy(), dtype=float)
        pstrain = np.asarray(out_pstrain_wp.numpy(), dtype=float)
        aux = np.asarray(out_aux_wp.numpy(), dtype=float)
        yielded = np.asarray(out_yield_wp.numpy(), dtype=np.int32)
        mode = np.asarray(out_mode_wp.numpy(), dtype=np.int32)
        branch = np.asarray(out_branch_wp.numpy(), dtype=np.int32) if family == 'hss' else None
        trial_states = _core_arrays_to_states(family, stress, strain, pstrain, aux, yielded, mode, branch)
        cell_stress = np.asarray(cell_stress_wp.numpy(), dtype=float)
        cell_yield = np.asarray(cell_yield_wp.numpy(), dtype=float)
        cell_eqp = np.asarray(cell_eqp_wp.numpy(), dtype=float)
    except Exception as exc:
        msg = f'warp nonlinear continuum kernel execution failed: {exc}'
        if 'Error while parsing function' in str(exc) or 'load on device' in str(exc):
            _WARP_NONLINEAR_FAILURES[device] = str(exc)
        info.warnings.append(msg)
        return None, None, None, None, None, None, info

    if total_ndof > trans_ndof:
        sp = _optional_import('scipy.sparse')
        if assemble_tangent:
            if hasattr(K, 'to_csr'):
                K_base = K.to_csr()
                zero_tail = sp.csr_matrix((total_ndof - trans_ndof, total_ndof - trans_ndof), dtype=float) if sp is not None else None
                K = sp.bmat([[K_base, None], [None, zero_tail]], format='csr') if sp is not None else K_base
            elif sp is not None and getattr(sp, 'issparse', lambda *_: False)(K):
                zero_tail = sp.csr_matrix((total_ndof - trans_ndof, total_ndof - trans_ndof), dtype=float)
                K = sp.bmat([[K, None], [None, zero_tail]], format='csr')
            else:
                K_full = np.zeros((total_ndof, total_ndof), dtype=float)
                K_full[:trans_ndof, :trans_ndof] = np.asarray(K, dtype=float)
                K = K_full
        fint_full = np.zeros(total_ndof, dtype=float)
        fint_full[:trans_ndof] = fint
        fint = fint_full

    info.used = True
    info.device = device
    info.backend = f'warp-{family}-global-assembly-{device}'
    return K, fint, trial_states, cell_stress, cell_yield, cell_eqp, info
