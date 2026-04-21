# ConflitTracker

Interactive network visualization platform mapping conflicts of interest in French public institutions.

## MVP Scope
- [x] Import existing Paris associations dataset
- [ ] Graph rendering with D3.js
- [ ] Search by name (person, association, institution)
- [ ] 2-hop neighbor exploration
- [ ] Export as PNG/SVG

## Tech Stack
- **Backend:** FastAPI + Python
- **Database:** PostgreSQL (pg_graph for graph queries)
- **Graph Engine:** NetworkX + D3.js frontend
- **Frontend:** HTML + HTMX + D3.js
- **Deployment:** Docker + VPS

## Project Structure
```
conflit-tracker/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI entry
│   │   ├── models.py            # SQLAlchemy + graph models
│   │   ├── schemas.py           # Pydantic schemas
│   │   ├── database.py          # DB connection + init
│   │   ├── graph_service.py     # NetworkX graph operations
│   │   └── data_importer.py     # Import from paris dataset
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   │       └── graph.js         # D3.js visualization
│   └── templates/
│       └── index.html           # HTMX + D3.js app
├── data/
│   └── paris_import.json        # Normalized import data
├── docker-compose.yml
└── README.md
```

## Data Model (Graph Schema)

### Nodes (3 types)
1. **Person** - individuals (elected officials, board members, directors)
   - id, name, role, source
2. **Association** - organizations receiving public funds
   - id, name, siret, total_budget, sector
3. **Institution** - public bodies (city, ministry, etc.)
   - id, name, type

### Edges (3 types)
1. **MEMBER_OF** (Person → Association)
   - role, appointment_date, source
2. **SUBSIDIZES** (Institution → Association)
   - amount, year, type
3. **CONFLICT_WITH** (Person → Person)
   - type, severity, description

## Quick Start
```bash
cd backend
pip install -r requirements.txt
python -m app.data_importer  # Import Paris data
uvicorn app.main:app --reload
```

## License
MIT
