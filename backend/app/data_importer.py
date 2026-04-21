import json
import os
import glob
from typing import List, Dict
from sqlalchemy.orm import Session
from .models import Node, Edge, NodeType, EdgeType
from .database import SessionLocal, init_db

def import_batch_files(db: Session, data_dir: str = None):
    """Import Paris associations research batch files into graph database"""
    
    if data_dir is None:
        data_dir = os.path.join(
            os.path.dirname(__file__), 
            "../../../paris-assos-website"
        )
    
    batch_files = sorted(glob.glob(os.path.join(data_dir, "batch*_research_results.json")))
    
    # Create Institution node for Paris city (if not exists)
    paris_node = db.query(Node).filter(Node.node_id == "inst_paris_ville").first()
    if not paris_node:
        paris_node = Node(
            node_id="inst_paris_ville",
            type=NodeType.INSTITUTION,
            name="Ville de Paris",
            institution_type="collectivite_territoriale",
            source="Import automatique"
        )
        db.add(paris_node)
        db.flush()
    
    total_assocs = 0
    total_persons = 0
    
    for batch_file in batch_files:
        print(f"Processing {os.path.basename(batch_file)}...")
        
        with open(batch_file, 'r') as f:
            data = json.load(f)
        
        # Handle different batch file structures
        if isinstance(data, list):
            associations = data
        elif isinstance(data, dict):
            associations = data.get("associations", data.get("associations_researched", []))
        else:
            associations = []
        
        for assoc in associations:
            total_assocs += 1
            siret = str(assoc.get("siret", "")).replace(" ", "")
            if not siret:
                continue
            
            assoc_id = f"assoc_{siret}"
            
            # Check if association already exists
            assoc_node = db.query(Node).filter(Node.node_id == assoc_id).first()
            if not assoc_node:
                assoc_node = Node(
                    node_id=assoc_id,
                    type=NodeType.ASSOCIATION,
                    name=assoc["name"],
                    siret=siret,
                    total_budget=assoc.get("total_budget"),
                    source=f"Batch {data.get('batch_number', 'unknown') if isinstance(data, dict) else 'unknown'}"
                )
                db.add(assoc_node)
                db.flush()
            
            # Create SUBSIDIZES edge from Paris to Association
            if assoc.get("total_budget"):
                edge_id = f"sub_{siret}"
                existing = db.query(Edge).filter(Edge.edge_id == edge_id).first()
                if not existing:
                    edge = Edge(
                        edge_id=edge_id,
                        type=EdgeType.SUBSIDIZES,
                        source_id=paris_node.id,
                        target_id=assoc_node.id,
                        amount=assoc["total_budget"],
                        description="Subventions sur 12 ans"
                    )
                    db.add(edge)
            
            # Create Person nodes for board members
            for member in assoc.get("board_members_found", []):
                name = member.get("name", "").strip()
                if not name or len(name) < 3 or any(skip in name.lower() for skip in ["conseil d'administration", "instance de gouvernance", "collège", "multiple establishments"]):
                    continue
                
                person_id = f"pers_{name.lower().replace(' ', '_').replace('-', '_').replace('’', '_')[:80]}"
                
                person = db.query(Node).filter(Node.node_id == person_id).first()
                if not person:
                    total_persons += 1
                    person = Node(
                        node_id=person_id,
                        type=NodeType.PERSON,
                        name=name,
                        role=member.get("role"),
                        source=member.get("source", "Inconnu")
                    )
                    db.add(person)
                    db.flush()
                
                # Create MEMBER_OF edge
                edge_id = f"mem_{person_id}_{assoc_id}"
                existing = db.query(Edge).filter(Edge.edge_id == edge_id).first()
                if not existing:
                    edge = Edge(
                        edge_id=edge_id,
                        type=EdgeType.MEMBER_OF,
                        source_id=person.id,
                        target_id=assoc_node.id,
                        role=member.get("role"),
                        description=member.get("note", "")
                    )
                    db.add(edge)
    
    db.commit()
    print(f"Imported {total_assocs} associations, {total_persons} unique persons")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        import_batch_files(db)
    finally:
        db.close()
