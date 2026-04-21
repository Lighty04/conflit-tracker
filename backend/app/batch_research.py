"""
Automated batch research script.
Fetches board members for top associations using Pappers.fr API.

Usage:
    # Research top 100 associations without board members
    python -m app.batch_research --limit 100 --output data/batch_research_results.json
    
    # Import results
    python -m app.import_research_results data/batch_research_results.json
"""

import json
import os
import time
import argparse
from datetime import datetime
from typing import List, Dict
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Node, Edge, NodeType, EdgeType

def get_research_targets(db: Session, limit: int = 100, min_budget: float = 50000) -> List[Node]:
    """Get top associations by budget that don't have board members"""
    from sqlalchemy import select
    
    has_boards = select(Node.id).join(
        Edge, Edge.target_id == Node.id
    ).where(
        Node.type == NodeType.ASSOCIATION,
        Edge.type == EdgeType.MEMBER_OF
    ).distinct().scalar_subquery()
    
    return db.query(Node).filter(
        Node.type == NodeType.ASSOCIATION,
        ~Node.id.in_(has_boards),
        Node.total_budget >= min_budget
    ).order_by(Node.total_budget.desc()).limit(limit).all()

def fetch_pappers_board(siret: str, api_key: str) -> List[Dict]:
    """Fetch board members from Pappers.fr API"""
    import requests
    
    url = "https://api.pappers.fr/v2/entreprise"
    params = {
        "siret": siret.replace(" ", ""),
        "api_token": api_key
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            members = []
            
            for d in data.get("dirigeants", []):
                members.append({
                    "name": f"{d.get('nom', '')} {d.get('prenom', '')}".strip(),
                    "role": d.get("qualite", "Dirigeant"),
                    "source": "Pappers.fr"
                })
            
            return members
        elif resp.status_code == 429:
            print(f"  Rate limited on {siret}, waiting 2s...")
            time.sleep(2)
            return fetch_pappers_board(siret, api_key)
        else:
            print(f"  Pappers error {resp.status_code} for {siret}")
            return []
    except Exception as e:
        print(f"  Exception fetching {siret}: {e}")
        return []

def run_batch_research(limit: int = 100, delay: float = 1.0, output_path: str = None, api_key: str = None):
    """Run automated batch research"""
    
    if api_key is None:
        api_key = os.environ.get("PAPPERS_API_KEY")
    
    if not api_key:
        print("ERROR: No PAPPERS_API_KEY set. Set env var or pass --api-key")
        return
    
    if output_path is None:
        output_path = f"data/batch_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    db = SessionLocal()
    try:
        targets = get_research_targets(db, limit=limit)
        print(f"Found {len(targets)} research targets")
        
        results = {
            "batch_number": int(datetime.now().timestamp()),
            "generated_at": datetime.now().isoformat(),
            "associations_researched": []
        }
        
        for i, target in enumerate(targets, 1):
            print(f"[{i}/{len(targets)}] Researching {target.name} (€{target.total_budget or 0:,.0f})...")
            
            board_members = fetch_pappers_board(target.siret, api_key)
            
            assoc_result = {
                "siret": target.siret,
                "name": target.name,
                "total_budget": target.total_budget,
                "board_members_found": board_members,
                "subventions": []  # Already in database
            }
            
            results["associations_researched"].append(assoc_result)
            
            if board_members:
                print(f"  Found {len(board_members)} board members")
            else:
                print(f"  No board members found")
            
            time.sleep(delay)
        
        # Save results
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to {output_path}")
        print(f"Total associations researched: {len(results['associations_researched'])}")
        
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch research board members")
    parser.add_argument("--limit", type=int, default=100, help="Number of associations to research")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between API calls (seconds)")
    parser.add_argument("--output", type=str, help="Output JSON file path")
    parser.add_argument("--api-key", type=str, help="Pappers.fr API key")
    
    args = parser.parse_args()
    run_batch_research(limit=args.limit, delay=args.delay, output_path=args.output, api_key=args.api_key)
