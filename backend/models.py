from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database import Base
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, index=True)
    title = Column(String, nullable=False)
    severity = Column(String, default="P2") # P1, P2, P3, P4
    status = Column(String, default="Investigating") # Investigating, Identified, Resolved
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), index=True, nullable=False)
    author = Column(String, default="human")
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)