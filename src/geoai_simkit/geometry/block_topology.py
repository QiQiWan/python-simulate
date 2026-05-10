from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from geoai_simkit.geometry.mesh_policy import build_mesh_assembly_plan_payload


_SPLIT_CONTACT_KINDS = {'surface', 'solid'}
_SPLIT_REVIEW_KINDS = {'point', 'line'}


@dataclass(frozen=True, slots=True)
class BlockTopologyNode:
    """A lightweight, UI-safe topology node for one editable block/region."""

    name: str
    region_name: str | None = None
    material_name: str | None = None
    source: str = 'model'
    parent: str | None = None
    split_name: str | None = None
    role: str = 'block'
    exists_in_model: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'region_name': self.region_name,
            'material_name': self.material_name,
            'source': self.source,
            'parent': self.parent,
            'split_name': self.split_name,
            'role': self.role,
            'exists_in_model': bool(self.exists_in_model),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class BlockAdjacencyEdge:
    """A derived adjacency between two topology nodes."""

    name: str
    node_a: str
    node_b: str
    source: str = 'split'
    split_name: str | None = None
    split_kind: str | None = None
    relationship: str = 'candidate_contact'
    contact_mode: str = 'contact'
    mesh_policy: str = 'nonconforming_contact'
    confidence: str = 'derived'
    configured: bool = False
    exact_only: bool = False
    active_stages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'node_a': self.node_a,
            'node_b': self.node_b,
            'source': self.source,
            'split_name': self.split_name,
            'split_kind': self.split_kind,
            'relationship': self.relationship,
            'contact_mode': self.contact_mode,
            'mesh_policy': self.mesh_policy,
            'confidence': self.confidence,
            'configured': bool(self.configured),
            'exact_only': bool(self.exact_only),
            'active_stages': list(self.active_stages),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MeshPolicyRow:
    """A user-facing policy row linking topology adjacency to meshing/contact behavior."""

    edge_name: str
    policy: str
    contact_mode: str
    needs_review: bool = False
    reason: str = ''
    action: str = ''
    merge_allowed: bool = False
    assembly_group: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'edge_name': self.edge_name,
            'policy': self.policy,
            'contact_mode': self.contact_mode,
            'needs_review': bool(self.needs_review),
            'reason': self.reason,
            'action': self.action,
            'merge_allowed': bool(self.merge_allowed),
            'assembly_group': self.assembly_group,
        }


