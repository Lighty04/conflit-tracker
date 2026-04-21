import json
import os
from collections import defaultdict
from sqlalchemy.orm import Session
from .models import Node, Edge, NodeType, EdgeType
from .database import SessionLocal, init_db

def import_full_dataset(db: Session, data_path: str = None, batch_dir: str = None, conflicts_path: str = None):
    """Import complete dataset: all associations, batch-enriched boards, known conflicts"""
    
    if data_path is None:
        data_path = os.path.join(os.path.dirname(__file__), "../../../paris-assos-website/data.json")
    if batch_dir is None:
        batch_dir = os.path.join(os.path.dirname(__file__), "../../../paris-assos-website")
    if conflicts_path is None:
        conflicts_path = os.path.join(os.path.dirname(__file__), "../../../paris-assos-website/conflicts_database.json")
    
    # --- PHASE 0: Create Paris institution ---
    paris_node = db.query(Node).filter(Node.node_id == "inst_paris_ville").first()
    if not paris_node:
        paris_node = Node(
            node_id="inst_paris_ville",
            type=NodeType.INSTITUTION,
            name="Ville de Paris",
            institution_type="collectivite_territoriale",
            source="full import"
        )
        db.add(paris_node)
        db.flush()
    
    # --- PHASE 1: Import batch files for enriched board data ---
    import glob
    batch_files = sorted(glob.glob(os.path.join(batch_dir, "batch*_research_results.json")))
    enriched_board = {}
    
    for bf in batch_files:
        with open(bf, 'r') as f:
            data = json.load(f)
        if isinstance(data, list):
            assocs = data
        elif isinstance(data, dict):
            assocs = data.get("associations", data.get("associations_researched", []))
        else:
            continue
        
        for a in assocs:
            siret = str(a.get("siret", "")).replace(" ", "")
            if siret and a.get("board_members_found"):
                enriched_board[siret] = a["board_members_found"]
    
    print(f"Loaded {len(enriched_board)} enriched associations from batch files")
    
    # --- PHASE 2: Import ALL associations from data.json ---
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    print(f"Importing all {len(data)} associations...")
    
    total_assocs = 0
    total_persons = 0
    total_edges = 0
    subvention_agg = defaultdict(lambda: {"amount": 0, "objects": set()})
    
    for assoc in data:
        total_assocs += 1
        siret = str(assoc.get("siret", "")).replace(" ", "")
        if not siret:
            continue
        
        assoc_id = f"assoc_{siret}"
        
        # Skip if already exists (for idempotency)
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
        
        # Board members - prefer enriched batch data, fallback to data.json
        board_members = enriched_board.get(siret, assoc.get("board_members", []))
        
        for member in board_members:
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
                total_edges += 1
        
        if total_assocs % 1000 == 0:
            print(f"  Progress: {total_assocs} associations, {total_persons} persons")
            db.commit()
    
    # Create aggregated subvention edges
    print(f"Creating {len(subvention_agg)} subvention edges...")
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
            total_edges += 1
    
    db.commit()
    
    # --- PHASE 3: Import known conflicts ---
    try:
        with open(conflicts_path, 'r') as f:
            conflicts_data = json.load(f)
        
        conflicts = conflicts_data.get("associations", [])
        print(f"\nImporting {len(conflicts)} known conflicts...")
        
        for conflict in conflicts:
            siret = str(conflict.get("siret", "")).replace(" ", "")
            if not siret:
                continue
            
            assoc_id = f"assoc_{siret}"
            assoc_node = db.query(Node).filter(Node.node_id == assoc_id).first()
            if not assoc_node:
                continue
            
            # Create conflict annotation as an edge attribute or special edge
            # For now, add a CONFLICT_WITH edge to the Paris institution
            edge_id = f"conf_{siret}"
            if not db.query(Edge).filter(Edge.edge_id == edge_id).first():
                db.add(Edge(
                    edge_id=edge_id,
                    type=EdgeType.CONFLICT_WITH,
                    source_id=paris_node.id,
                    target_id=assoc_node.id,
                    description=conflict.get("details", ""),
                    amount=conflict.get("budget")
                ))
    
        db.commit()
        print(f"Imported {len(conflicts)} conflict annotations")
    except FileNotFoundError:
        print("No conflicts file found, skipping")
    
    # Final stats
    total_nodes = db.query(Node).count()
    total_edges = db.query(Edge).count()
    persons = db.query(Node).filter(Node.type == NodeType.PERSON).count()
    assocs = db.query(Node).filter(Node.type == NodeType.ASSOCIATION).count()
    
    print(f"\nDone: {total_nodes} total nodes ({assocs} assocs, {persons} persons), {total_edges} edges")

def normalize_name(name):
    return name.lower().replace(' ', '_').replace('-', '_').replace('’', '_').replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('à', 'a').replace('ô', 'o').replace('ç', 'c')[:80]

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        import_full_dataset(db)
    finally:
        db.close()
