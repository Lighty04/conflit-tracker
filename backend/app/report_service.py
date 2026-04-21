from typing import Dict, List
from sqlalchemy.orm import Session
from .models import Node, Edge, NodeType, EdgeType
from .conflict_service import ConflictService

class ReportService:
    """Generate PDF-ready report data for a person or association"""
    
    def __init__(self, db: Session):
        self.db = db
        self.conflict = ConflictService(db)
    
    def generate_person_report(self, person_id: str) -> Dict:
        """Generate complete report data for a person"""
        person = self.db.query(Node).filter(Node.node_id == person_id).first()
        if not person:
            return {}
        
        aggregate = self.conflict.get_person_aggregate(person_id)
        
        # Get 2-hop network for graph data
        from .graph_service import GraphService
        graph = GraphService()
        graph.load_from_db(self.db)
        network = graph.get_neighbors(person_id, hops=2)
        
        # Calculate derived metrics
        boards = aggregate.get("boards", [])
        
        # Find top subventions
        top_subventions = sorted(boards, key=lambda x: x.get("subventions_received", 0), reverse=True)[:5]
        
        # Find strongest connections (co-members on multiple boards)
        co_members = aggregate.get("co_members", [])
        
        # Risk assessment
        risk_level = "LOW"
        if aggregate.get("conflict_score", 0) > 70:
            risk_level = "CRITICAL"
        elif aggregate.get("conflict_score", 0) > 40:
            risk_level = "HIGH"
        elif aggregate.get("conflict_score", 0) > 20:
            risk_level = "MEDIUM"
        
        return {
            "generated_at": None,  # Will be set by caller
            "report_type": "person_conflict_analysis",
            "subject": {
                "id": person.node_id,
                "name": person.name,
                "role": person.role,
                "conflict_score": aggregate.get("conflict_score", 0),
                "risk_level": risk_level,
                "is_membre_de_droit": aggregate.get("is_membre_de_droit", False),
            },
            "summary": {
                "board_count": aggregate.get("board_count", 0),
                "total_subventions_controlled": aggregate.get("total_subventions_controlled", 0),
                "unique_associations": len(boards),
                "co_members_count": len(co_members),
                "network_nodes": len(network.get("nodes", [])),
                "network_edges": len(network.get("edges", [])),
            },
            "boards": boards,
            "top_subventions": top_subventions,
            "co_members": co_members,
            "network": network,
            "risk_factors": self._generate_risk_factors(aggregate),
        }
    
    def _generate_risk_factors(self, aggregate: Dict) -> List[Dict]:
        """Generate list of risk factors with explanations"""
        factors = []
        
        if aggregate.get("is_membre_de_droit"):
            factors.append({
                "type": "MEMBRE_DE_DROIT",
                "severity": "HIGH",
                "description": "Personne nommée d'office (membre de droit) à un conseil d'administration",
                "impact": "Nomination automatique sans concurrence, potentiel conflit d'intérêts"
            })
        
        if aggregate.get("board_count", 0) > 1:
            factors.append({
                "type": "MULTIPLE_BOARDS",
                "severity": "MEDIUM" if aggregate["board_count"] <= 3 else "HIGH",
                "description": f"Siège sur {aggregate['board_count']} conseils d'administration",
                "impact": "Concentration du pouvoir décisionnaire dans les associations subventionnées"
            })
        
        if aggregate.get("total_subventions_controlled", 0) > 1000000:
            factors.append({
                "type": "HIGH_SUBVENTIONS",
                "severity": "HIGH",
                "description": f"Contrôle des associations recevant €{aggregate['total_subventions_controlled']:,.0f}",
                "impact": "Contrôle significatif de l'argent public via associations"
            })
        elif aggregate.get("total_subventions_controlled", 0) > 100000:
            factors.append({
                "type": "MEDIUM_SUBVENTIONS",
                "severity": "MEDIUM",
                "description": f"Contrôle des associations recevant €{aggregate['total_subventions_controlled']:,.0f}",
                "impact": "Contrôle modéré de l'argent public via associations"
            })
        
        return factors
