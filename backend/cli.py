#!/usr/bin/env python3
"""
CLI for running batch research on associations.

Usage:
    # Identify top 500 research targets
    python cli.py identify --limit 500 --output data/targets.json
    
    # Run batch research (requires PAPPERS_API_KEY env var)
    python cli.py research --limit 100 --delay 1.0
    
    # Import research results
    python cli.py import data/batch_research_*.json
    
    # Recalculate all conflict scores
    python cli.py recalculate
"""

import sys
import os
import argparse
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import init_db, SessionLocal
from app.identify_research_targets import identify_research_targets
from app.batch_research import run_batch_research
from app.import_research_results import import_research_results
from app.conflict_service import ConflictService

def main():
    parser = argparse.ArgumentParser(description="ConflitMap batch research CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # identify
    identify_parser = subparsers.add_parser("identify", help="Identify research targets")
    identify_parser.add_argument("--limit", type=int, default=500)
    identify_parser.add_argument("--min-budget", type=float, default=50000)
    identify_parser.add_argument("--output", type=str, default="data/research_targets.json")
    
    # research
    research_parser = subparsers.add_parser("research", help="Run batch research")
    research_parser.add_argument("--limit", type=int, default=100)
    research_parser.add_argument("--delay", type=float, default=1.0)
    research_parser.add_argument("--output", type=str)
    research_parser.add_argument("--api-key", type=str)
    
    # import
    import_parser = subparsers.add_parser("import", help="Import research results")
    import_parser.add_argument("files", nargs="+", help="JSON files to import")
    
    # recalculate
    recalc_parser = subparsers.add_parser("recalculate", help="Recalculate conflict scores")
    
    args = parser.parse_args()
    
    if args.command == "identify":
        init_db()
        identify_research_targets(
            output_path=args.output,
            limit=args.limit,
            min_budget=args.min_budget
        )
    
    elif args.command == "research":
        run_batch_research(
            limit=args.limit,
            delay=args.delay,
            output_path=args.output,
            api_key=args.api_key
        )
    
    elif args.command == "import":
        init_db()
        db = SessionLocal()
        try:
            for f in args.files:
                print(f"\nImporting {f}...")
                import_research_results(db, f)
        finally:
            db.close()
    
    elif args.command == "recalculate":
        init_db()
        db = SessionLocal()
        try:
            service = ConflictService(db)
            count = service.calculate_person_metrics()
            print(f"Recalculated metrics for {count} persons")
        finally:
            db.close()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
