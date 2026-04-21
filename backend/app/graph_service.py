import networkx as nx
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from .models import Node, Edge, NodeType, EdgeType

class GraphService:
    def __init__(self):
        self.graph = nx.DiGraph()
    
    def load_from_db(self, db: Session):
        """Load entire graph from database into NetworkX"""
        self.graph.clear()
        
        # Add all nodes
        for node in db.query(Node).all():
            self.graph.add_node(
                node.node_id,
                type=node.type.value,
                name=node.name,
                siret=node.siret,
                sector=node.sector,
                total_budget=node.total_budget,
                role=node.role,
                institution_type=node.institution_type,
                source=node.source
            )
        
        # Add all edges
        for edge in db.query(Edge).all():
            self.graph.add_edge(
                edge.source.node_id,
                edge.target.node_id,
                type=edge.type.value,
                role=edge.role,
                amount=edge.amount,
                year=edge.year,
                severity=edge.severity,
                description=edge.description
            )
    
    def get_neighbors(self, node_id: str, hops: int = 1) -> Dict:
        """Get n-hop neighborhood of a node for visualization"""
        if node_id not in self.graph:
            return {"nodes": [], "edges": []}
        
        # BFS to find nodes within n hops
        visited = {node_id}
        frontier = {node_id}
        edges = []
        
        for _ in range(hops):
            new_frontier = set()
            for n in frontier:
                for neighbor in self.graph.successors(n):
                    edges.append((n, neighbor, dict(self.graph.edges[n, neighbor])))
                    new_frontier.add(neighbor)
                for neighbor in self.graph.predecessors(n):
                    edges.append((neighbor, n, dict(self.graph.edges[neighbor, n])))
                    new_frontier.add(neighbor)
            frontier = new_frontier - visited
            visited.update(frontier)
        
        nodes_data = []
        for n_id in visited:
            nodes_data.append({
                "id": n_id,
                **self.graph.nodes[n_id]
            })
        
        edges_data = []
        seen_edges = set()
        for src, tgt, attrs in edges:
            key = tuple(sorted([src, tgt]))
            if key not in seen_edges:
                seen_edges.add(key)
                edges_data.append({
                    "source": src,
                    "target": tgt,
                    **attrs
                })
        
        return {"nodes": nodes_data, "edges": edges_data}
    
    def find_path(self, source: str, target: str) -> Optional[List[str]]:
        """Find shortest path between two nodes"""
        try:
            # Convert to undirected for path finding
            undirected = self.graph.to_undirected()
            return nx.shortest_path(undirected, source, target)
        except nx.NetworkXNoPath:
            return None
    
    def get_centrality(self, node_id: str) -> Dict:
        """Get centrality metrics for a node"""
        if node_id not in self.graph:
            return {}
        
        undirected = self.graph.to_undirected()
        
        return {
            "degree_centrality": nx.degree_centrality(undirected).get(node_id, 0),
            "betweenness_centrality": nx.betweenness_centrality(undirected).get(node_id, 0),
            "closeness_centrality": nx.closeness_centrality(undirected).get(node_id, 0)
        }
    
    def search_nodes(self, query: str, limit: int = 20) -> List[Dict]:
        """Search nodes by name"""
        results = []
        query_lower = query.lower()
        
        for node_id, attrs in self.graph.nodes(data=True):
            if query_lower in attrs.get("name", "").lower():
                results.append({
                    "id": node_id,
                    **attrs
                })
        
        return results[:limit]
