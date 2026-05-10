from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

TETRA_VTK = 10


def _tet_volume(points: np.ndarray, tet: np.ndarray) -> float:
    a, b, c, d = (points[int(i)] for i in tet[:4])
    return float(np.dot(np.cross(b - a, c - a), d - a) / 6.0)


def _edge_lengths(points: np.ndarray, tet: np.ndarray) -> np.ndarray:
    pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    return np.asarray([np.linalg.norm(points[int(tet[i])] - points[int(tet[j])]) for i, j in pairs], dtype=float)


def _parse_vtk_cells(grid: Any) -> tuple[np.ndarray, np.ndarray]:
    cells = np.asarray(getattr(grid, 'cells', np.asarray([], dtype=np.int64)), dtype=np.int64)
    types = np.asarray(getattr(grid, 'celltypes', np.asarray([], dtype=np.uint8)))
    out: list[np.ndarray] = []
    ids: list[int] = []
    pos = 0
    for i, ctype in enumerate(types):
        if pos >= len(cells):
            break
        n = int(cells[pos])
        conn = cells[pos + 1:pos + 1 + n]
        if int(ctype) == TETRA_VTK and n == 4:
            out.append(np.asarray(conn, dtype=np.int64))
            ids.append(int(i))
        pos += n + 1
    if not out:
        return np.zeros((0, 4), dtype=np.int64), np.asarray([], dtype=np.int64)
    return np.vstack(out), np.asarray(ids, dtype=np.int64)


def _tet_dihedral_angles(points: np.ndarray, tet: np.ndarray) -> np.ndarray:
    p = [points[int(i)] for i in tet[:4]]
    faces = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))
    normals: list[np.ndarray] = []
    for a, b, c in faces:
        n = np.cross(p[b] - p[a], p[c] - p[a])
        norm = np.linalg.norm(n)
        normals.append(n / norm if norm > 1.0e-30 else np.zeros(3))
    pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    angles: list[float] = []
    for i, j in pairs:
        dot = float(np.clip(np.dot(normals[i], normals[j]), -1.0, 1.0))
        angles.append(180.0 - float(np.degrees(np.arccos(dot))))
    return np.asarray(angles, dtype=float)


def _radius_ratio(points: np.ndarray, tet: np.ndarray, volume: float) -> float:
    lengths = _edge_lengths(points, tet)
    lmax = max(float(np.max(lengths)), 1.0e-30)
    # Lightweight proxy in [0, 1]; exact inradius/circumradius can replace this.
    return float(min(1.0, max(0.0, (12.0 * abs(volume)) ** (1.0 / 3.0) / lmax)))


@dataclass(frozen=True, slots=True)
class MeshQualityReport:
    cell_count: int
    tetra_count: int
    min_signed_volume: float = 0.0
    min_abs_volume: float = 0.0
    max_aspect_ratio: float = 0.0
    mean_aspect_ratio: float = 0.0
    min_dihedral_angle: float = 0.0
    max_dihedral_angle: float = 0.0
    min_radius_ratio: float = 0.0
    min_scaled_jacobian: float = 0.0
    sliver_cell_ids: tuple[int, ...] = ()
    inverted_cell_ids: tuple[int, ...] = ()
    tiny_cell_ids: tuple[int, ...] = ()
    poor_angle_cell_ids: tuple[int, ...] = ()
    duplicate_node_count: int = 0
    disconnected_region_count: int = 0
    contact_face_quality: dict[str, Any] = field(default_factory=dict)
    bad_cell_geometry_refs: tuple[dict[str, Any], ...] = ()
    issues: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        bad = set(self.sliver_cell_ids) | set(self.inverted_cell_ids) | set(self.tiny_cell_ids) | set(self.poor_angle_cell_ids)
        quality_ok = len(bad) == 0 and int(self.contact_face_quality.get('unmatched_boundary_face_count', 0) or 0) == 0 and int(self.contact_face_quality.get('normal_inconsistent_face_set_count', 0) or 0) == 0
        recommended_actions: list[str] = []
        if self.inverted_cell_ids or self.tiny_cell_ids:
            recommended_actions.append('repair_or_simplify_source_entities_then_remesh')
        if self.sliver_cell_ids or self.poor_angle_cell_ids:
            recommended_actions.append('tighten_mesh_size_field_near_bad_geometry_or_switch_gmsh_algorithm')
        if int(self.contact_face_quality.get('unmatched_boundary_face_count', 0) or 0) > 0:
            recommended_actions.append('review_physical_surface_to_volume_face_matching')
        if int(self.contact_face_quality.get('normal_inconsistent_face_set_count', 0) or 0) > 0:
            recommended_actions.append('review_face_set_normal_orientation_before_surface_load_or_contact')
        return {
            'contract': 'mesh_quality_report_v3',
            'cell_count': int(self.cell_count),
            'tetra_count': int(self.tetra_count),
            'min_signed_volume': float(self.min_signed_volume),
            'min_abs_volume': float(self.min_abs_volume),
            'max_aspect_ratio': float(self.max_aspect_ratio),
            'mean_aspect_ratio': float(self.mean_aspect_ratio),
            'min_dihedral_angle': float(self.min_dihedral_angle),
            'max_dihedral_angle': float(self.max_dihedral_angle),
            'min_radius_ratio': float(self.min_radius_ratio),
            'min_scaled_jacobian': float(self.min_scaled_jacobian),
            'sliver_cell_ids': [int(v) for v in self.sliver_cell_ids[:200]],
            'inverted_cell_ids': [int(v) for v in self.inverted_cell_ids[:200]],
            'tiny_cell_ids': [int(v) for v in self.tiny_cell_ids[:200]],
            'poor_angle_cell_ids': [int(v) for v in self.poor_angle_cell_ids[:200]],
            'bad_cell_count': len(bad),
            'duplicate_node_count': int(self.duplicate_node_count),
            'disconnected_region_count': int(self.disconnected_region_count),
            'contact_face_quality': dict(self.contact_face_quality),
            'bad_cell_geometry_refs': [dict(row) for row in self.bad_cell_geometry_refs[:500]],
            'issues': [dict(i) for i in self.issues],
            'recommended_actions': list(dict.fromkeys(recommended_actions)),
            'summary': {
                'quality_ok': quality_ok,
                'bad_cell_count': len(bad),
                'inverted_cell_count': len(self.inverted_cell_ids),
                'sliver_cell_count': len(self.sliver_cell_ids),
                'tiny_cell_count': len(self.tiny_cell_ids),
                'poor_angle_cell_count': len(self.poor_angle_cell_ids),
                'duplicate_node_count': int(self.duplicate_node_count),
            },
        }


