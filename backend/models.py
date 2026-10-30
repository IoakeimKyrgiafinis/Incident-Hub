from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database import Base

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