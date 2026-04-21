import json
import os
from sqlalchemy.orm import Session
from .models import Node, Edge, NodeType, EdgeType
from .database import SessionLocal, init_db

def import_full_dataset(db: Session, data_path: str = None, limit: int = 500):
    """Import full Paris associations dataset (top N by budget)"""
    
    if data_path is None:
        data_path = os.path.join(
            os.path.dirname(__file__), 
            "../../../paris-assos-website/data.json"
        )
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Sort by totalAmount descending, take top N
    data.sort(key=lambda x: x.get('totalAmount', 0) or 0, reverse=True)
    associations = data[:limit]
    
    print(f"Importing top {len(associations)} associations from {len(data)} total")
    
    # Create Institution node for Paris city
    paris_node = db.query(Node).filter(Node.node_id == "inst_paris_ville").first()
    if not paris_node:
        paris_node = Node(
            node_id="inst_paris_ville",
            type=NodeType.INSTITUTION,
            name="Ville de Paris",
            institution_type="collectivite_territoriale",
            source="data.json import"
        )
        db.add(paris_node)
        db.flush()
    
    total_assocs = 0
    total_persons = 0
    total_edges = 0
    
    for assoc in associations:
        siret = str(assoc.get("siret", "")).replace(" ", "")
        if not siret:
            continue
        
        total_assocs += 1
        assoc_id = f"assoc_{siret}"
        
        # Skip if already exists
        assoc_node = db.query(Node).filter(Node.node_id == assoc_id).first()
        if assoc_node:
            continue
        
        # Create Association node
        assoc_node = Node(
            node_id=assoc_id,
            type=NodeType.ASSOCIATION,
            name=assoc["name"],
            siret=siret,
            total_budget=assoc.get("totalAmount"),
            sector=", ".join(assoc.get("sectors", [])) if assoc.get("sectors") else None,
            source=assoc.get("board_data_source", "data.json")
        )
        db.add(assoc_node)
        db.flush()
        
        # Create SUBSIDIZES edges for each subvention
        for i, sub in enumerate(assoc.get("subventions", [])):
            if sub.get("amount") and sub["amount"] > 0:
                edge_id = f"sub_{siret}_{sub.get('year', 'unknown')}_{i}"
                existing = db.query(Edge).filter(Edge.edge_id == edge_id).first()
                if not existing:
                    edge = Edge(
                        edge_id=edge_id,
                        type=EdgeType.SUBSIDIZES,
                        source_id=paris_node.id,
                        target_id=assoc_node.id,
                        amount=sub["amount"],
                        year=int(sub["year"]) if str(sub.get("year", "")).isdigit() else None,
                        description=sub.get("object", "")
                    )
                    db.add(edge)
                    total_edges += 1
        
        # Create Person nodes for board members
        for member in assoc.get("board_members", []):
            name = member.get("name", "").strip()
            if not name or len(name) < 3:
                continue
            # Skip generic entries
            if any(skip in name.lower() for skip in [
                "conseil d'administration", "instance de gouvernance",
                "collège", "multiple establishments", "representatives",
                "non disponible", "information non"
            ]):
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
                total_edges += 1
        
        if total_assocs % 50 == 0:
            print(f"  Progress: {total_assocs} associations, {total_persons} persons, {total_edges} edges")
    
    db.commit()
    print(f"Done: {total_assocs} associations, {total_persons} persons, {total_edges} edges")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        import_full_dataset(db, limit=200)
    finally:
        db.close()
