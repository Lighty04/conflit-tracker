import json
import os
from typing import List, Dict
from sqlalchemy.orm import Session
from .models import Node, Edge, NodeType, EdgeType
from .database import SessionLocal, init_db

def import_paris_data(db: Session, data_path: str = None):
    """Import Paris associations research data into graph database"""
    
    # Default to paris-assos-website conflict_research.json
    if data_path is None:
        data_path = os.path.join(
            os.path.dirname(__file__), 
            "../../../paris-assos-website/conflict_research.json"
        )
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    associations = data.get("associations_researched", [])
    
    # Create Institution node for Paris city
    paris_node = Node(
        node_id="inst_paris_ville",
        type=NodeType.INSTITUTION,
        name="Ville de Paris",
        institution_type="collectivite_territoriale",
        source="Import automatique"
    )
    db.add(paris_node)
    
    for assoc in associations:
        assoc_id = f"assoc_{assoc['siret']}"
        
        # Create Association node
        assoc_node = Node(
            node_id=assoc_id,
            type=NodeType.ASSOCIATION,
            name=assoc["name"],
            siret=assoc.get("siret"),
            total_budget=assoc.get("total_budget"),
            source=f"Batch {data.get('batch_number', 'unknown')}"
        )
        db.add(assoc_node)
        
        # Create SUBSIDIZES edge from Paris to Association
        if assoc.get("total_budget"):
            edge = Edge(
                edge_id=f"sub_{assoc['siret']}",
                type=EdgeType.SUBSIDIZES,
                source=paris_node,
                target=assoc_node,
                amount=assoc["total_budget"],
                description=f"Subventions sur 12 ans"
            )
            db.add(edge)
        
        # Create Person nodes for board members
        for member in assoc.get("board_members_found", []):
            if not member.get("name") or member["name"] in ["Conseil d'administration", "Conseil d'administration paritaire"]:
                continue
            
            person_id = f"pers_{member['name'].lower().replace(' ', '_').replace('-', '_')}"
            
            # Check if person already exists
            person = db.query(Node).filter(Node.node_id == person_id).first()
            if not person:
                person = Node(
                    node_id=person_id,
                    type=NodeType.PERSON,
                    name=member["name"],
                    role=member.get("role"),
                    source=member.get("source", "Inconnu")
                )
                db.add(person)
            
            # Create MEMBER_OF edge
            edge = Edge(
                edge_id=f"mem_{person_id}_{assoc_id}",
                type=EdgeType.MEMBER_OF,
                source=person,
                target=assoc_node,
                role=member.get("role"),
                description=member.get("note", "")
            )
            db.add(edge)
    
    db.commit()
    print(f"Imported {len(associations)} associations")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        import_paris_data(db)
    finally:
        db.close()