class MeshQualityEvaluator:
    def evaluate(self, grid: Any, *, face_sets: dict[str, Any] | None = None, brep_document: dict[str, Any] | None = None, sliver_aspect_ratio: float = 20.0, min_angle_deg: float = 5.0) -> dict[str, Any]:
        points = np.asarray(getattr(grid, 'points', np.zeros((0, 3)))[:, :3], dtype=float)
        tets, original_ids = _parse_vtk_cells(grid)
        issues: list[dict[str, Any]] = []
        if tets.size == 0:
            issues.append({'id': 'mesh_quality.no_tetra', 'severity': 'warning', 'message': 'No tetrahedral cells were found for quality evaluation.'})
            return MeshQualityReport(cell_count=int(getattr(grid, 'n_cells', 0) or 0), tetra_count=0, issues=tuple(issues)).to_dict()
        volumes = np.asarray([_tet_volume(points, tet) for tet in tets], dtype=float)
        abs_vol = np.abs(volumes)
        min_abs = float(np.min(abs_vol)) if abs_vol.size else 0.0
        vol_tol = max(min_abs * 1.0e-6, 1.0e-14)
        aspects: list[float] = []
        radius_ratios: list[float] = []
        dihedral_min: list[float] = []
        dihedral_max: list[float] = []
        scaled_j: list[float] = []
        for tet, vol in zip(tets, abs_vol):
            lengths = _edge_lengths(points, tet)
            lmin = max(float(np.min(lengths)), 1.0e-30)
            lmax = float(np.max(lengths))
            compact = (lmax ** 3) / max(float(vol), 1.0e-30)
            aspects.append(max(lmax / lmin, compact / 8.0))
            rr = _radius_ratio(points, tet, float(vol))
            radius_ratios.append(rr)
            angles = _tet_dihedral_angles(points, tet)
            dihedral_min.append(float(np.min(angles)))
            dihedral_max.append(float(np.max(angles)))
            scaled_j.append(float(np.sign(vol) * min(1.0, rr)))
        aspect_arr = np.asarray(aspects, dtype=float)
        radius_arr = np.asarray(radius_ratios, dtype=float)
        dmin_arr = np.asarray(dihedral_min, dtype=float)
        dmax_arr = np.asarray(dihedral_max, dtype=float)
        sj_arr = np.asarray(scaled_j, dtype=float)
        inverted = tuple(int(original_ids[i]) for i in np.where(volumes <= 0.0)[0])
        tiny = tuple(int(original_ids[i]) for i in np.where(abs_vol <= vol_tol)[0])
        sliver = tuple(int(original_ids[i]) for i in np.where(aspect_arr >= float(sliver_aspect_ratio))[0])
        poor_angle = tuple(int(original_ids[i]) for i in np.where((dmin_arr <= float(min_angle_deg)) | (dmax_arr >= 175.0))[0])
        rounded_nodes = {tuple(round(float(v), 10) for v in row) for row in points}
        duplicate_nodes = max(0, int(points.shape[0]) - len(rounded_nodes))
        fs = dict(face_sets or {})
        fs_summary = dict(fs.get('summary', {}) or {})
        contact_rows = [row for row in list(fs.get('face_sets', []) or []) if any(k in str(row.get('surface_role', '')).lower() or k in str(row.get('name', '')).lower() for k in ('contact', 'interface', 'protected', 'split'))]
        contact_face_quality = {
            'face_set_count': int(fs_summary.get('face_set_count', 0) or 0),
            'boundary_face_set_count': int(fs_summary.get('boundary_face_set_count', 0) or 0),
            'internal_face_set_count': int(fs_summary.get('internal_face_set_count', 0) or 0),
            'contact_like_face_set_count': len(contact_rows),
            'unmatched_boundary_face_count': int(fs_summary.get('unmatched_boundary_face_count', 0) or 0),
            'matched_boundary_face_count': int(fs_summary.get('matched_boundary_face_count', 0) or 0),
            'normal_inconsistent_face_set_count': int(fs_summary.get('normal_inconsistent_face_set_count', 0) or 0),
            'min_contact_face_area': min([float(min(row.get('areas') or [0.0])) for row in contact_rows if row.get('areas')] or [0.0]),
        }
        if duplicate_nodes:
            issues.append({'id': 'mesh_quality.duplicate_nodes', 'severity': 'warning', 'count': duplicate_nodes, 'message': 'Duplicate node coordinates were detected; verify entity interfaces and merge policy.'})
        bad_ids = list(dict.fromkeys([*sliver, *inverted, *tiny, *poor_angle]))[:500]
        brep = dict(brep_document or {})
        volume_by_region = {str(row.get('region_name') or row.get('name') or ''): dict(row) for row in list(brep.get('volumes', []) or []) if isinstance(row, dict)}
        volume_by_occ = {str(row.get('occ_volume_tag') or ''): dict(row) for row in list(brep.get('volumes', []) or []) if isinstance(row, dict)}
        region_arr = np.asarray(getattr(grid, 'cell_data', {}).get('region_name', []), dtype=object) if hasattr(grid, 'cell_data') else np.asarray([], dtype=object)
        occ_arr = np.asarray(getattr(grid, 'cell_data', {}).get('occ_volume_tag', []), dtype=object) if hasattr(grid, 'cell_data') else np.asarray([], dtype=object)
        bad_refs: list[dict[str, Any]] = []
        for cid in bad_ids:
            region = str(region_arr[int(cid)]) if int(cid) < len(region_arr) else ''
            occ = str(occ_arr[int(cid)]) if int(cid) < len(occ_arr) else ''
            volume = volume_by_occ.get(occ) or volume_by_region.get(region) or {}
            flags = []
            if cid in sliver:
                flags.append('sliver')
            if cid in inverted:
                flags.append('inverted')
            if cid in tiny:
                flags.append('tiny')
            if cid in poor_angle:
                flags.append('poor_angle')
            bad_refs.append({
                'cell_id': int(cid),
                'region_name': region,
                'occ_volume_tag': occ,
                'brep_volume_id': volume.get('id') or volume.get('topology_entity_id') or (f'solid:{region}' if region else ''),
                'source_block': volume.get('source_block') or region,
                'quality_flags': flags,
                'recommended_target': volume.get('id') or volume.get('topology_entity_id') or region,
            })
        return MeshQualityReport(
            cell_count=int(getattr(grid, 'n_cells', 0) or 0),
            tetra_count=int(tets.shape[0]),
            min_signed_volume=float(np.min(volumes)),
            min_abs_volume=float(np.min(abs_vol)),
            max_aspect_ratio=float(np.max(aspect_arr)),
            mean_aspect_ratio=float(np.mean(aspect_arr)),
            min_dihedral_angle=float(np.min(dmin_arr)),
            max_dihedral_angle=float(np.max(dmax_arr)),
            min_radius_ratio=float(np.min(radius_arr)),
            min_scaled_jacobian=float(np.min(sj_arr)),
            sliver_cell_ids=sliver,
            inverted_cell_ids=inverted,
            tiny_cell_ids=tiny,
            poor_angle_cell_ids=poor_angle,
            duplicate_node_count=duplicate_nodes,
            contact_face_quality=contact_face_quality,
            bad_cell_geometry_refs=tuple(bad_refs),
            issues=tuple(issues),
        ).to_dict()


__all__ = ['MeshQualityEvaluator', 'MeshQualityReport']
