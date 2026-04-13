from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

from geoai_simkit.solver.linear_algebra import _optional_import


_WARP_HEX8_FAILURES: dict[str, str] = {}


@dataclass(slots=True)
class WarpHex8Config:
    enabled: bool = True
    force: bool = False
    min_cells: int = 256
    precision: str = "float32"
    fallback_to_cpu: bool = True
    gpu_global_assembly: bool = True


@dataclass(slots=True)
class WarpHex8AssemblyInfo:
    enabled: bool
    used: bool
    device: str
    backend: str
    precision: str
    warnings: list[str] = field(default_factory=list)
    element_count: int = 0


@dataclass(slots=True)
class BlockSparsePattern:
    rows: np.ndarray
    cols: np.ndarray
    elem_block_slots: np.ndarray
    diag_block_slots: np.ndarray
    _slot_lookup_cache: dict[tuple[int, int], int] | None = None
    _csr_index_cache: dict[int, tuple[np.ndarray, np.ndarray]] | None = None
    _device_array_cache: dict[str, tuple[Any, Any, Any]] | None = None


@dataclass(slots=True)
class WarpBlockSparseMatrix:
    pattern: BlockSparsePattern
    ndof: int
    block_size: int = 3
    device: str = 'cpu'
    values_host: np.ndarray | None = None
    values_device: Any | None = None
    _csr_cache: Any | None = None

    def host_values(self) -> np.ndarray:
        if self.values_host is not None:
            return np.asarray(self.values_host, dtype=float)
        vals = self.values_device
        if vals is None:
            raise RuntimeError('block sparse matrix has no host or device values')
        if hasattr(vals, 'numpy'):
            self.values_host = np.asarray(vals.numpy(), dtype=float)
            return np.asarray(self.values_host, dtype=float)
        raise RuntimeError('unable to materialize device block values on host')

    def with_host_values(self, values: np.ndarray, *, clear_device: bool = True) -> 'WarpBlockSparseMatrix':
        return WarpBlockSparseMatrix(
            pattern=self.pattern,
            ndof=self.ndof,
            block_size=self.block_size,
            device=self.device,
            values_host=np.asarray(values, dtype=float),
            values_device=None if clear_device else self.values_device,
        )

    def add_host_values(self, values: np.ndarray) -> 'WarpBlockSparseMatrix':
        merged = np.asarray(self.host_values(), dtype=float) + np.asarray(values, dtype=float)
        return self.with_host_values(merged)

    def to_csr(self) -> Any:
        if self._csr_cache is None:
            self._csr_cache = block_values_to_csr(self.pattern, self.host_values(), ndof=int(self.ndof))
        return self._csr_cache

    def matvec(self, x: np.ndarray) -> np.ndarray:
        return block_values_matvec(self.pattern, self.host_values(), np.asarray(x, dtype=float), block_size=int(self.block_size), ndof=int(self.ndof))


DEFAULT_WARP_HEX8_CONFIG = WarpHex8Config()


