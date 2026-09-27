"""Lightweight directed graph for itinerary bookings. No external graph library —
keeps the demo dependency-free and the propagation logic transparent/explainable."""
from collections import deque
from app.models import BookingNode, DependencyEdge


class ItineraryGraph:
    def __init__(self, nodes: list[BookingNode], edges: list[DependencyEdge]):
        self.nodes: dict[str, BookingNode] = {n.id: n for n in nodes}
        self.edges: list[DependencyEdge] = edges
        self._successors: dict[str, list[DependencyEdge]] = {}
        self._predecessors: dict[str, list[DependencyEdge]] = {}
        for e in edges:
            self._successors.setdefault(e.source, []).append(e)
            self._predecessors.setdefault(e.target, []).append(e)

    def successors(self, node_id: str) -> list[DependencyEdge]:
        return self._successors.get(node_id, [])

    def predecessors(self, node_id: str) -> list[DependencyEdge]:
        return self._predecessors.get(node_id, [])

    def topological_order_from(self, start_id: str) -> list[str]:
        """BFS-based order of every node reachable from start_id (start_id included first)."""
        visited = {start_id}
        order = [start_id]
        queue = deque([start_id])
        while queue:
            current = queue.popleft()
            for edge in self.successors(current):
                if edge.target not in visited:
                    visited.add(edge.target)
                    order.append(edge.target)
                    queue.append(edge.target)
        return order

    def to_dict(self) -> dict:
        return {
            "nodes": [n.model_dump() for n in self.nodes.values()],
            "edges": [e.model_dump() for e in self.edges],
        }
