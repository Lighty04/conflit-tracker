from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import enum

Base = declarative_base()

class NodeType(str, enum.Enum):
    PERSON = "person"
    ASSOCIATION = "association"
    INSTITUTION = "institution"

class EdgeType(str, enum.Enum):
    MEMBER_OF = "member_of"
    SUBSIDIZES = "subsidizes"
    CONFLICT_WITH = "conflict_with"

class Node(Base):
    __tablename__ = "nodes"
    
    id = Column(Integer, primary_key=True)
    node_id = Column(String, unique=True, nullable=False, index=True)
    type = Column(Enum(NodeType), nullable=False)
    name = Column(String, nullable=False, index=True)
    
    # Type-specific fields (stored as JSON-like or separate tables)
    siret = Column(String, nullable=True)  # for associations
    sector = Column(String, nullable=True)  # for associations
    total_budget = Column(Float, nullable=True)  # for associations
    role = Column(String, nullable=True)  # for persons
    institution_type = Column(String, nullable=True)  # for institutions
    
    # Metadata
    source = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    outgoing_edges = relationship("Edge", foreign_keys="Edge.source_id", back_populates="source")
    incoming_edges = relationship("Edge", foreign_keys="Edge.target_id", back_populates="target")

class Edge(Base):
    __tablename__ = "edges"
    
    id = Column(Integer, primary_key=True)
    edge_id = Column(String, unique=True, nullable=False, index=True)
    type = Column(Enum(EdgeType), nullable=False)
    
    source_id = Column(Integer, ForeignKey("nodes.id"), nullable=False, index=True)
    target_id = Column(Integer, ForeignKey("nodes.id"), nullable=False, index=True)
    
    # Edge attributes
    role = Column(String, nullable=True)  # for MEMBER_OF
    amount = Column(Float, nullable=True)  # for SUBSIDIZES
    year = Column(Integer, nullable=True)  # for SUBSIDIZES
    severity = Column(String, nullable=True)  # for CONFLICT_WITH (HIGH/MEDIUM/LOW)
    description = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    source = relationship("Node", foreign_keys=[source_id], back_populates="outgoing_edges")
    target = relationship("Node", foreign_keys=[target_id], back_populates="incoming_edges")
