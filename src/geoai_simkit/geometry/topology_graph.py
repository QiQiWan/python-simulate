from __future__ import annotations

"""Topology graph for block, face and contact relations."""

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

TopologyNodeType = Literal["block", "face", "edge", "point", "support", "interface", "stage", "material", "mesh_cell", "result", "feature", "cluster", "volume", "boundary", "load"]
TopologyRelation = Literal[
    "owns",
    "adjacent_to",
    "bounded_by",
    "connected_to",
    "contacts",
    "embedded_in",
    "activated_by",
    "deactivated_by",
    "mapped_to",
    "derived_from",
    "generated_by",
    "candidate_interface",
]


@dataclass(slots=True)
class TopologyNode:
    id: str
    type: TopologyNodeType
    label: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "label": self.label or self.id, "attributes": dict(self.attributes)}


@dataclass(slots=True)
class TopologyEdge:
    source: str
    target: str
    relation: TopologyRelation
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.target, self.relation)

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "relation": self.relation, "attributes": dict(self.attributes)}


@dataclass(slots=True)
class TopologyGraph:
    nodes: dict[str, TopologyNode] = field(default_factory=dict)
    edges: list[TopologyEdge] = field(default_factory=list)

    def add_node(self, node_id: str, node_type: TopologyNodeType, *, label: str = "", **attributes: Any) -> TopologyNode:
        node = self.nodes.get(node_id)
        if node is None:
            node = TopologyNode(id=node_id, type=node_type, label=label or node_id, attributes=dict(attributes))
            self.nodes[node_id] = node
        else:
            node.type = node_type
            if label:
                node.label = label
            node.attributes.update(attributes)
        return node

    def add_edge(self, source: str, target: str, relation: TopologyRelation, **attributes: Any) -> TopologyEdge:
        edge = TopologyEdge(source=source, target=target, relation=relation, attributes=dict(attributes))
        if edge.key not in {item.key for item in self.edges}:
            self.edges.append(edge)
        else:
            for item in self.edges:
                if item.key == edge.key:
                    item.attributes.update(attributes)
                    return item
        return edge

    def outgoing(self, node_id: str, relation: TopologyRelation | None = None) -> list[TopologyEdge]:
        return [edge for edge in self.edges if edge.source == node_id and (relation is None or edge.relation == relation)]

    def incoming(self, node_id: str, relation: TopologyRelation | None = None) -> list[TopologyEdge]:
        return [edge for edge in self.edges if edge.target == node_id and (relation is None or edge.relation == relation)]

    def adjacent_blocks(self, block_id: str) -> list[str]:
        out: list[str] = []
        for edge in self.edges:
            if edge.relation not in {"adjacent_to", "contacts"}:
                continue
            if edge.source == block_id and edge.target not in out:
                out.append(edge.target)
            elif edge.target == block_id and edge.source not in out:
                out.append(edge.source)
        return out

    def contact_edges(self) -> list[TopologyEdge]:
        return [edge for edge in self.edges if edge.relation == "contacts"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "contact_count": len(self.contact_edges()),
        }


def build_topology_from_foundation_pit_artifact(artifact: dict[str, Any]) -> TopologyGraph:
    graph = TopologyGraph()
    for block in list(artifact.get("blocks", []) or []):
        block_id = str(block.get("name") or block.get("id"))
        if not block_id:
            continue
        graph.add_node(
            block_id,
            "block",
            label=block_id,
            role=block.get("role", "unknown"),
            material_id=block.get("material_name"),
            layer_id=block.get("layer_name"),
            bounds=list(block.get("bounds", []) or []),
        )
    for face in list(artifact.get("face_tags", []) or []):
        face_id = str(face.get("tag") or face.get("id"))
        owner = str(face.get("block_name") or face.get("owner_block_id") or "")
        if not face_id or not owner:
            continue
        graph.add_node(face_id, "face", label=face_id, axis=face.get("axis"), side=face.get("side"), area=face.get("area"), role=face.get("role"))
        graph.add_edge(owner, face_id, "owns", face_role=face.get("role"), area=face.get("area"))
        graph.add_edge(face_id, owner, "bounded_by")
    for pair in list(artifact.get("contact_pairs", []) or []):
        a = str(pair.get("block_a") or pair.get("region_a") or "")
        b = str(pair.get("block_b") or pair.get("region_b") or "")
        if not a or not b:
            continue
        graph.add_edge(a, b, "adjacent_to", axis=pair.get("axis"), overlap_area=pair.get("overlap_area"), contact_mode=pair.get("contact_mode"))
        graph.add_edge(a, b, "contacts", name=pair.get("name"), mesh_policy=pair.get("mesh_policy"), active_stages=list(pair.get("active_stages", []) or []))
    for row in list(artifact.get("interface_requests", []) or []):
        iid = str(row.get("interface_name") or row.get("name") or row.get("request_type") or "interface")
        graph.add_node(iid, "interface", label=iid, request_type=row.get("request_type"), contact_mode=row.get("contact_mode"), stage_policy=row.get("stage_policy"))
        a = str(row.get("region_a") or "")
        b = str(row.get("region_b") or "")
        if a:
            graph.add_edge(iid, a, "connected_to")
        if b:
            graph.add_edge(iid, b, "connected_to")
    for stage in list(artifact.get("stage_rows", []) or []):
        sid = str(stage.get("name") or "")
        if not sid:
            continue
        graph.add_node(sid, "stage", label=sid, role=stage.get("role"), excavation_depth=stage.get("excavation_depth"))
        for bid in list(stage.get("activate_blocks", []) or []):
            graph.add_edge(bid, sid, "activated_by")
        for bid in list(stage.get("deactivate_blocks", []) or []):
            graph.add_edge(bid, sid, "deactivated_by")
    return graph


__all__ = ["TopologyNode", "TopologyEdge", "TopologyGraph", "build_topology_from_foundation_pit_artifact"]
