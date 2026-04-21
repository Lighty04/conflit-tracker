import math
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func
from .models import Node, Edge, NodeType, EdgeType

class ConflictService:
    """Calculate conflict metrics and leaderboards"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_person_metrics(self):
        """Recalculate all person metrics with 0-100 conflict score"""
        persons = self.db.query(Node).filter(Node.type == NodeType.PERSON).all()
        
        for person in persons:
            # Count boards (outgoing MEMBER_OF edges)
            board_edges = self.db.query(Edge).filter(
                Edge.source_id == person.id,
                Edge.type == EdgeType.MEMBER_OF
            ).all()
            
            person.board_count = len(board_edges)
            
            # Sum subventions to those associations
            total_subv = 0
            for edge in board_edges:
                assoc = edge.target
                subv_edges = self.db.query(Edge).filter(
                    Edge.target_id == assoc.id,
                    Edge.type == EdgeType.SUBSIDIZES
                ).all()
                for se in subv_edges:
                    total_subv += se.amount or 0
            
            person.total_subventions_controlled = total_subv
            
            # Detect membre_de_droit — explicit public appointment only
            person.is_membre_de_droit = 0
            for edge in board_edges:
                role = (edge.role or "").lower()
                desc = (edge.description or "").lower()
                combined = role + " " + desc
                
                # Exclude standard corporate titles (NOT political appointments)
                corporate_skips = ["conseil d'administration", "conseil de surveillance"]
                for skip in corporate_skips:
                    if skip in combined:
                        combined = combined.replace(skip, "")  # Remove to prevent false match
                
                # Only explicit political appointment indicators
                if any(indicator in combined for indicator in [
                    "membre de droit", "constitutif de droit",
                    "membres de droit", "membres constitutifs de droit",
                    "représentant de la ville", "représentant de l'etat",
                    "représentant du maire", "représentant municipal",
                    "délégué du maire", "délégué municipal",
                    "adjoint au maire", "adjointe au maire",
                    "conseiller municipal", "conseillère municipal",
                    "conseiller de paris", "conseillère de paris",
                    "maire de ", "maire du ", "maire d'",
                    "président du conseil municipal",
                    "présidente du conseil municipal",
                    "membre du conseil municipal", "membre du conseil de paris",
                    "député", "sénateur", "sénatrice",
                    "ministre", "secrétaire d'état"
                ]):
                    person.is_membre_de_droit = 1
                    break
            
            # NEW: 0-100 conflict score algorithm
            score = 0
            
            # Base: membre de droit (automatic appointment) = 40 pts
            if person.is_membre_de_droit:
                score += 40
            
            # Multiple boards = concentration of power, max 45 pts
            if person.board_count > 1:
                score += min((person.board_count - 1) * 15, 45)
            
            # Money controlled, max 35 pts
            if total_subv > 500000:
                score += 35
            elif total_subv > 100000:
                score += 25
            elif total_subv > 50000:
                score += 15
            
            # Cap at 100
            person.conflict_score = min(score, 100)
        
        self.db.commit()
        return len(persons)
    
    def get_leaderboard(self, metric: str = "conflict_score", limit: int = 50) -> List[Dict]:
        """Get top persons by metric (conflict_score, total_subventions_controlled, board_count)"""
        
        valid_metrics = {
            "conflict_score": Node.conflict_score,
            "total_subventions_controlled": Node.total_subventions_controlled,
            "board_count": Node.board_count,
        }
        
        col = valid_metrics.get(metric, Node.conflict_score)
        
        persons = self.db.query(Node).filter(
            Node.type == NodeType.PERSON
        ).order_by(col.desc()).limit(limit).all()
        
        result = []
        for i, p in enumerate(persons, 1):
            # Get associations they sit on
            boards = self.db.query(Edge, Node).join(
                Node, Edge.target_id == Node.id
            ).filter(
                Edge.source_id == p.id,
                Edge.type == EdgeType.MEMBER_OF
            ).all()
            
            result.append({
                "rank": i,
                "id": p.node_id,
                "name": p.name,
                "conflict_score": round(p.conflict_score, 2) if p.conflict_score else 0,
                "total_subventions_controlled": round(p.total_subventions_controlled or 0, 2),
                "board_count": p.board_count or 0,
                "is_membre_de_droit": bool(p.is_membre_de_droit),
                "role": p.role,
                "boards": [{"name": n.name, "role": e.role} for e, n in boards[:5]]
            })
        
        return result
    
    def get_person_aggregate(self, person_id: str) -> Dict:
        """Full breakdown of a person's network: boards, total money, centrality"""
        person = self.db.query(Node).filter(Node.node_id == person_id).first()
        if not person:
            return {}
        
        # All boards they sit on
        boards = self.db.query(Edge, Node).join(
            Node, Edge.target_id == Node.id
        ).filter(
            Edge.source_id == person.id,
            Edge.type == EdgeType.MEMBER_OF
        ).all()
        
        board_details = []
        total_subv = 0
        
        for edge, assoc in boards:
            # Get subventions to this association
            subv_edges = self.db.query(Edge).filter(
                Edge.target_id == assoc.id,
                Edge.type == EdgeType.SUBSIDIZES
            ).all()
            
            subv_total = sum(se.amount or 0 for se in subv_edges)
            total_subv += subv_total
            
            board_details.append({
                "id": assoc.node_id,
                "name": assoc.name,
                "role": edge.role,
                "siret": assoc.siret,
                "total_budget": assoc.total_budget,
                "subventions_received": round(subv_total, 2),
                "source": edge.description or assoc.source
            })
        
        # Find co-board members (people on same boards)
        co_members = set()
        for edge, assoc in boards:
            other_edges = self.db.query(Edge, Node).join(
                Node, Edge.source_id == Node.id
            ).filter(
                Edge.target_id == assoc.id,
                Edge.type == EdgeType.MEMBER_OF,
                Node.id != person.id
            ).all()
            for oe, on in other_edges:
                co_members.add((on.node_id, on.name))
        
        return {
            "id": person.node_id,
            "name": person.name,
            "role": person.role,
            "conflict_score": round(person.conflict_score or 0, 2),
            "is_membre_de_droit": bool(person.is_membre_de_droit),
            "board_count": len(boards),
            "total_subventions_controlled": round(total_subv, 2),
            "boards": board_details,
            "co_members": [{"id": nid, "name": nname} for nid, nname in co_members]
        }
    
    def get_conflict_alerts(self, threshold_subv: float = 500000, threshold_boards: int = 3) -> List[Dict]:
        """Auto-flag high-risk persons"""
        
        alerts = []
        
        # Flag 1: High subventions controlled
        high_subv = self.db.query(Node).filter(
            Node.type == NodeType.PERSON,
            Node.total_subventions_controlled >= threshold_subv
        ).order_by(Node.total_subventions_controlled.desc()).all()
        
        for p in high_subv:
            alerts.append({
                "type": "HIGH_SUBVENTIONS",
                "severity": "HIGH" if p.total_subventions_controlled > 1000000 else "MEDIUM",
                "person_id": p.node_id,
                "person_name": p.name,
                "amount": round(p.total_subventions_controlled or 0, 2),
                "board_count": p.board_count,
                "message": f"{p.name} contrôle des associations recevant {p.total_subventions_controlled:,.0f}€ de subventions publiques"
            })
        
        # Flag 2: Multiple boards
        multi_board = self.db.query(Node).filter(
            Node.type == NodeType.PERSON,
            Node.board_count >= threshold_boards
        ).order_by(Node.board_count.desc()).all()
        
        for p in multi_board:
            alerts.append({
                "type": "MULTIPLE_BOARDS",
                "severity": "MEDIUM",
                "person_id": p.node_id,
                "person_name": p.name,
                "board_count": p.board_count,
                "message": f"{p.name} siège sur {p.board_count} conseils d'administration"
            })
        
        # Flag 3: Membre de droit + subventions
        membre_droit = self.db.query(Node).filter(
            Node.type == NodeType.PERSON,
            Node.is_membre_de_droit == 1,
            Node.total_subventions_controlled > 0
        ).all()
        
        for p in membre_droit:
            alerts.append({
                "type": "MEMBRE_DE_DROIT_CONFLICT",
                "severity": "HIGH",
                "person_id": p.node_id,
                "person_name": p.name,
                "amount": round(p.total_subventions_controlled or 0, 2),
                "message": f"{p.name} est membre de droit (nomination automatique) d'associations recevant des subventions"
            })
        
        return alerts
