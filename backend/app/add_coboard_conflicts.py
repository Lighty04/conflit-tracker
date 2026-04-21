from sqlalchemy.orm import joinedload
from .models import Node, Edge, NodeType, EdgeType
from .database import SessionLocal, init_db

def add_coboard_conflicts():
    """Add CONFLICT_WITH edges between people who sit on the same boards"""
    db = SessionLocal()
    try:
        print("Creating CONFLICT_WITH edges between co-board members...")
        
        associations_with_boards = db.query(Node).options(
            joinedload(Node.incoming_edges).joinedload(Edge.source)
        ).filter(Node.type == NodeType.ASSOCIATION).all()
        
        conflict_edges_created = 0
        
        for assoc in associations_with_boards:
            board_members = []
            for edge in assoc.incoming_edges:
                if edge.type == EdgeType.MEMBER_OF and edge.source and edge.source.type == NodeType.PERSON:
                    board_members.append(edge.source)
            
            if len(board_members) < 2:
                continue
            
            for i in range(len(board_members)):
                for j in range(i + 1, len(board_members)):
                    p1 = board_members[i]
                    p2 = board_members[j]
                    
                    edge_id = f"conflict_{assoc.siret}_{min(p1.node_id, p2.node_id)}_{max(p1.node_id, p2.node_id)}"
                    
                    existing = db.query(Edge).filter(Edge.edge_id == edge_id).first()
                    if not existing:
                        db.add(Edge(
                            edge_id=edge_id,
                            type=EdgeType.CONFLICT_WITH,
                            source_id=p1.id,
                            target_id=p2.id,
                            description=f"Co-membres du CA de {assoc.name}",
                            role="co_member"
                        ))
                        conflict_edges_created += 1
        
        db.commit()
        print(f"Created {conflict_edges_created} CONFLICT_WITH edges")
        
        # Stats
        total_conflicts = db.query(Edge).filter(Edge.type == EdgeType.CONFLICT_WITH).count()
        print(f"Total CONFLICT_WITH edges: {total_conflicts}")
        
    finally:
        db.close()

if __name__ == "__main__":
    add_coboard_conflicts()
