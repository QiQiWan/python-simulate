from __future__ import annotations

import numpy as np


def mean_pressure_compression(stress: np.ndarray) -> float:
    s = np.asarray(stress, dtype=float)
    return float(-(s[0] + s[1] + s[2]) / 3.0)


def deviator(stress: np.ndarray) -> np.ndarray:
    s = np.asarray(stress, dtype=float).copy()
    p = mean_pressure_compression(s)
    s[:3] += p
    return s


def j2_invariant(stress: np.ndarray) -> float:
    s = deviator(stress)
    return 0.5 * (s[0]**2 + s[1]**2 + s[2]**2 + 2.0 * (s[3]**2 + s[4]**2 + s[5]**2))


def q_invariant(stress: np.ndarray) -> float:
    return float(np.sqrt(max(0.0, 3.0 * j2_invariant(stress))))


def lode_weighted_norm(vec6: np.ndarray) -> float:
    v = np.asarray(vec6, dtype=float)
    return float(np.sqrt(v[0]**2 + v[1]**2 + v[2]**2 + 2.0*(v[3]**2 + v[4]**2 + v[5]**2)))


def stress6_to_tensor(stress: np.ndarray) -> np.ndarray:
    s = np.asarray(stress, dtype=float)
    return np.array([[s[0], s[3], s[5]], [s[3], s[1], s[4]], [s[5], s[4], s[2]]], dtype=float)


def tensor_to_stress6(tensor: np.ndarray) -> np.ndarray:
    t = np.asarray(tensor, dtype=float)
    return np.array([t[0, 0], t[1, 1], t[2, 2], t[0, 1], t[1, 2], t[0, 2]], dtype=float)


def principal_decomposition(stress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tensor = stress6_to_tensor(stress)
    vals, vecs = np.linalg.eigh(tensor)
    order = np.argsort(vals)[::-1]
    return vals[order], vecs[:, order]


def principal_stresses(stress: np.ndarray) -> np.ndarray:
    vals, _ = principal_decomposition(stress)
    return vals


def reconstruct_from_principal(principal_vals: np.ndarray, principal_vecs: np.ndarray) -> np.ndarray:
    tensor = principal_vecs @ np.diag(np.asarray(principal_vals, dtype=float)) @ principal_vecs.T
    tensor = 0.5 * (tensor + tensor.T)
    return tensor_to_stress6(tensor)


def dp_alpha_k_from_mc(c: float, phi_deg: float) -> tuple[float, float]:
    phi = np.deg2rad(phi_deg)
    denom = np.sqrt(3.0) * max(1e-12, 3.0 - np.sin(phi))
    alpha = 6.0 * np.sin(phi) / denom
    k = 6.0 * c * np.cos(phi) / denom
    return float(alpha), float(k)


def dp_beta_from_dilation(psi_deg: float) -> float:
    psi = np.deg2rad(psi_deg)
    denom = np.sqrt(3.0) * max(1e-12, 3.0 - np.sin(psi))
    return float(6.0 * np.sin(psi) / denom)


def mc_nphi(phi_deg: float) -> float:
    phi = np.deg2rad(phi_deg)
    return float((1.0 + np.sin(phi)) / max(1e-12, 1.0 - np.sin(phi)))


def mc_npsi(psi_deg: float) -> float:
    psi = np.deg2rad(psi_deg)
    return float((1.0 + np.sin(psi)) / max(1e-12, 1.0 - np.sin(psi)))
