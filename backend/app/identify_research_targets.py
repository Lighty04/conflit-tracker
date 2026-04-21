"""
Identify associations that need board member research.
Outputs a JSON file with the top N associations by budget
that don't currently have board member data.
"""

import json
import os
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Node, Edge, NodeType, EdgeType

def identify_research_targets(output_path: str = None, limit: int = 500, min_budget: float = 50000) -> list:
    """Find top associations by budget without board members"""
    
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(__file__),
            "../../../data/research_targets.json"
        )
    
    db = SessionLocal()
    try:
        # Subquery: associations WITH board members
        from sqlalchemy import select
        has_boards = select(Node.id).join(
            Edge, Edge.target_id == Node.id
        ).where(
            Node.type == NodeType.ASSOCIATION,
            Edge.type == EdgeType.MEMBER_OF
        ).distinct().scalar_subquery()
        
        # Get associations without boards, ordered by budget
        targets = db.query(Node).filter(
            Node.type == NodeType.ASSOCIATION,
            ~Node.id.in_(has_boards),
            Node.total_budget >= min_budget
        ).order_by(Node.total_budget.desc()).limit(limit).all()
        
        result = []
        for t in targets:
            result.append({
                "siret": t.siret,
                "name": t.name,
                "total_budget": t.total_budget,
                "sector": t.sector,
                "node_id": t.node_id,
                "source": t.source,
            })
        
        # Save to file
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump({
                "generated_at": None,  # Will be set
                "count": len(result),
                "total_budget_sum": sum(t["total_budget"] or 0 for t in result),
                "targets": result
            }, f, indent=2, ensure_ascii=False)
        
        print(f"Identified {len(result)} research targets")
        print(f"Total budget: €{sum(t.total_budget or 0 for t in targets):,.0f}")
        
        return result
        
    finally:
        db.close()

if __name__ == "__main__":
    targets = identify_research_targets()
    print(f"\nTop 10 targets:")
    for t in targets[:10]:
        print(f"  {t['name']:60s} €{t['total_budget']:>15,.0f}")
