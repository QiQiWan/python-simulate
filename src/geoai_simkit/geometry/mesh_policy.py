from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


CONTACT_LIKE_POLICIES = {'nonconforming_contact', 'interface_element', 'separated', 'topology_review_required'}
CONTINUOUS_POLICIES = {'shared_node_continuous', 'continuous'}


def _text(value: Any) -> str:
    return str(value or '').strip()


@dataclass(frozen=True, slots=True)
class MeshAssemblyPolicy:
    """Region-pair policy used by mesh assembly and contact preparation.

    The policy is intentionally lightweight.  It can be built from split-derived
    contact pairs, block-topology rows, or future CAD face adjacencies before any
    heavy meshing backend is loaded.
    """

    edge_name: str
    region_a: str
    region_b: str
    mesh_policy: str = 'nonconforming_contact'
    contact_mode: str = 'contact'
    active_stages: tuple[str, ...] = ()
    exact_only: bool = False
    source: str = 'contact_pair'
    needs_review: bool = False
    reason: str = ''
    action: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def merge_allowed(self) -> bool:
        return self.mesh_policy in CONTINUOUS_POLICIES

    @property
    def requires_contact_or_interface(self) -> bool:
        return self.mesh_policy in CONTACT_LIKE_POLICIES

    def to_dict(self) -> dict[str, Any]:
        return {
            'edge_name': self.edge_name,
            'region_a': self.region_a,
            'region_b': self.region_b,
            'mesh_policy': self.mesh_policy,
            'policy': self.mesh_policy,
            'contact_mode': self.contact_mode,
            'active_stages': list(self.active_stages),
            'exact_only': bool(self.exact_only),
            'source': self.source,
            'needs_review': bool(self.needs_review),
            'reason': self.reason,
            'action': self.action,
            'merge_allowed': bool(self.merge_allowed),
            'requires_contact_or_interface': bool(self.requires_contact_or_interface),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MeshAssemblyPlan:
    """A mesh-assembly plan that prevents accidental welding across contacts."""

    policies: tuple[MeshAssemblyPolicy, ...] = ()
    protected_regions: tuple[str, ...] = ()
    merge_group_overrides: dict[str, str] = field(default_factory=dict)
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def region_policy(self, region_name: str) -> str | None:
        region = _text(region_name)
        for policy in self.policies:
            if region in {policy.region_a, policy.region_b}:
                return policy.mesh_policy
        return None

    def merge_group_for(self, region_name: str, default_group: str) -> str:
        region = _text(region_name)
        return self.merge_group_overrides.get(region, default_group)

    def to_dict(self) -> dict[str, Any]:
        policy_rows = [policy.to_dict() for policy in self.policies]
        return {
            'policies': policy_rows,
            'policy_rows': policy_rows,
            'protected_regions': list(self.protected_regions),
            'merge_group_overrides': dict(self.merge_group_overrides),
            'issues': [dict(issue) for issue in self.issues],
            'summary': {
                'policy_count': len(self.policies),
                'protected_region_count': len(self.protected_regions),
                'merge_group_override_count': len(self.merge_group_overrides),
                'review_policy_count': sum(1 for policy in self.policies if policy.needs_review),
                'contact_like_policy_count': sum(1 for policy in self.policies if policy.requires_contact_or_interface),
                'continuous_policy_count': sum(1 for policy in self.policies if policy.merge_allowed),
            },
            'metadata': dict(self.metadata),
        }


def _issue(issue_id: str, severity: str, message: str, *, target: str = 'mesh_readiness', action: str = '', details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'id': issue_id,
        'severity': severity,
        'message': message,
        'target': target,
        'action': action,
        'details': dict(details or {}),
    }


def _policy_from_text(value: Any, *, kind: str = '', exact_only: bool = False) -> str:
    text = _text(value).lower()
    if text in CONTACT_LIKE_POLICIES | CONTINUOUS_POLICIES:
        return 'shared_node_continuous' if text == 'continuous' else text
    if kind in {'point', 'line'}:
        return 'topology_review_required'
    if exact_only:
        return 'interface_element'
    return 'nonconforming_contact'


def build_mesh_assembly_plan(
    *,
    contact_pairs: Iterable[dict[str, Any]] | None = None,
    topology_edges: Iterable[dict[str, Any]] | None = None,
    mesh_policy_rows: Iterable[dict[str, Any]] | None = None,
    stage_names: Iterable[str] | None = None,
    protected_surfaces: Iterable[dict[str, Any]] | None = None,
) -> MeshAssemblyPlan:
    """Build conservative merge/contact policy rows.

    The most important guarantee is that contact-like region pairs are removed
    from automatic shared-point welding groups.  This keeps split blocks editable
    and lets contact/interface generation operate on separated region point sets.
    """
    stage_tuple = tuple(_text(name) for name in list(stage_names or []) if _text(name))
    policy_by_edge: dict[str, MeshAssemblyPolicy] = {}
    mesh_policy_lookup: dict[str, dict[str, Any]] = {}
    for row in list(mesh_policy_rows or []):
        if not isinstance(row, dict):
            continue
        edge_name = _text(row.get('edge_name') or row.get('pair_name') or row.get('name'))
        if edge_name:
            mesh_policy_lookup[edge_name] = dict(row)

    for edge in list(topology_edges or []):
        if not isinstance(edge, dict):
            continue
        edge_name = _text(edge.get('name') or edge.get('edge_name'))
        region_a = _text(edge.get('node_a') or edge.get('region_a') or edge.get('slave_region'))
        region_b = _text(edge.get('node_b') or edge.get('region_b') or edge.get('master_region'))
        if not edge_name or not region_a or not region_b or region_a == region_b:
            continue
        policy_row = mesh_policy_lookup.get(edge_name, {})
        policy_name = _policy_from_text(policy_row.get('policy') or edge.get('mesh_policy'), kind=_text(edge.get('split_kind')), exact_only=bool(edge.get('exact_only')))
        needs_review = bool(policy_row.get('needs_review', False)) or policy_name == 'topology_review_required'
        policy_by_edge[edge_name] = MeshAssemblyPolicy(
            edge_name=edge_name,
            region_a=region_a,
            region_b=region_b,
            mesh_policy=policy_name,
            contact_mode=_text(edge.get('contact_mode') or policy_row.get('contact_mode') or 'contact'),
            active_stages=tuple(_text(name) for name in list(edge.get('active_stages', []) or []) if _text(name)) or stage_tuple,
            exact_only=bool(edge.get('exact_only', False)),
            source=_text(edge.get('source') or 'block_topology'),
            needs_review=needs_review,
            reason=_text(policy_row.get('reason')),
            action=_text(policy_row.get('action')),
            metadata={'split_name': edge.get('split_name'), 'split_kind': edge.get('split_kind'), **dict(edge.get('metadata', {}) or {})},
        )

    for pair in list(contact_pairs or []):
        if not isinstance(pair, dict):
            continue
        edge_name = _text(pair.get('pair_name') or pair.get('name'))
        region_a = _text(pair.get('slave_region') or pair.get('region_a'))
        region_b = _text(pair.get('master_region') or pair.get('region_b'))
        if not edge_name or not region_a or not region_b or region_a == region_b:
            continue
        meta = dict(pair.get('metadata', {}) or {})
        kind = _text(pair.get('kind') or meta.get('split_kind'))
        policy_name = _policy_from_text(pair.get('mesh_policy') or meta.get('mesh_policy'), kind=kind, exact_only=bool(pair.get('exact_only', False)))
        policy_by_edge[edge_name] = MeshAssemblyPolicy(
            edge_name=edge_name,
            region_a=region_a,
            region_b=region_b,
            mesh_policy=policy_name,
            contact_mode=_text(pair.get('contact_mode') or meta.get('contact_mode') or 'contact'),
            active_stages=tuple(_text(name) for name in list(pair.get('active_stages', []) or []) if _text(name)) or stage_tuple,
            exact_only=bool(pair.get('exact_only', False)),
            source='contact_pair',
            needs_review=policy_name == 'topology_review_required',
            reason='Contact pair requests non-welded mesh assembly.' if policy_name in CONTACT_LIKE_POLICIES else '',
            action='Keep regions in separate mesh groups and generate contact/interface definitions.' if policy_name in CONTACT_LIKE_POLICIES else '',
            metadata=meta,
        )

    for surface in list(protected_surfaces or []):
        if not isinstance(surface, dict):
            continue
        name = _text(surface.get('name') or surface.get('id'))
        meta = dict(surface.get('metadata', {}) or {})
        child_regions = [_text(item) for item in list(meta.get('child_regions', []) or []) if _text(item)]
        if len(child_regions) >= 2:
            region_a, region_b = child_regions[0], child_regions[1]
            edge_name = f'protected_surface:{name}' if name else f'protected_surface:{region_a}->{region_b}'
            policy_by_edge.setdefault(edge_name, MeshAssemblyPolicy(
                edge_name=edge_name,
                region_a=region_a,
                region_b=region_b,
                mesh_policy='nonconforming_contact',
                contact_mode='contact',
                active_stages=stage_tuple,
                exact_only=False,
                source='protected_surface',
                needs_review=False,
                reason='Protected split surface requests non-welded mesh assembly.',
                action='Keep child regions in separate mesh groups and preserve the split face for contact/interface generation.',
                metadata={'protected_surface': name, **meta},
            ))
    policies = tuple(policy_by_edge.values())
    protected: set[str] = set()
    overrides: dict[str, str] = {}
    issues: list[dict[str, Any]] = []
    for policy in policies:
        if policy.requires_contact_or_interface:
            for region in (policy.region_a, policy.region_b):
                protected.add(region)
                # A conservative override: isolate protected split/contact children so
                # continuum_soil welding cannot erase the intended interface.
                overrides[region] = f'contact_island::{region}'
        if policy.needs_review:
            issues.append(_issue(
                f'mesh_policy.{policy.edge_name}.review_required',
                'warning',
                f'Mesh/contact policy for {policy.edge_name!r} requires review.',
                action=policy.action or 'Review the contact or interface policy before final meshing.',
                details=policy.to_dict(),
            ))
    return MeshAssemblyPlan(
        policies=policies,
        protected_regions=tuple(sorted(protected)),
        merge_group_overrides=overrides,
        issues=tuple(issues),
        metadata={'stage_names': list(stage_tuple), 'protected_surface_count': len(list(protected_surfaces or []))},
    )


def build_mesh_assembly_plan_payload(**kwargs: Any) -> dict[str, Any]:
    return build_mesh_assembly_plan(**kwargs).to_dict()


def contact_pair_specs_to_rows(contact_pairs: Iterable[Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pair in list(contact_pairs or []):
        meta = dict(getattr(pair, 'metadata', {}) or {})
        rows.append({
            'pair_name': _text(getattr(pair, 'name', '')),
            'slave_region': _text(getattr(pair, 'slave_region', '')),
            'master_region': _text(getattr(pair, 'master_region', '')),
            'active_stages': [_text(name) for name in tuple(getattr(pair, 'active_stages', ()) or ()) if _text(name)],
            'exact_only': bool(getattr(pair, 'exact_only', False)),
            'kind': _text(meta.get('split_kind')),
            'mesh_policy': _text(meta.get('mesh_policy')),
            'contact_mode': _text(meta.get('contact_mode')),
            'metadata': meta,
        })
    return rows


__all__ = [
    'CONTACT_LIKE_POLICIES',
    'CONTINUOUS_POLICIES',
    'MeshAssemblyPlan',
    'MeshAssemblyPolicy',
    'build_mesh_assembly_plan',
    'build_mesh_assembly_plan_payload',
    'contact_pair_specs_to_rows',
]
