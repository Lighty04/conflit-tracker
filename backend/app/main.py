from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pathlib import Path
import os

from .database import get_db, init_db
from .graph_service import GraphService
from .models import Node, Edge

app = FastAPI(title="ConflitTracker API")

# Mount static files
static_path = Path(__file__).parent.parent.parent / "frontend" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
async def read_root():
    template_path = Path(__file__).parent.parent.parent / "frontend" / "templates" / "index.html"
    if template_path.exists():
        return template_path.read_text()
    return "<h1>ConflitTracker</h1><p>Frontend not built yet.</p>"

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
