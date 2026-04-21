"""
Import batch research results into the graph database.

Expected input format (JSON):
{
    "batch_number": 12,
    "associations_researched": [
        {
            "siret": "12345678900010",
            "name": "Association Name",
            "board_members_found": [
                {
                    "name": "Jean Dupont",
                    "role": "Président",
                    "source": "Pappers.fr / Official site"
                }
            ],
            "subventions": [...]
        }
    ]
}

Usage:
    python -m app.import_research_results path/to/batch12_results.json
"""

import json
import sys
import os
from sqlalchemy.orm import Session
from .models import Node, Edge, NodeType, EdgeType
from .database import SessionLocal, init_db

def normalize_name(name):
    return name.lower().replace(' ', '_').replace('-', '_').replace('’', '_').replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ô', 'o').replace('ç', 'c')[:80]

def import_research_results(db: Session, data_path: str):
    """Import a batch research results file"""
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    batch_num = data.get("batch_number", "unknown")
    associations = data.get("associations_researched", data.get("associations", []))
    
    print(f"Importing batch {batch_num}: {len(associations)} associations")
    
    # Get or create Paris institution
    paris_node = db.query(Node).filter(Node.node_id == "inst_paris_ville").first()
    if not paris_node:
        paris_node = Node(
            node_id="inst_paris_ville",
            type=NodeType.INSTITUTION,
            name="Ville de Paris",
            institution_type="collectivite_territoriale",
            source="batch import"
        )
        db.add(paris_node)
        db.flush()
    
    persons_added = 0
    edges_added = 0
    
    for assoc in associations:
        siret = str(assoc.get("siret", "")).replace(" ", "")
        if not siret:
            continue
        
        assoc_id = f"assoc_{siret}"
        
        # Find or create association node
        assoc_node = db.query(Node).filter(Node.node_id == assoc_id).first()
        if not assoc_node:
            print(f"  Warning: Association {siret} not found in database, skipping")
            continue
        
        # Import board members
        for member in assoc.get("board_members_found", []):
            name = member.get("name", "").strip()
            if not name or len(name) < 3:
                continue
            
            # Skip generic entries
            if any(skip in name.lower() for skip in [
                "conseil d'administration", "instance de gouvernance",
                "collège", "multiple establishments", "representatives",
                "non disponible", "information non", "direction",
                "directeur général", "fédération entreprises"
            ]):
                continue
            
            person_id = f"pers_{normalize_name(name)}"
            
            person = db.query(Node).filter(Node.node_id == person_id).first()
            if not person:
                persons_added += 1
                person = Node(
                    node_id=person_id,
                    type=NodeType.PERSON,
                    name=name,
                    role=member.get("role"),
                    source=member.get("source", f"Batch {batch_num}")
                )
                db.add(person)
                db.flush()
            
            # Create MEMBER_OF edge
            edge_id = f"mem_{person_id}_{assoc_id}"
            existing = db.query(Edge).filter(Edge.edge_id == edge_id).first()
            if not existing:
                db.add(Edge(
                    edge_id=edge_id,
                    type=EdgeType.MEMBER_OF,
                    source_id=person.id,
                    target_id=assoc_node.id,
                    role=member.get("role"),
                    description=member.get("note", "")
                ))
                edges_added += 1
        
        # Import subventions if present
        for sub in assoc.get("subventions", []):
            if sub.get("amount") and sub["amount"] > 0:
                year = str(sub.get("year", "unknown"))
                edge_id = f"sub_{siret}_{year}"
                existing = db.query(Edge).filter(Edge.edge_id == edge_id).first()
                if not existing:
                    db.add(Edge(
                        edge_id=edge_id,
                        type=EdgeType.SUBSIDIZES,
                        source_id=paris_node.id,
                        target_id=assoc_node.id,
                        amount=sub["amount"],
                        year=int(year) if year.isdigit() else None,
                        description=sub.get("object", "")
                    ))
    
    db.commit()
    print(f"Done: {persons_added} persons added, {edges_added} edges added")
    
    # Recalculate conflict metrics
    from .conflict_service import ConflictService
    service = ConflictService(db)
    count = service.calculate_person_metrics()
    print(f"Recalculated metrics for {count} persons")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        if len(sys.argv) > 1:
            import_research_results(db, sys.argv[1])
        else:
            print("Usage: python -m app.import_research_results path/to/results.json")
    finally:
        db.close()
