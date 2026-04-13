from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

from geoai_simkit.solver.linear_algebra import _optional_import


@dataclass(slots=True)
class WarpHex8Config:
    enabled: bool = True
    force: bool = False
    min_cells: int = 256
    precision: str = "float32"
    fallback_to_cpu: bool = True


@dataclass(slots=True)
class WarpHex8AssemblyInfo:
    enabled: bool
    used: bool
    device: str
    backend: str
    precision: str
    warnings: list[str] = field(default_factory=list)
    element_count: int = 0


DEFAULT_WARP_HEX8_CONFIG = WarpHex8Config()


def resolve_warp_hex8_config(metadata: dict[str, Any] | None = None) -> WarpHex8Config:
    meta = metadata or {}
    return WarpHex8Config(
        enabled=bool(meta.get("warp_hex8_enabled", DEFAULT_WARP_HEX8_CONFIG.enabled)),
        force=bool(meta.get("warp_hex8_force", DEFAULT_WARP_HEX8_CONFIG.force)),
        min_cells=max(1, int(meta.get("warp_hex8_min_cells", DEFAULT_WARP_HEX8_CONFIG.min_cells))),
        precision=str(meta.get("warp_hex8_precision", DEFAULT_WARP_HEX8_CONFIG.precision)).lower(),
        fallback_to_cpu=bool(meta.get("warp_hex8_fallback_to_cpu", DEFAULT_WARP_HEX8_CONFIG.fallback_to_cpu)),
    )


def _build_element_dof_map(elements: np.ndarray) -> np.ndarray:
    elems = np.asarray(elements, dtype=np.int64)
    edofs = np.empty((elems.shape[0], 24), dtype=np.int64)
    for a in range(8):
        base = 3 * elems[:, a]
        edofs[:, 3 * a + 0] = base + 0
        edofs[:, 3 * a + 1] = base + 1
        edofs[:, 3 * a + 2] = base + 2
    return edofs


