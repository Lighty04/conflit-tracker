from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from pathlib import Path
import os

from .database import get_db, init_db
from .graph_service import GraphService
from .conflict_service import ConflictService
from .report_service import ReportService
from .models import Node, Edge

app = FastAPI(title="ConflitTracker API")

# Mount static files
static_path = Path(__file__).parent.parent.parent / "frontend" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.on_event("startup")
async def startup():
    init_db()
    # Metrics recalculation is done via POST /api/admin/recalculate
    # Run it once after import, not on every startup

@app.get("/", response_class=HTMLResponse)
async def read_root():
    template_path = Path(__file__).parent.parent.parent / "frontend" / "templates" / "index.html"
    if template_path.exists():
        return template_path.read_text()
    return "<h1>ConflitTracker</h1><p>Frontend not built yet.</p>"

@app.get("/embed", response_class=HTMLResponse)
async def read_embed():
    template_path = Path(__file__).parent.parent.parent / "frontend" / "templates" / "embed.html"
    if template_path.exists():
        return template_path.read_text()
    return "<h1>ConflitMap Embed</h1><p>Template not found.</p>"

@app.get("/api/graph/neighbors")
async def get_neighbors(node_id: str, hops: int = 1, db: Session = Depends(get_db)):
    """Get n-hop neighborhood for visualization"""
    service = GraphService()
    service.load_from_db(db)
    return service.get_neighbors(node_id, hops)

@app.get("/api/graph/search")
async def search_nodes(q: str, limit: int = 20, db: Session = Depends(get_db)):
    """Search nodes by name"""
    service = GraphService()
    service.load_from_db(db)
    return service.search_nodes(q, limit)

@app.get("/api/graph/path")
async def find_path(source: str, target: str, db: Session = Depends(get_db)):
    """Find shortest path between two nodes"""
    service = GraphService()
    service.load_from_db(db)
    path = service.find_path(source, target)
    if path is None:
        raise HTTPException(status_code=404, detail="No path found")
    return {"path": path}

@app.get("/api/graph/centrality")
async def get_centrality(node_id: str, db: Session = Depends(get_db)):
    """Get centrality metrics for a node"""
    service = GraphService()
    service.load_from_db(db)
    return service.get_centrality(node_id)

@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get database statistics"""
    node_count = db.query(Node).count()
    edge_count = db.query(Edge).count()
    
    person_count = db.query(Node).filter(Node.type == "person").count()
    assoc_count = db.query(Node).filter(Node.type == "association").count()
    inst_count = db.query(Node).filter(Node.type == "institution").count()
    
    return {
        "total_nodes": node_count,
        "total_edges": edge_count,
        "persons": person_count,
        "associations": assoc_count,
        "institutions": inst_count
    }

@app.post("/api/admin/recalculate")
async def recalculate_metrics(db: Session = Depends(get_db)):
    """Recalculate all conflict metrics"""
    service = ConflictService(db)
    count = service.calculate_person_metrics()
    return {"recalculated": count}

@app.get("/api/leaderboard")
async def get_leaderboard(metric: str = "conflict_score", limit: int = 50, db: Session = Depends(get_db)):
    """Get top persons by conflict metric"""
    service = ConflictService(db)
    return service.get_leaderboard(metric, limit)

@app.get("/api/person/{person_id}")
async def get_person_aggregate(person_id: str, db: Session = Depends(get_db)):
    """Full breakdown of a person's network"""
    service = ConflictService(db)
    result = service.get_person_aggregate(person_id)
    if not result:
        raise HTTPException(status_code=404, detail="Person not found")
    return result

@app.get("/api/alerts")
async def get_conflict_alerts(
    threshold_subv: float = 500000,
    threshold_boards: int = 3,
    db: Session = Depends(get_db)
):
    """Auto-flag high-risk persons"""
    service = ConflictService(db)
    return service.get_conflict_alerts(threshold_subv, threshold_boards)

@app.get("/api/export/graph")
async def export_graph(node_id: str, hops: int = 2, format: str = "json", db: Session = Depends(get_db)):
    """Export graph neighborhood as JSON or for later SVG/PNG"""
    service = GraphService()
    service.load_from_db(db)
    data = service.get_neighbors(node_id, hops)
    return data

@app.get("/api/report/{person_id}")
async def get_person_report(person_id: str, db: Session = Depends(get_db)):
    """Generate complete conflict report for a person (PDF-ready data)"""
    service = ReportService(db)
    report = service.generate_person_report(person_id)
    if not report:
        raise HTTPException(status_code=404, detail="Person not found")
    from datetime import datetime
    report["generated_at"] = datetime.utcnow().isoformat()
    return report

@app.get("/api/embed/person/{person_id}")
async def embed_person(person_id: str, hops: int = 1, db: Session = Depends(get_db)):
    """Get embeddable graph data for iframe embedding"""
    service = GraphService()
    service.load_from_db(db)
    person = db.query(Node).filter(Node.node_id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    network = service.get_neighbors(person_id, hops)
    return {
        "person_id": person_id,
        "person_name": person.name,
        "conflict_score": person.conflict_score or 0,
        "is_membre_de_droit": bool(person.is_membre_de_droit),
        "total_subventions_controlled": person.total_subventions_controlled or 0,
        "board_count": person.board_count or 0,
        "network": network,
        "embeddable": True,
        "watermark": "ConflitMap.fr"
    }