@dataclass(frozen=True, slots=True)
class BlockTopologyModel:
    """Minimal block topology graph for v5 Model Space.

    This object deliberately does not depend on PyVista/Gmsh. It is the stable
    semantic graph that the GUI, contact preparation and mesh-readiness gates
    can consume before heavy geometry kernels are loaded.
    """

    nodes: tuple[BlockTopologyNode, ...] = ()
    edges: tuple[BlockAdjacencyEdge, ...] = ()
    mesh_policies: tuple[MeshPolicyRow, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def node_names(self) -> tuple[str, ...]:
        return tuple(node.name for node in self.nodes)

    def edge_names(self) -> tuple[str, ...]:
        return tuple(edge.name for edge in self.edges)

    def to_dict(self) -> dict[str, Any]:
        mesh_assembly_plan = build_mesh_assembly_plan_payload(
            topology_edges=[edge.to_dict() for edge in self.edges],
            mesh_policy_rows=[row.to_dict() for row in self.mesh_policies],
            stage_names=list(self.metadata.get('stage_names', []) or []),
        )
        issue_counts = {
            'blocking': sum(1 for issue in self.issues if issue.get('severity') == 'blocking'),
            'warning': sum(1 for issue in self.issues if issue.get('severity') == 'warning'),
            'info': sum(1 for issue in self.issues if issue.get('severity') == 'info'),
        }
        configured_count = sum(1 for edge in self.edges if edge.configured)
        review_count = sum(1 for row in self.mesh_policies if row.needs_review)
        return {
            'nodes': [node.to_dict() for node in self.nodes],
            'edges': [edge.to_dict() for edge in self.edges],
            'adjacency_rows': [edge.to_dict() for edge in self.edges],
            'mesh_policy_rows': [row.to_dict() for row in self.mesh_policies],
            'issues': [dict(issue) for issue in self.issues],
            'issue_counts': issue_counts,
            'summary': {
                'node_count': len(self.nodes),
                'edge_count': len(self.edges),
                'configured_edge_count': configured_count,
                'unconfigured_edge_count': max(0, len(self.edges) - configured_count),
                'review_policy_count': review_count,
                'blocking_issue_count': issue_counts['blocking'],
                'warning_issue_count': issue_counts['warning'],
            },
            'mesh_assembly_plan': mesh_assembly_plan,
            'metadata': dict(self.metadata),
        }


def _text(value: Any) -> str:
    return str(value or '').strip()


def _issue(issue_id: str, severity: str, message: str, *, target: str, action: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'id': issue_id,
        'severity': severity,
        'message': message,
        'target': target,
        'action': action,
        'details': dict(details or {}),
    }


def normalize_split_definitions(split_definitions: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(list(split_definitions or []), start=1):
        if not isinstance(raw, dict):
            continue
        target = _text(raw.get('target_block') or raw.get('region_name') or raw.get('target'))
        if not target:
            continue
        kind = _text(raw.get('kind') or 'surface').lower() or 'surface'
        split_name = _text(raw.get('name') or f'{target}__split_{index:02d}')
        item = dict(raw)
        item['name'] = split_name
        item['target_block'] = target
        item['kind'] = kind
        rows.append(item)
    return rows


def _leaf_names_for_split(item: dict[str, Any]) -> tuple[str, str]:
    split_name = _text(item.get('name'))
    kind = _text(item.get('kind') or 'surface').lower()
    if kind == 'solid':
        return _text(item.get('inside_name') or f'{split_name}__inside'), _text(item.get('outside_name') or f'{split_name}__outside')
    return _text(item.get('negative_name') or f'{split_name}__neg'), _text(item.get('positive_name') or f'{split_name}__pos')


def _pair_name_for_split(split_name: str) -> str:
    return f'auto_split_contact:{split_name}'


def _configured_lookup(configured_contact_pairs: Iterable[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for pair in list(configured_contact_pairs or []):
        if not isinstance(pair, dict):
            continue
        name = _text(pair.get('pair_name') or pair.get('name'))
        if name:
            lookup[name] = dict(pair)
    return lookup


def build_block_topology(
    *,
    blocks: Iterable[dict[str, Any]] | None = None,
    split_definitions: Iterable[dict[str, Any]] | None = None,
    configured_contact_pairs: Iterable[dict[str, Any]] | None = None,
    mesh_hints: Iterable[dict[str, Any]] | None = None,
    stage_names: Iterable[str] | None = None,
) -> BlockTopologyModel:
    """Build a lightweight block topology graph from current workbench rows."""
    block_rows = [dict(row) for row in list(blocks or []) if isinstance(row, dict)]
    split_rows = normalize_split_definitions(split_definitions)
    configured = _configured_lookup(configured_contact_pairs)
    mesh_hint_lookup = {_text(row.get('block_name')): dict(row) for row in list(mesh_hints or []) if isinstance(row, dict) and _text(row.get('block_name'))}
    stage_name_tuple = tuple(_text(name) for name in list(stage_names or []) if _text(name))

    nodes: dict[str, BlockTopologyNode] = {}
    for row in block_rows:
        name = _text(row.get('name') or row.get('region_name'))
        if not name:
            continue
        nodes[name] = BlockTopologyNode(
            name=name,
            region_name=_text(row.get('region_name')) or name,
            material_name=_text(row.get('material_name')) or None,
            source='model',
            exists_in_model=True,
            metadata=dict(row.get('metadata', {}) or {}),
        )

    edges: list[BlockAdjacencyEdge] = []
    policies: list[MeshPolicyRow] = []
    issues: list[dict[str, Any]] = []

    for item in split_rows:
        split_name = _text(item.get('name'))
        target = _text(item.get('target_block'))
        kind = _text(item.get('kind') or 'surface').lower()
        leaf_a, leaf_b = _leaf_names_for_split(item)
        for leaf, role in ((leaf_a, 'split_child_a'), (leaf_b, 'split_child_b')):
            if leaf and leaf not in nodes:
                nodes[leaf] = BlockTopologyNode(
                    name=leaf,
                    region_name=leaf,
                    material_name=None,
                    source='split_virtual',
                    parent=target,
                    split_name=split_name,
                    role=role,
                    exists_in_model=False,
                    metadata={'split_kind': kind},
                )
        pair_name = _pair_name_for_split(split_name)
        pair = configured.get(pair_name, {})
        contact_ready = kind in _SPLIT_CONTACT_KINDS
        review_required = kind in _SPLIT_REVIEW_KINDS
        contact_mode = 'contact' if contact_ready else 'split_constraint'
        mesh_policy = 'nonconforming_contact' if contact_ready else 'topology_review_required'
        if pair:
            slave = _text(pair.get('slave_region') or leaf_a)
            master = _text(pair.get('master_region') or leaf_b)
            exact_only = bool(pair.get('exact_only', False))
            active_stages = tuple(_text(name) for name in list(pair.get('active_stages', []) or []) if _text(name))
        else:
            slave = leaf_a
            master = leaf_b
            exact_only = False
            active_stages = stage_name_tuple
        edge = BlockAdjacencyEdge(
            name=pair_name,
            node_a=slave,
            node_b=master,
            split_name=split_name,
            split_kind=kind,
            relationship='split_sibling',
            contact_mode=contact_mode,
            mesh_policy=mesh_policy,
            confidence='configured' if pair else 'derived',
            configured=bool(pair),
            exact_only=exact_only,
            active_stages=active_stages,
            metadata={
                'target_block': target,
                'axis': item.get('axis'),
                'coordinate': item.get('coordinate'),
                'has_mesh_hint_a': leaf_a in mesh_hint_lookup,
                'has_mesh_hint_b': leaf_b in mesh_hint_lookup,
            },
        )
        edges.append(edge)
        policies.append(MeshPolicyRow(
            edge_name=edge.name,
            policy=mesh_policy,
            contact_mode=contact_mode,
            needs_review=review_required or not edge.configured,
            merge_allowed=mesh_policy in {'shared_node_continuous', 'continuous'},
            assembly_group=f'contact_island::{leaf_a}|{leaf_b}' if mesh_policy in {'nonconforming_contact', 'interface_element', 'separated', 'topology_review_required'} else 'continuous',
            reason=(
                'Point/line splits do not define a full contact surface.' if review_required
                else ('Derived contact pair has not been synchronized into mesh preparation.' if not edge.configured else 'Configured split contact pair is ready.')
            ),
            action=(
                'Convert to a surface/solid split or manually define an interface policy.' if review_required
                else ('Run Sync split contact pairs.' if not edge.configured else 'Review active stages and exact-only matching as needed.')
            ),
        ))
        if review_required:
            issues.append(_issue(
                f'topology.{split_name}.review_required',
                'warning',
                f'Split {split_name!r} is a {kind} split and does not define a full contact surface.',
                target='structures_interfaces_studio',
                action='Convert to a surface/solid split or define a manual interface policy.',
                details={'split_name': split_name, 'kind': kind},
            ))
        if contact_ready and not pair:
            issues.append(_issue(
                f'topology.{split_name}.contact_unsynced',
                'warning',
                f'Split {split_name!r} has a derived contact pair that is not synchronized.',
                target='structures_interfaces_studio',
                action='Run Sync split contact pairs.',
                details={'pair_name': pair_name, 'split_name': split_name},
            ))
        if target and target not in nodes:
            issues.append(_issue(
                f'topology.{split_name}.target_missing',
                'warning',
                f'Split {split_name!r} targets block {target!r}, but that block is not visible in the current model browser.',
                target='geometry_studio',
                action='Refresh/rebuild geometry after applying split definitions.',
                details={'target_block': target, 'split_name': split_name},
            ))

    if split_rows and not edges:
        issues.append(_issue(
            'topology.no_edges',
            'warning',
            'Split definitions exist but no topology adjacency edges were derived.',
            target='geometry_studio',
            action='Inspect split definitions and rebuild topology.',
        ))

    return BlockTopologyModel(
        nodes=tuple(nodes.values()),
        edges=tuple(edges),
        mesh_policies=tuple(policies),
        issues=tuple(issues),
        metadata={'stage_names': list(stage_name_tuple), 'split_definition_count': len(split_rows)},
    )


def build_block_topology_payload(**kwargs: Any) -> dict[str, Any]:
    """Convenience wrapper for presenters and tests."""
    return build_block_topology(**kwargs).to_dict()


__all__ = [
    'BlockAdjacencyEdge',
    'BlockTopologyModel',
    'BlockTopologyNode',
    'MeshPolicyRow',
    'build_block_topology',
    'build_block_topology_payload',
    'normalize_split_definitions',
]