def resolve_warp_hex8_config(metadata: dict[str, Any] | None = None) -> WarpHex8Config:
    meta = metadata or {}
    return WarpHex8Config(
        enabled=bool(meta.get("warp_hex8_enabled", DEFAULT_WARP_HEX8_CONFIG.enabled)),
        force=bool(meta.get("warp_hex8_force", DEFAULT_WARP_HEX8_CONFIG.force)),
        min_cells=max(1, int(meta.get("warp_hex8_min_cells", DEFAULT_WARP_HEX8_CONFIG.min_cells))),
        precision=str(meta.get("warp_hex8_precision", DEFAULT_WARP_HEX8_CONFIG.precision)).lower(),
        fallback_to_cpu=bool(meta.get("warp_hex8_fallback_to_cpu", DEFAULT_WARP_HEX8_CONFIG.fallback_to_cpu)),
        gpu_global_assembly=bool(meta.get("warp_gpu_global_assembly", DEFAULT_WARP_HEX8_CONFIG.gpu_global_assembly)),
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


def build_node_block_sparse_pattern(connectivities: list[np.ndarray] | tuple[np.ndarray, ...], n_nodes: int | None = None) -> BlockSparsePattern:
    arrays = [np.asarray(conn, dtype=np.int32) for conn in connectivities if np.asarray(conn).size]
    if not arrays:
        n_local = int(max(0, n_nodes or 0))
        return BlockSparsePattern(
            rows=np.empty((0,), dtype=np.int32),
            cols=np.empty((0,), dtype=np.int32),
            elem_block_slots=np.empty((0, 0), dtype=np.int32),
            diag_block_slots=np.full((n_local,), -1, dtype=np.int32),
        )
    if n_nodes is None:
        n_nodes = max(int(np.max(arr)) + 1 for arr in arrays)
    n_nodes = int(n_nodes)

    pair_keys_parts: list[np.ndarray] = []
    primary_shape: tuple[int, int] | None = None
    primary_keys: np.ndarray | None = None
    for idx, conn in enumerate(arrays):
        conn = np.asarray(conn, dtype=np.int64)
        if conn.ndim != 2 or conn.size == 0:
            continue
        nen = int(conn.shape[1])
        rows_part = np.repeat(conn, nen, axis=1)
        cols_part = np.tile(conn, (1, nen))
        keys = rows_part.reshape(-1) * np.int64(n_nodes) + cols_part.reshape(-1)
        pair_keys_parts.append(np.asarray(keys, dtype=np.int64))
        if idx == 0:
            primary_shape = (int(conn.shape[0]), nen * nen)
            primary_keys = np.asarray(keys, dtype=np.int64)

    if not pair_keys_parts:
        return BlockSparsePattern(
            rows=np.empty((0,), dtype=np.int32),
            cols=np.empty((0,), dtype=np.int32),
            elem_block_slots=np.empty((0, 0), dtype=np.int32),
            diag_block_slots=np.full((n_nodes,), -1, dtype=np.int32),
        )

    all_keys = np.concatenate(pair_keys_parts, axis=0)
    unique_keys, inverse = np.unique(all_keys, return_inverse=True)
    rows = np.asarray(unique_keys // np.int64(n_nodes), dtype=np.int32)
    cols = np.asarray(unique_keys % np.int64(n_nodes), dtype=np.int32)
    diag_slots = np.full((n_nodes,), -1, dtype=np.int32)
    diag_mask = rows == cols
    if np.any(diag_mask):
        diag_slots[rows[diag_mask]] = np.nonzero(diag_mask)[0].astype(np.int32)

    elem_slots = np.empty((0, 0), dtype=np.int32)
    if primary_shape is not None and primary_keys is not None:
        primary_count = int(primary_keys.size)
        elem_slots = np.asarray(inverse[:primary_count], dtype=np.int32).reshape(primary_shape)

    return BlockSparsePattern(
        rows=rows,
        cols=cols,
        elem_block_slots=elem_slots,
        diag_block_slots=diag_slots,
    )


def build_block_sparse_pattern(elements: np.ndarray) -> BlockSparsePattern:
    elems = np.asarray(elements, dtype=np.int32)
    n_nodes = int(np.max(elems)) + 1 if elems.size else 0
    return build_node_block_sparse_pattern([elems], n_nodes=n_nodes)




def pattern_slot_lookup(pattern: BlockSparsePattern) -> dict[tuple[int, int], int]:
    cache = getattr(pattern, '_slot_lookup_cache', None)
    if cache is None:
        cache = {(int(r), int(c)): idx for idx, (r, c) in enumerate(zip(np.asarray(pattern.rows, dtype=np.int32), np.asarray(pattern.cols, dtype=np.int32), strict=False))}
        pattern._slot_lookup_cache = cache
    return cache


def block_values_matvec(pattern: BlockSparsePattern, values: np.ndarray, x: np.ndarray, *, block_size: int = 3, ndof: int | None = None) -> np.ndarray:
    bs = int(block_size)
    vec = np.asarray(x, dtype=float).reshape(-1)
    if ndof is None:
        ndof = int(vec.shape[0])
    vals = np.asarray(values, dtype=float)
    if vals.ndim == 1:
        vals = vals.reshape(-1, 1, 1)
    if vals.size == 0 or int(pattern.rows.size) == 0:
        return np.zeros(int(ndof), dtype=float)
    n_nodes = max(int(np.max(pattern.rows)) + 1 if pattern.rows.size else 0, int(np.max(pattern.cols)) + 1 if pattern.cols.size else 0, int(ndof) // bs)
    x_nodes = np.zeros((n_nodes, bs), dtype=float)
    flat = vec[: n_nodes * bs]
    if flat.size:
        x_nodes[: flat.size // bs] = flat.reshape(-1, bs)
    contrib = np.einsum('nij,nj->ni', vals, x_nodes[np.asarray(pattern.cols, dtype=np.int64)], optimize=True)
    out_nodes = np.zeros((n_nodes, bs), dtype=float)
    np.add.at(out_nodes, np.asarray(pattern.rows, dtype=np.int64), contrib)
    return out_nodes.reshape(-1)[: int(ndof)]


def accumulate_block_values(pattern: BlockSparsePattern, values: np.ndarray, node_ids: np.ndarray, local_matrix: np.ndarray, *, block_size: int = 3, slot_lookup: dict[tuple[int, int], int] | None = None) -> None:
    nodes = np.asarray(node_ids, dtype=np.int64).reshape(-1)
    mat = np.asarray(local_matrix, dtype=float)
    bs = int(block_size)
    lookup = slot_lookup or pattern_slot_lookup(pattern)
    for a, na in enumerate(nodes):
        ra = slice(a * bs, (a + 1) * bs)
        for b, nb in enumerate(nodes):
            cb = slice(b * bs, (b + 1) * bs)
            slot = lookup[(int(na), int(nb))]
            values[slot] += mat[ra, cb]

def block_values_to_csr(pattern: BlockSparsePattern, values: np.ndarray, *, ndof: int) -> Any:
    sp = _optional_import("scipy.sparse")
    if sp is None:
        raise RuntimeError("SciPy sparse is required to finalize block sparse values")
    vals = np.asarray(values, dtype=float)
    if vals.ndim == 1:
        vals = vals.reshape(-1, 1, 1)
    bs = int(vals.shape[1])
    cache = getattr(pattern, '_csr_index_cache', None)
    if cache is None:
        cache = {}
        pattern._csr_index_cache = cache
    cached = cache.get(bs)
    if cached is None:
        rr = np.repeat(pattern.rows[:, None] * bs + np.arange(bs, dtype=np.int32)[None, :], bs, axis=1).reshape(-1)
        cc = np.tile(pattern.cols[:, None] * bs + np.arange(bs, dtype=np.int32)[None, :], (1, bs)).reshape(-1)
        cached = (rr, cc)
        cache[bs] = cached
    rr, cc = cached
    data = vals.reshape(-1)
    return sp.coo_matrix((data, (rr, cc)), shape=(ndof, ndof)).tocsr()




def get_pattern_device_arrays(pattern: BlockSparsePattern, device: str, wp: Any) -> tuple[Any, Any, Any]:
    cache = getattr(pattern, '_device_array_cache', None)
    if cache is None:
        cache = {}
        pattern._device_array_cache = cache
    key = str(device)
    cached = cache.get(key)
    if cached is None:
        cached = (
            wp.from_numpy(np.asarray(pattern.rows, dtype=np.int32), dtype=wp.int32, device=device),
            wp.from_numpy(np.asarray(pattern.cols, dtype=np.int32), dtype=wp.int32, device=device),
            wp.from_numpy(np.asarray(pattern.diag_block_slots, dtype=np.int32), dtype=wp.int32, device=device),
        )
        cache[key] = cached
    return cached


def clone_warp_block_values(values: Any, wp: Any, block_type: Any, device: str) -> Any:
    if hasattr(wp, 'clone'):
        try:
            return wp.clone(values)
        except Exception:
            pass
    try:
        arr = wp.empty_like(values)
        copy_fn = getattr(wp, 'copy', None)
        if callable(copy_fn):
            copy_fn(arr, values)
        else:
            arr.assign(values)
        return arr
    except Exception:
        pass
    if hasattr(values, 'numpy'):
        return wp.from_numpy(np.asarray(values.numpy(), dtype=np.float32), dtype=block_type, device=device)
    raise RuntimeError('unable to clone warp block values for safe in-place modification')

@lru_cache(maxsize=1)
def _get_warp_kernel_bundle() -> Any | None:
    wp = _optional_import("warp")
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
            return vec6f(gx, 0.0, 0.0, gy, 0.0, gz)
        if comp == 1:
            return vec6f(0.0, gy, 0.0, gx, gz, 0.0)
        return vec6f(0.0, 0.0, gz, 0.0, gy, gx)

    @wp.func
    def _apply_isotropic(e: vec6f, lam: float, mu: float):
        return vec6f(
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

            grad_x = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            grad_y = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            grad_z = vec8f(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

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

    @wp.kernel
    def _scatter_blocks_kernel(
        elements: wp.array2d(dtype=wp.int32),
        block_slots: wp.array2d(dtype=wp.int32),
        ke_in: wp.array2d(dtype=wp.float32),
        fe_in: wp.array2d(dtype=wp.float32),
        block_values: wp.array3d(dtype=wp.float32),
        global_force: wp.array(dtype=wp.float32),
    ):
        eidx = wp.tid()
        for a in range(8):
            node_a = elements[eidx, a]
            for ia in range(3):
                wp.atomic_add(global_force, 3 * node_a + ia, fe_in[eidx, 3 * a + ia])
            for b in range(8):
                slot = block_slots[eidx, a * 8 + b]
                for ia in range(3):
                    row = 3 * a + ia
                    for ib in range(3):
                        col = 3 * b + ib
                        wp.atomic_add(block_values, slot, ia, ib, ke_in[eidx, row * 24 + col])

    return wp, _hex8_linear_kernel, _scatter_blocks_kernel


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
    block_pattern: BlockSparsePattern | None = None,
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
    if device in _WARP_HEX8_FAILURES:
        info.warnings.append(f"warp hex8 previously disabled on {device}: {_WARP_HEX8_FAILURES[device]}")
        return None, None, info
    if not str(device).startswith("cuda") and not config.force:
        info.warnings.append("warp hex8 assembly skipped because requested device is not CUDA")
        return None, None, info

    try:
        bundle = _get_warp_kernel_bundle()
    except Exception as exc:
        msg = f"failed to build Warp hex8 kernels for {device}: {exc}"
        _WARP_HEX8_FAILURES[device] = str(exc)
        info.warnings.append(msg)
        return None, None, info
    if bundle is None:
        info.warnings.append("warp-lang is not installed; using CPU element assembly")
        return None, None, info

    wp, kernel, scatter_kernel = bundle
    try:
        if hasattr(wp, "init"):
            wp.init()
        if hasattr(wp, "set_device"):
            wp.set_device(device)
    except Exception as exc:
        msg = f"failed to initialize Warp device {device}: {exc}"
        _WARP_HEX8_FAILURES[device] = str(exc)
        info.warnings.append(msg)
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
    pattern = block_pattern or build_block_sparse_pattern(elems)

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

        valid = np.asarray(valid_wp.numpy(), dtype=np.int32)
        detj_min = np.asarray(detj_wp.numpy(), dtype=float)
    except Exception as exc:
        msg = f"warp kernel execution failed: {exc}"
        if "Error while parsing function" in str(exc) or "load on device" in str(exc):
            _WARP_HEX8_FAILURES[device] = str(exc)
        info.warnings.append(msg)
        return None, None, info

    bad = np.where(valid <= 0)[0]
    if bad.size:
        info.warnings.append(
            f"warp hex8 assembly found {bad.size} degenerate elements; min_detJ={float(np.min(detj_min[bad])):.3e}"
        )
        return None, None, info

    try:
        block_vals_wp = wp.zeros((max(1, pattern.rows.shape[0]), 3, 3), dtype=wp.float32, device=device)
        force_wp = wp.zeros(ndof, dtype=wp.float32, device=device)
        slots_wp = wp.from_numpy(np.asarray(pattern.elem_block_slots, dtype=np.int32), dtype=wp.int32, device=device)
        wp.launch(
            kernel=scatter_kernel,
            dim=int(elems.shape[0]),
            inputs=[elems_wp, slots_wp, ke_wp, fe_wp],
            outputs=[block_vals_wp, force_wp],
            device=device,
        )
        sync = getattr(wp, "synchronize_device", None)
        if callable(sync):
            sync(device)
        elif hasattr(wp, "synchronize"):
            wp.synchronize()
        F = np.asarray(force_wp.numpy(), dtype=float)
    except Exception as exc:
        info.warnings.append(f"warp global block assembly failed: {exc}")
        return None, None, info

    if bool(config.gpu_global_assembly):
        K = WarpBlockSparseMatrix(pattern=pattern, ndof=int(ndof), block_size=3, device=device, values_device=block_vals_wp)
        info.backend = f"warp-kernel-device-block-assembly-{device}"
    else:
        block_vals = np.asarray(block_vals_wp.numpy(), dtype=float)[: pattern.rows.shape[0]]
        K = block_values_to_csr(pattern, block_vals, ndof=ndof)
        info.backend = f"warp-kernel-block-assembly-{device}"
    _WARP_HEX8_FAILURES.pop(device, None)
    info.used = True
    info.device = device
    return K, F, info
