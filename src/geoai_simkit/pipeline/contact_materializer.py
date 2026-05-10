from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from geoai_simkit.core.model import InterfaceDefinition, SimulationModel
from geoai_simkit.pipeline.interface_requests import InterfaceMaterializationRequest
from geoai_simkit.pipeline.preprocess import build_node_pair_contact


@dataclass(frozen=True, slots=True)
class MaterializedContactRow:
    """Serializable handoff row for one materialized contact/interface request."""

    request_id: str
    interface_name: str
    request_type: str
    slave_region: str
    master_region: str
    status: str
    pair_count: int = 0
    active_stages: tuple[str, ...] = ()
    needs_review: bool = False
    can_assemble: bool = False
    message: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'request_id': self.request_id,
            'interface_name': self.interface_name,
            'request_type': self.request_type,
            'slave_region': self.slave_region,
            'master_region': self.master_region,
            'status': self.status,
            'pair_count': int(self.pair_count),
            'active_stages': list(self.active_stages),
            'needs_review': bool(self.needs_review),
            'can_assemble': bool(self.can_assemble),
            'message': self.message,
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ContactAssemblyRow:
    """Solver-readable node-pair penalty/contact row.

    This is deliberately lighter than a full nonlinear contact element. It gives
    the local/reference solver and GUI a stable contract: region pair, node pairs,
    activation scope and penalty parameters. Production backends can translate the
    same row into richer interface elements later.
    """

    interface_name: str
    interface_kind: str
    slave_region: str
    master_region: str
    active_stages: tuple[str, ...]
    node_pair_count: int
    effective_pair_count: int
    zero_length_pair_count: int
    missing_pair_count: int
    inactive_region_pair_count: int
    missing_geometry_pair_count: int
    kn: float
    ks: float
    friction_deg: float
    stage_active: bool = True
    request_type: str = 'node_pair_contact'
    source: str = 'model.interfaces'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'interface_name': self.interface_name,
            'interface_kind': self.interface_kind,
            'slave_region': self.slave_region,
            'master_region': self.master_region,
            'active_stages': list(self.active_stages),
            'node_pair_count': int(self.node_pair_count),
            'effective_pair_count': int(self.effective_pair_count),
            'zero_length_pair_count': int(self.zero_length_pair_count),
            'missing_pair_count': int(self.missing_pair_count),
            'inactive_region_pair_count': int(self.inactive_region_pair_count),
            'missing_geometry_pair_count': int(self.missing_geometry_pair_count),
            'kn': float(self.kn),
            'ks': float(self.ks),
            'friction_deg': float(self.friction_deg),
            'stage_active': bool(self.stage_active),
            'request_type': self.request_type,
            'source': self.source,
            'metadata': dict(self.metadata),
        }