@lru_cache(maxsize=1)
def _get_warp_kernel_bundle() -> Any | None:
    wp = _optional_import("warp")
    if wp is None:
        return None

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
            return wp.vec(length=6, dtype=wp.float32)(gx, 0.0, 0.0, gy, 0.0, gz)
        if comp == 1:
            return wp.vec(length=6, dtype=wp.float32)(0.0, gy, 0.0, gx, gz, 0.0)
        return wp.vec(length=6, dtype=wp.float32)(0.0, 0.0, gz, 0.0, gy, gx)

    @wp.func
    def _apply_isotropic(e: Any, lam: float, mu: float):
        return wp.vec(length=6, dtype=wp.float32)(
            (lam + 2.0 * mu) * e[0] + lam * e[1] + lam * e[2],
            lam * e[0] + (lam + 2.0 * mu) * e[1] + lam * e[2],
            lam * e[0] + lam * e[1] + (lam + 2.0 * mu) * e[2],
            mu * e[3],
            mu * e[4],
            mu * e[5],
        )

    @wp.kernel
    def _hex8_linear_kernel(
        points: wp.array(dtype=wp.vec3),
        elements: wp.array2d(dtype=wp.int32),
        young: wp.array(dtype=wp.float32),
        nu: wp.array(dtype=wp.float32),
        rho: wp.array(dtype=wp.float32),
        gx: float,
        gy: float,
        gz: float,
        ke_out: wp.array2d(dtype=wp.float32),
        fe_out: wp.array2d(dtype=wp.float32),
        valid_out: wp.array(dtype=wp.int32),
        detj_min_out: wp.array(dtype=wp.float32),
    ):
        eidx = wp.tid()
        E = young[eidx]
        nui = nu[eidx]
        rhoi = rho[eidx]
        lam = E * nui / ((1.0 + nui) * (1.0 - 2.0 * nui))
        mu = E / (2.0 * (1.0 + nui))
        min_detj = wp.float32(1.0e20)
        valid_out[eidx] = 1

        for i in range(24):
            fe_out[eidx, i] = 0.0
        for i in range(24 * 24):
            ke_out[eidx, i] = 0.0

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

            detj = (
                j00 * (j11 * j22 - j12 * j21)
                - j01 * (j10 * j22 - j12 * j20)
                + j02 * (j10 * j21 - j11 * j20)
            )
            if detj < min_detj:
                min_detj = detj
            if detj <= 1.0e-10:
                valid_out[eidx] = 0
                detj_min_out[eidx] = min_detj
                return

            inv_detj = 1.0 / detj
            i00 = (j11 * j22 - j12 * j21) * inv_detj
            i01 = (j02 * j21 - j01 * j22) * inv_detj
            i02 = (j01 * j12 - j02 * j11) * inv_detj
            i10 = (j12 * j20 - j10 * j22) * inv_detj
            i11 = (j00 * j22 - j02 * j20) * inv_detj
            i12 = (j02 * j10 - j00 * j12) * inv_detj
            i20 = (j10 * j21 - j11 * j20) * inv_detj
            i21 = (j01 * j20 - j00 * j21) * inv_detj
            i22 = (j00 * j11 - j01 * j10) * inv_detj

            grad_x = wp.vec(length=8, dtype=wp.float32)(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            grad_y = wp.vec(length=8, dtype=wp.float32)(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            grad_z = wp.vec(length=8, dtype=wp.float32)(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

            for a in range(8):
                gref = _shape_grad_ref(a, xi, eta, zeta)
                gx_a = i00 * gref[0] + i10 * gref[1] + i20 * gref[2]
                gy_a = i01 * gref[0] + i11 * gref[1] + i21 * gref[2]
                gz_a = i02 * gref[0] + i12 * gref[1] + i22 * gref[2]
                grad_x[a] = gx_a
                grad_y[a] = gy_a
                grad_z[a] = gz_a

                Na = _shape_value(a, xi, eta, zeta)
                base = 3 * a
                fe_out[eidx, base + 0] = fe_out[eidx, base + 0] + Na * rhoi * gx * detj
                fe_out[eidx, base + 1] = fe_out[eidx, base + 1] + Na * rhoi * gy * detj
                fe_out[eidx, base + 2] = fe_out[eidx, base + 2] + Na * rhoi * gz * detj

            for a in range(8):
                gax = grad_x[a]
                gay = grad_y[a]
                gaz = grad_z[a]
                for ia in range(3):
                    ea = _strain_col(gax, gay, gaz, ia)
                    row = 3 * a + ia
                    for b in range(8):
                        gbx = grad_x[b]
                        gby = grad_y[b]
                        gbz = grad_z[b]
                        for ib in range(3):
                            eb = _strain_col(gbx, gby, gbz, ib)
                            stress = _apply_isotropic(eb, lam, mu)
                            val = (
                                ea[0] * stress[0] + ea[1] * stress[1] + ea[2] * stress[2]
                                + ea[3] * stress[3] + ea[4] * stress[4] + ea[5] * stress[5]
                            ) * detj
                            col = 3 * b + ib
                            ke_out[eidx, row * 24 + col] = ke_out[eidx, row * 24 + col] + val

        detj_min_out[eidx] = min_detj

    return wp, _hex8_linear_kernel


def _pick_warp_device(requested_device: str) -> str:
    req = str(requested_device or "auto").lower()
    if req == "auto":
        return "cuda:0"
    if req == "cuda":
        return "cuda:0"
    return req


def try_warp_hex8_linear_assembly(
    points: np.ndarray,
    elements: np.ndarray,
    young: np.ndarray,
    nu: np.ndarray,
    rho: np.ndarray,
    gravity: tuple[float, float, float],
    *,
    ndof: int,
    requested_device: str,
    config: WarpHex8Config,
) -> tuple[Any | None, np.ndarray | None, WarpHex8AssemblyInfo]:
    info = WarpHex8AssemblyInfo(
        enabled=bool(config.enabled),
        used=False,
        device=str(requested_device or "cpu"),
        backend="cpu-fallback",
        precision=str(config.precision),
        element_count=int(np.asarray(elements).shape[0]),
    )

    if not config.enabled:
        info.warnings.append("warp hex8 assembly disabled by configuration")
        return None, None, info

    if elements.shape[0] < config.min_cells and not config.force:
        info.warnings.append(
            f"warp hex8 assembly skipped because element_count={elements.shape[0]} < min_cells={config.min_cells}"
        )
        return None, None, info

    device = _pick_warp_device(requested_device)
    if not str(device).startswith("cuda") and not config.force:
        info.warnings.append("warp hex8 assembly skipped because requested device is not CUDA")
        return None, None, info

    bundle = _get_warp_kernel_bundle()
    if bundle is None:
        info.warnings.append("warp-lang is not installed; using CPU element assembly")
        return None, None, info

    wp, kernel = bundle
    try:
        if hasattr(wp, "init"):
            wp.init()
        if hasattr(wp, "set_device"):
            wp.set_device(device)
    except Exception as exc:
        info.warnings.append(f"failed to initialize Warp device {device}: {exc}")
        return None, None, info

    sp = _optional_import("scipy.sparse")
    if sp is None:
        info.warnings.append("SciPy sparse is unavailable; using CPU element assembly")
        return None, None, info

    pts = np.asarray(points, dtype=np.float32)
    elems = np.asarray(elements, dtype=np.int32)
    e = np.asarray(young, dtype=np.float32)
    n = np.asarray(nu, dtype=np.float32)
    r = np.asarray(rho, dtype=np.float32)
    gx, gy, gz = [float(v) for v in gravity]

    try:
        points_wp = wp.from_numpy(pts, dtype=wp.vec3, device=device)
        elems_wp = wp.from_numpy(elems, dtype=wp.int32, device=device)
        e_wp = wp.from_numpy(e, dtype=wp.float32, device=device)
        n_wp = wp.from_numpy(n, dtype=wp.float32, device=device)
        r_wp = wp.from_numpy(r, dtype=wp.float32, device=device)
        ke_wp = wp.zeros((elems.shape[0], 24 * 24), dtype=wp.float32, device=device)
        fe_wp = wp.zeros((elems.shape[0], 24), dtype=wp.float32, device=device)
        valid_wp = wp.zeros(elems.shape[0], dtype=wp.int32, device=device)
        detj_wp = wp.zeros(elems.shape[0], dtype=wp.float32, device=device)

        wp.launch(
            kernel=kernel,
            dim=int(elems.shape[0]),
            inputs=[points_wp, elems_wp, e_wp, n_wp, r_wp, gx, gy, gz],
            outputs=[ke_wp, fe_wp, valid_wp, detj_wp],
            device=device,
        )
        sync = getattr(wp, "synchronize_device", None)
        if callable(sync):
            sync(device)
        elif hasattr(wp, "synchronize"):
            wp.synchronize()

        ke = np.asarray(ke_wp.numpy(), dtype=float).reshape(elems.shape[0], 24, 24)
        fe = np.asarray(fe_wp.numpy(), dtype=float)
        valid = np.asarray(valid_wp.numpy(), dtype=np.int32)
        detj_min = np.asarray(detj_wp.numpy(), dtype=float)
    except Exception as exc:
        info.warnings.append(f"warp kernel execution failed: {exc}")
        return None, None, info

    bad = np.where(valid <= 0)[0]
    if bad.size:
        info.warnings.append(
            f"warp hex8 assembly found {bad.size} degenerate elements; min_detJ={float(np.min(detj_min[bad])):.3e}"
        )
        return None, None, info

    edofs = _build_element_dof_map(elems)
    rows = np.repeat(edofs, 24, axis=1).reshape(-1)
    cols = np.tile(edofs, (1, 24)).reshape(-1)
    data = np.asarray(ke, dtype=float).reshape(-1)
    K = sp.coo_matrix((data, (rows, cols)), shape=(ndof, ndof)).tocsr()
    F = np.zeros(ndof, dtype=float)
    np.add.at(F, edofs.reshape(-1), fe.reshape(-1))

    info.used = True
    info.device = device
    info.backend = f"warp-kernel-{device}"
    return K, F, info
