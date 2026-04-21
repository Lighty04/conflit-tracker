import json
import os
import glob
from collections import defaultdict
from sqlalchemy.orm import Session
from .models import Node, Edge, NodeType, EdgeType
from .database import SessionLocal, init_db

def import_combined(db: Session, limit: int = 200):
    """Import batch files first (enriched board data), then fill from data.json"""
    
    # --- PHASE 1: Import batch research files (better board member data) ---
    batch_dir = os.path.join(os.path.dirname(__file__), "../../../paris-assos-website")
    batch_files = sorted(glob.glob(os.path.join(batch_dir, "batch*_research_results.json")))
    
    batch_sirets = set()
    batch_persons = set()
    
    # Create Paris institution
    paris_node = db.query(Node).filter(Node.node_id == "inst_paris_ville").first()
    if not paris_node:
        paris_node = Node(
            node_id="inst_paris_ville",
            type=NodeType.INSTITUTION,
            name="Ville de Paris",
            institution_type="collectivite_territoriale",
            source="combined import"
        )
        db.add(paris_node)
        db.flush()
    
    print("=== PHASE 1: Batch files (enriched board data) ===")
    
    for bf in batch_files:
        with open(bf, 'r') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            assocs = data
        elif isinstance(data, dict):
            assocs = data.get("associations", data.get("associations_researched", []))
        else:
            continue
        
        for assoc in assocs:
            siret = str(assoc.get("siret", "")).replace(" ", "")
            if not siret:
                continue
            
            batch_sirets.add(siret)
            assoc_id = f"assoc_{siret}"
            
            # Skip if already exists
            assoc_node = db.query(Node).filter(Node.node_id == assoc_id).first()
            if assoc_node:
                continue
            
            assoc_node = Node(
                node_id=assoc_id,
                type=NodeType.ASSOCIATION,
                name=assoc["name"],
                siret=siret,
                total_budget=assoc.get("total_budget") or assoc.get("budget"),
                source=f"Batch {data.get('batch_number', 'unknown') if isinstance(data, dict) else 'unknown'}"
            )
            db.add(assoc_node)
            db.flush()
            
            # Board members from batch files
            for member in assoc.get("board_members_found", []):
                name = member.get("name", "").strip()
                if not name or len(name) < 3:
                    continue
                if any(skip in name.lower() for skip in [
                    "conseil d'administration", "instance de gouvernance",
                    "collège", "multiple establishments", "representatives",
                    "non disponible", "information non", "direction",
                    "directeur général", "fédération entreprises"
                ]):
                    continue
                
                person_id = f"pers_{normalize_name(name)}"
                batch_persons.add(person_id)
                
                person = db.query(Node).filter(Node.node_id == person_id).first()
                if not person:
                    person = Node(
                        node_id=person_id,
                        type=NodeType.PERSON,
                        name=name,
                        role=member.get("role"),
                        source=member.get("source", "Inconnu")
                    )
                    db.add(person)
                    db.flush()
                
                edge_id = f"mem_{person_id}_{assoc_id}"
                if not db.query(Edge).filter(Edge.edge_id == edge_id).first():
                    db.add(Edge(
                        edge_id=edge_id,
                        type=EdgeType.MEMBER_OF,
                        source_id=person.id,
                        target_id=assoc_node.id,
                        role=member.get("role"),
                        description=member.get("note", "")
                    ))
            
            # Subventions from batch files
            for sub in assoc.get("subventions", []):
                if sub.get("amount") and sub["amount"] > 0:
                    edge_id = f"sub_{siret}_{sub.get('year', 'unk')}"
                    if not db.query(Edge).filter(Edge.edge_id == edge_id).first():
                        db.add(Edge(
                            edge_id=edge_id,
                            type=EdgeType.SUBSIDIZES,
                            source_id=paris_node.id,
                            target_id=assoc_node.id,
                            amount=sub["amount"],
                            year=int(sub["year"]) if str(sub.get("year", "")).isdigit() else None,
                            description=sub.get("object", "")
                        ))
    
    db.commit()
    print(f"Batch phase: {len(batch_sirets)} associations, {len(batch_persons)} persons")
    
    # --- PHASE 2: Import top associations from data.json, skip batch overlaps ---
    data_path = os.path.join(batch_dir, "data.json")
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    data.sort(key=lambda x: x.get('totalAmount', 0) or 0, reverse=True)
    
    # Take top N that aren't already imported, cap total at limit
    remaining = [a for a in data if str(a.get("siret", "")).replace(" ", "") not in batch_sirets]
    already_count = len(batch_sirets)
    need = max(0, limit - already_count)
    new_assocs = remaining[:need]
    
    print(f"\n=== PHASE 2: data.json top {len(new_assocs)} (non-overlapping, cap {limit}) ===")
    
    subvention_agg = defaultdict(lambda: {"amount": 0, "objects": set()})
    
    for assoc in new_assocs:
        siret = str(assoc.get("siret", "")).replace(" ", "")
        if not siret:
            continue
        
        assoc_id = f"assoc_{siret}"
        
        assoc_node = db.query(Node).filter(Node.node_id == assoc_id).first()
        if assoc_node:
            continue
        
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
        
        # Aggregate subventions
        for sub in assoc.get("subventions", []):
            if sub.get("amount") and sub["amount"] > 0:
                year = str(sub.get("year", "unknown"))
                key = (siret, year)
                subvention_agg[key]["amount"] += sub["amount"]
                if sub.get("object"):
                    subvention_agg[key]["objects"].add(sub["object"])
        
        # Board members from data.json (usually sparse)
        for member in assoc.get("board_members", []):
            name = member.get("name", "").strip()
            if not name or len(name) < 3:
                continue
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
                person = Node(
                    node_id=person_id,
                    type=NodeType.PERSON,
                    name=name,
                    role=member.get("role"),
                    source=member.get("source", "Inconnu")
                )
                db.add(person)
                db.flush()
            
            edge_id = f"mem_{person_id}_{assoc_id}"
            if not db.query(Edge).filter(Edge.edge_id == edge_id).first():
                db.add(Edge(
                    edge_id=edge_id,
                    type=EdgeType.MEMBER_OF,
                    source_id=person.id,
                    target_id=assoc_node.id,
                    role=member.get("role"),
                    description=member.get("note", "")
                ))
    
    # Create aggregated subvention edges
    for (siret, year), agg in subvention_agg.items():
        assoc_id = f"assoc_{siret}"
        assoc_node = db.query(Node).filter(Node.node_id == assoc_id).first()
        if not assoc_node:
            continue
        
        edge_id = f"sub_{siret}_{year}"
        if not db.query(Edge).filter(Edge.edge_id == edge_id).first():
            db.add(Edge(
                edge_id=edge_id,
                type=EdgeType.SUBSIDIZES,
                source_id=paris_node.id,
                target_id=assoc_node.id,
                amount=agg["amount"],
                year=int(year) if year.isdigit() else None,
                description="; ".join(list(agg["objects"])[:3])
            ))
    
    db.commit()
    
    # Stats
    total_nodes = db.query(Node).count()
    total_edges = db.query(Edge).count()
    persons = db.query(Node).filter(Node.type == NodeType.PERSON).count()
    assocs = db.query(Node).filter(Node.type == NodeType.ASSOCIATION).count()
    
    print(f"\nDone: {total_nodes} total nodes ({assocs} assocs, {persons} persons), {total_edges} edges")

def normalize_name(name):
    return name.lower().replace(' ', '_').replace('-', '_').replace('’', '_').replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a')[:80]

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        import_combined(db, limit=200)
    finally:
        db.close()
