"""Minimal dependency graph: nodes are risk components, edges mean 'depends on'."""
from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    kind: str  # chain | issuer | asset | oracle | amm | lending
    label: str
    data: dict = field(default_factory=dict)


@dataclass
class Edge:
    source: str  # the dependent
    target: str  # what it depends on
    relation: str
    exposure_usd: float | None = None


@dataclass
class Graph:
    nodes: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)

    def add_node(self, node):
        self.nodes.setdefault(node.id, node)

    def add_edge(self, source, target, relation, exposure_usd=None):
        self.edges.append(Edge(source, target, relation, exposure_usd))

    def dependencies_of(self, node_id):
        return [e for e in self.edges if e.source == node_id]