def _as_request_rows(request_payload: Any = None, requests: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if requests is not None:
        for item in list(requests or []):
            if isinstance(item, InterfaceMaterializationRequest):
                rows.append(item.to_dict())
            elif isinstance(item, dict):
                rows.append(dict(item))
    if isinstance(request_payload, dict):
        raw = request_payload.get('requests') or request_payload.get('request_rows') or []
        for item in list(raw or []):
            if isinstance(item, InterfaceMaterializationRequest):
                rows.append(item.to_dict())
            elif isinstance(item, dict):
                rows.append(dict(item))
    return rows


def _request_text(row: dict[str, Any], key: str, default: str = '') -> str:
    return str(row.get(key) or default).strip()


def _request_stages(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(v) for v in list(row.get('active_stages', []) or []) if str(v))


def _existing_interface_names(model: SimulationModel) -> set[str]:
    return {str(item.name) for item in list(getattr(model, 'interfaces', []) or [])}


def materialize_interface_requests(
    model: SimulationModel,
    *,
    request_payload: Any = None,
    requests: Iterable[Any] | None = None,
    append: bool = True,
    overwrite_existing: bool = True,
    exact_only: bool = True,
    search_radius_factor: float = 1.25,
    default_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize request rows into model interfaces and release metadata.

    Supported materialization paths are intentionally conservative:
    * node_pair_contact -> InterfaceDefinition(kind='node_pair')
    * release_boundary -> metadata row for staged excavation/release handling
    * face_interface_element -> pending row unless an upstream interface exists
    """
    request_rows = _as_request_rows(request_payload=request_payload, requests=requests)
    if not append:
        model.interfaces = []
    existing = _existing_interface_names(model)
    materialized: list[MaterializedContactRow] = []
    release_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    params = {'kn': 5.0e8, 'ks': 1.0e8, 'friction_deg': 25.0}
    params.update(dict(default_parameters or {}))

    if overwrite_existing and request_rows:
        target_names = {str(row.get('interface_name') or row.get('name') or '') for row in request_rows}
        target_names.discard('')
        if target_names:
            model.interfaces = [item for item in list(model.interfaces) if str(item.name) not in target_names]
            existing = _existing_interface_names(model)

    for row in request_rows:
        request_type = _request_text(row, 'request_type')
        interface_name = _request_text(row, 'interface_name') or _request_text(row, 'name')
        slave_region = _request_text(row, 'slave_region') or _request_text(row, 'region_a')
        master_region = _request_text(row, 'master_region') or _request_text(row, 'region_b')
        request_id = _request_text(row, 'request_id') or f'{request_type}:{interface_name}'
        active_stages = _request_stages(row)
        needs_review = bool(row.get('needs_review', False))
        can_materialize = bool(row.get('can_materialize', True))
        if not interface_name or not slave_region or not master_region:
            materialized.append(MaterializedContactRow(
                request_id=request_id,
                interface_name=interface_name,
                request_type=request_type,
                slave_region=slave_region,
                master_region=master_region,
                status='skipped-invalid-request',
                needs_review=True,
                can_assemble=False,
                message='Request is missing interface name, slave region or master region.',
                metadata={'request_row': dict(row)},
            ))
            skipped_rows.append(dict(row))
            continue
        if needs_review or not can_materialize:
            materialized.append(MaterializedContactRow(
                request_id=request_id,
                interface_name=interface_name,
                request_type=request_type,
                slave_region=slave_region,
                master_region=master_region,
                status='skipped-review-required',
                needs_review=True,
                can_assemble=False,
                message='Request is marked as review-only or cannot be materialized automatically.',
                metadata={'request_row': dict(row)},
            ))
            skipped_rows.append(dict(row))
            continue
        if request_type == 'release_boundary':
            release = {
                'request_id': request_id,
                'interface_name': interface_name,
                'slave_region': slave_region,
                'master_region': master_region,
                'active_stages': list(active_stages),
                'mesh_policy': row.get('mesh_policy'),
                'source': 'pipeline.contact_materializer',
            }
            release_rows.append(release)
            materialized.append(MaterializedContactRow(
                request_id=request_id,
                interface_name=interface_name,
                request_type=request_type,
                slave_region=slave_region,
                master_region=master_region,
                status='recorded-release-boundary',
                pair_count=0,
                active_stages=active_stages,
                can_assemble=True,
                message='Release boundary recorded for staged excavation handoff.',
                metadata=release,
            ))
            continue
        if request_type != 'node_pair_contact':
            materialized.append(MaterializedContactRow(
                request_id=request_id,
                interface_name=interface_name,
                request_type=request_type,
                slave_region=slave_region,
                master_region=master_region,
                status='pending-non-node-pair-request',
                active_stages=active_stages,
                can_assemble=False,
                message='Only node_pair_contact is automatically materialized in the lightweight backend.',
                metadata={'request_row': dict(row)},
            ))
            skipped_rows.append(dict(row))
            continue
        if interface_name in existing:
            existing_item = next((item for item in model.interfaces if str(item.name) == interface_name), None)
            pair_count = 0 if existing_item is None else min(len(existing_item.slave_point_ids), len(existing_item.master_point_ids))
            materialized.append(MaterializedContactRow(
                request_id=request_id,
                interface_name=interface_name,
                request_type=request_type,
                slave_region=slave_region,
                master_region=master_region,
                status='already-present',
                pair_count=pair_count,
                active_stages=active_stages,
                can_assemble=pair_count > 0,
                message='Interface already exists on the model.',
                metadata={'request_row': dict(row)},
            ))
            continue
        metadata = {
            'source': 'pipeline.contact_materializer',
            'request_id': request_id,
            'request_type': request_type,
            'mesh_policy': row.get('mesh_policy'),
            'stage_scope': row.get('stage_scope'),
            'request_row': dict(row),
        }
        interface = build_node_pair_contact(
            model,
            slave_region=slave_region,
            master_region=master_region,
            active_stages=active_stages,
            parameters=params,
            name=interface_name,
            search_radius_factor=float(search_radius_factor),
            exact_only=bool(exact_only),
            avoid_identical_pairs=False,
            metadata=metadata,
        )
        if interface is None:
            materialized.append(MaterializedContactRow(
                request_id=request_id,
                interface_name=interface_name,
                request_type=request_type,
                slave_region=slave_region,
                master_region=master_region,
                status='skipped-no-node-pairs',
                active_stages=active_stages,
                can_assemble=False,
                message='No coincident or nearby node pairs were found for this contact request.',
                metadata={'request_row': dict(row)},
            ))
            skipped_rows.append(dict(row))
            continue
        model.interfaces.append(interface)
        existing.add(interface_name)
        pair_count = min(len(interface.slave_point_ids), len(interface.master_point_ids))
        materialized.append(MaterializedContactRow(
            request_id=request_id,
            interface_name=interface_name,
            request_type=request_type,
            slave_region=slave_region,
            master_region=master_region,
            status='materialized-node-pair-contact',
            pair_count=pair_count,
            active_stages=tuple(interface.active_stages),
            can_assemble=pair_count > 0,
            message='Node-pair contact interface was added to the model.',
            metadata={'interface_metadata': dict(interface.metadata or {}), 'request_row': dict(row)},
        ))

    model.metadata['materialized_release_boundaries'] = release_rows
    rows = [item.to_dict() for item in materialized]
    summary = {
        'request_count': len(request_rows),
        'materialized_interface_count': sum(1 for item in materialized if item.status == 'materialized-node-pair-contact'),
        'already_present_count': sum(1 for item in materialized if item.status == 'already-present'),
        'release_boundary_count': len(release_rows),
        'skipped_count': len(skipped_rows),
        'node_pair_count': int(sum(int(item.pair_count) for item in materialized)),
        'can_assemble_count': sum(1 for item in materialized if item.can_assemble),
        'review_count': sum(1 for item in materialized if item.needs_review),
    }
    payload = {'summary': summary, 'rows': rows, 'release_boundaries': release_rows, 'skipped_requests': skipped_rows}
    model.metadata['contact_materialization'] = payload
    return payload


def _stage_is_active(active_stages: tuple[str, ...], stage_name: str | None) -> bool:
    if not active_stages:
        return True
    if not stage_name:
        return True
    return str(stage_name) in {str(v) for v in active_stages}


def _interface_regions(interface: InterfaceDefinition) -> tuple[str, str]:
    meta = dict(interface.metadata or {})
    return str(meta.get('slave_region') or ''), str(meta.get('master_region') or '')


def _contact_parameter(interface: InterfaceDefinition, name: str, default: float) -> float:
    try:
        return float(dict(interface.parameters or {}).get(name, default) or default)
    except Exception:
        return float(default)


def build_contact_solver_assembly_table(
    model: SimulationModel,
    *,
    stage_name: str | None = None,
    global_to_local: dict[int, int] | None = None,
    active_regions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build a lightweight solver-readable contact table from model interfaces."""
    rows: list[ContactAssemblyRow] = []
    active_region_set = {str(v) for v in tuple(active_regions or ()) if str(v)}
    has_active_region_filter = bool(active_region_set)
    total_pairs = 0
    active_pairs = 0
    zero_pairs = 0
    missing_pairs = 0
    inactive_region_pairs = 0
    missing_geometry_pairs = 0
    for interface in list(getattr(model, 'interfaces', []) or []):
        kind = str(interface.kind or '').lower()
        if kind not in {'node_pair', 'node_pair_contact', 'contact'}:
            continue
        active_stages = tuple(str(v) for v in tuple(interface.active_stages or ()) if str(v))
        active = _stage_is_active(active_stages, stage_name)
        slave_ids = tuple(int(v) for v in tuple(interface.slave_point_ids or ()))
        master_ids = tuple(int(v) for v in tuple(interface.master_point_ids or ()))
        pair_count = min(len(slave_ids), len(master_ids))
        slave_region, master_region = _interface_regions(interface)
        region_active = True
        inactive_regions: list[str] = []
        if has_active_region_filter:
            for region_name in (slave_region, master_region):
                if region_name and region_name not in active_region_set and region_name not in inactive_regions:
                    inactive_regions.append(region_name)
            region_active = len(inactive_regions) == 0
        missing = 0
        missing_geometry = 0
        inactive_region_missing = 0
        zero = 0
        effective = 0
        if global_to_local is None:
            for slave, master in zip(slave_ids[:pair_count], master_ids[:pair_count], strict=False):
                if int(slave) == int(master):
                    zero += 1
                else:
                    if region_active:
                        effective += 1
                    else:
                        inactive_region_missing += 1
        else:
            for slave, master in zip(slave_ids[:pair_count], master_ids[:pair_count], strict=False):
                if int(slave) not in global_to_local or int(master) not in global_to_local:
                    missing += 1
                    if not region_active:
                        inactive_region_missing += 1
                    else:
                        missing_geometry += 1
                    continue
                if int(slave) == int(master) or int(global_to_local[int(slave)]) == int(global_to_local[int(master)]):
                    zero += 1
                    continue
                if not region_active:
                    inactive_region_missing += 1
                    continue
                effective += 1
        row = ContactAssemblyRow(
            interface_name=str(interface.name),
            interface_kind=str(interface.kind),
            slave_region=slave_region,
            master_region=master_region,
            active_stages=active_stages,
            node_pair_count=pair_count,
            effective_pair_count=effective if active else 0,
            zero_length_pair_count=zero if active else 0,
            missing_pair_count=missing if active else 0,
            inactive_region_pair_count=inactive_region_missing if active else 0,
            missing_geometry_pair_count=missing_geometry if active else 0,
            kn=_contact_parameter(interface, 'kn', 5.0e8),
            ks=_contact_parameter(interface, 'ks', 1.0e8),
            friction_deg=_contact_parameter(interface, 'friction_deg', 25.0),
            stage_active=active,
            metadata={
                'interface_metadata': dict(interface.metadata or {}),
                'has_global_to_local_filter': global_to_local is not None,
                'has_active_region_filter': has_active_region_filter,
                'region_active': bool(region_active),
                'inactive_regions': inactive_regions,
            },
        )
        rows.append(row)
        total_pairs += pair_count
        if active:
            active_pairs += effective
            zero_pairs += zero
            missing_pairs += missing
            inactive_region_pairs += inactive_region_missing
            missing_geometry_pairs += missing_geometry
    rows_dict = [row.to_dict() for row in rows]
    return {
        'summary': {
            'interface_count': len(rows),
            'stage_name': stage_name,
            'active_interface_count': sum(1 for row in rows if row.stage_active),
            'total_node_pair_count': int(total_pairs),
            'effective_pair_count': int(active_pairs),
            'zero_length_pair_count': int(zero_pairs),
            'missing_pair_count': int(missing_pairs),
            'inactive_region_pair_count': int(inactive_region_pairs),
            'missing_geometry_pair_count': int(missing_geometry_pairs),
            'missing_contact_classification': 'inactive_region_or_geometry_v1',
            'solver_contract': 'node_pair_penalty_contact_v1',
        },
        'rows': rows_dict,
    }


def _contact_pair_stiffness_triplets(sdofs: tuple[int, int, int], mdofs: tuple[int, int, int], Kpair: np.ndarray) -> tuple[list[int], list[int], list[float]]:
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    K = np.asarray(Kpair, dtype=float).reshape(3, 3)
    for a in range(3):
        for b in range(3):
            value = float(K[a, b])
            if abs(value) <= 0.0:
                continue
            sdof_a = int(sdofs[a])
            sdof_b = int(sdofs[b])
            mdof_a = int(mdofs[a])
            mdof_b = int(mdofs[b])
            rows.extend([sdof_a, mdof_a, sdof_a, mdof_a])
            cols.extend([sdof_b, mdof_b, mdof_b, sdof_b])
            vals.extend([value, value, -value, -value])
    return rows, cols, vals


def penalty_contact_triplets_for_submesh(
    interfaces: Iterable[InterfaceDefinition],
    *,
    global_to_local: dict[int, int],
    stage_name: str | None = None,
    ndof: int,
    active_regions: Iterable[str] | None = None,
    points: np.ndarray | None = None,
    displacements: np.ndarray | None = None,
    contact_active_set: str = 'always_closed',
    gap_tolerance: float = 1.0e-9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Return sparse triplets for node-pair frictional contact.

    The old component-wise penalty spring assumed a global z-normal. This version
    builds each pair in a local normal/tangent basis and records complementarity
    diagnostics for the nonlinear active-set loop.
    """
    from geoai_simkit.materials.interface import CoulombInterfaceMaterial

    row_ids: list[int] = []
    col_ids: list[int] = []
    data: list[float] = []
    used_pairs = 0
    skipped_same = 0
    skipped_missing = 0
    skipped_inactive = 0
    skipped_inactive_region = 0
    skipped_missing_geometry = 0
    interface_count = 0
    closed_pair_count = 0
    open_pair_count = 0
    stick_pair_count = 0
    slip_pair_count = 0
    max_gap = 0.0
    min_gap = 0.0
    max_lambda_n = 0.0
    max_friction_violation = 0.0
    max_complementarity = 0.0
    pair_rows: list[dict[str, Any]] = []
    active_set_mode = str(contact_active_set or 'always_closed').strip().lower()
    strict_friction = active_set_mode in {'strict_frictional', 'frictional', 'coulomb', 'semismooth', 'complementarity'}
    gap_controlled = active_set_mode in {'open_close', 'normal_gap', 'gap', 'strict_frictional', 'frictional', 'coulomb', 'semismooth', 'complementarity'}
    pts = None if points is None else np.asarray(points, dtype=float)
    disp = None if displacements is None else np.asarray(displacements, dtype=float)
    active_region_set = {str(v) for v in tuple(active_regions or ()) if str(v)}
    has_active_region_filter = bool(active_region_set)
    for interface in list(interfaces or []):
        if str(interface.kind or '').lower() not in {'node_pair', 'node_pair_contact', 'contact'}:
            continue
        active_stages = tuple(str(v) for v in tuple(interface.active_stages or ()) if str(v))
        if not _stage_is_active(active_stages, stage_name):
            skipped_inactive += min(len(interface.slave_point_ids), len(interface.master_point_ids))
            continue
        interface_count += 1
        slave_region, master_region = _interface_regions(interface)
        inactive_regions: list[str] = []
        if has_active_region_filter:
            for region_name in (slave_region, master_region):
                if region_name and region_name not in active_region_set and region_name not in inactive_regions:
                    inactive_regions.append(region_name)
        region_active = len(inactive_regions) == 0
        kn = _contact_parameter(interface, 'kn', 5.0e8)
        ks = _contact_parameter(interface, 'ks', 1.0e8)
        friction_deg = _contact_parameter(interface, 'friction_deg', 25.0)
        cohesion = _contact_parameter(interface, 'cohesion', 0.0)
        material = CoulombInterfaceMaterial(kn=kn, ks=ks, friction_deg=friction_deg, cohesion=cohesion)
        for pair_index, (slave, master) in enumerate(zip(tuple(interface.slave_point_ids), tuple(interface.master_point_ids), strict=False)):
            s_global = int(slave)
            m_global = int(master)
            if s_global not in global_to_local or m_global not in global_to_local:
                skipped_missing += 1
                if not region_active:
                    skipped_inactive_region += 1
                else:
                    skipped_missing_geometry += 1
                continue
            if not region_active:
                skipped_inactive_region += 1
                continue
            s_local = int(global_to_local[s_global])
            m_local = int(global_to_local[m_global])
            if s_local == m_local:
                skipped_same += 1
                continue
            if pts is not None:
                xs0 = np.asarray(pts[s_local], dtype=float)
                xm0 = np.asarray(pts[m_local], dtype=float)
            else:
                xs0 = np.zeros(3, dtype=float)
                xm0 = np.array([0.0, 0.0, 1.0], dtype=float)
            normal = xm0 - xs0
            nrm = float(np.linalg.norm(normal))
            if nrm <= 1.0e-14:
                normal = np.array([0.0, 0.0, 1.0], dtype=float)
            else:
                normal = normal / nrm
            us = np.zeros(3, dtype=float) if disp is None else np.asarray(disp[s_local], dtype=float)
            um = np.zeros(3, dtype=float) if disp is None else np.asarray(disp[m_local], dtype=float)
            jump = (xm0 + um) - (xs0 + us)
            if active_set_mode == 'always_closed' and disp is None:
                state, _traction, Kpair, comp = material.update(-normal * 1.0e-12, normal, gap_tolerance=gap_tolerance)
                gap = 0.0
                comp['gap'] = 0.0
                comp['status'] = 'stick'
            else:
                state, _traction, Kpair, comp = material.update(jump, normal, gap_tolerance=gap_tolerance)
                gap = float(comp.get('gap', state.normal_gap))
            max_gap = max(max_gap, float(gap))
            min_gap = min(min_gap, float(gap))
            max_lambda_n = max(max_lambda_n, float(comp.get('lambda_n', 0.0) or 0.0))
            max_friction_violation = max(max_friction_violation, float(comp.get('friction_violation', 0.0) or 0.0))
            max_complementarity = max(max_complementarity, float(comp.get('normal_complementarity', 0.0) or 0.0))
            status = str(comp.get('status', state.status))
            if gap_controlled and gap > float(gap_tolerance) and active_set_mode != 'always_closed':
                open_pair_count += 1
                if len(pair_rows) < 200:
                    pair_rows.append({'interface_name': str(interface.name), 'pair_index': int(pair_index), 'status': 'open', 'gap': float(gap), 'lambda_n': 0.0})
                continue
            closed_pair_count += 1
            if status == 'slip':
                slip_pair_count += 1
            elif status == 'stick':
                stick_pair_count += 1
            sdofs = tuple(3 * s_local + comp_i for comp_i in range(3))
            mdofs = tuple(3 * m_local + comp_i for comp_i in range(3))
            if max((*sdofs, *mdofs)) >= int(ndof):
                skipped_missing += 1
                skipped_missing_geometry += 1
                continue
            rr, cc, vv = _contact_pair_stiffness_triplets(sdofs, mdofs, Kpair)
            row_ids.extend(rr)
            col_ids.extend(cc)
            data.extend(vv)
            used_pairs += 1
            if len(pair_rows) < 200:
                pair_rows.append({
                    'interface_name': str(interface.name),
                    'pair_index': int(pair_index),
                    'status': status,
                    'gap': float(gap),
                    'lambda_n': float(comp.get('lambda_n', 0.0) or 0.0),
                    'friction_limit': float(comp.get('friction_limit', 0.0) or 0.0),
                    'friction_violation': float(comp.get('friction_violation', 0.0) or 0.0),
                })
    summary = {
        'interface_count': int(interface_count),
        'used_pair_count': int(used_pairs),
        'skipped_same_node_pair_count': int(skipped_same),
        'skipped_missing_node_pair_count': int(skipped_missing),
        'skipped_missing_geometry_pair_count': int(skipped_missing_geometry),
        'skipped_inactive_region_pair_count': int(skipped_inactive_region),
        'skipped_inactive_pair_count': int(skipped_inactive),
        'triplet_count': int(len(data)),
        'stage_name': stage_name,
        'active_set_mode': active_set_mode,
        'strict_frictional_complementarity': bool(strict_friction),
        'closed_pair_count': int(closed_pair_count),
        'open_pair_count': int(open_pair_count),
        'stick_pair_count': int(stick_pair_count),
        'slip_pair_count': int(slip_pair_count),
        'max_gap': float(max_gap),
        'min_gap': float(min_gap),
        'max_normal_multiplier': float(max_lambda_n),
        'max_friction_violation': float(max_friction_violation),
        'max_complementarity_violation': float(max_complementarity),
        'gap_tolerance': float(gap_tolerance),
        'pair_rows': pair_rows,
        'solver_contract': 'node_pair_coulomb_contact_complementarity_v2' if strict_friction else 'node_pair_penalty_contact_active_set_v1',
        'extended_solver_contract': 'node_pair_coulomb_contact_complementarity_v2',
    }
    return (
        np.asarray(row_ids, dtype=np.int64),
        np.asarray(col_ids, dtype=np.int64),
        np.asarray(data, dtype=float),
        summary,
    )

__all__ = [
    'ContactAssemblyRow',
    'MaterializedContactRow',
    'build_contact_solver_assembly_table',
    'materialize_interface_requests',
    'penalty_contact_triplets_for_submesh',
]
