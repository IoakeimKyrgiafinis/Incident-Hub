from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging
from telemetry import setup_telemetry, incidents_created, incidents_resolved

import os
import models
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Incident & Post-Mortem Hub API", version="1.0.0")
setup_telemetry(app, engine)
logger = logging.getLogger("incident-hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class IncidentCreate(BaseModel):
    service_name: str
    title: str
    severity: Optional[str] = "P2"
    description: Optional[str] = ""

class IncidentResponse(BaseModel):
    id: int
    service_name: str
    title: str
    severity: str
    status: str
    description: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/incidents", response_model=List[IncidentResponse])
def get_incidents(db: Session = Depends(get_db)):
    return db.query(models.Incident).order_by(models.Incident.created_at.desc()).all()

@app.post("/incidents", response_model=IncidentResponse)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db)):
    new_incident = models.Incident(
        service_name=payload.service_name,
        title=payload.title,
        severity=payload.severity,
        description=payload.description,
        status="Investigating"
    )
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)
    incidents_created.add(1, {"severity": new_incident.severity})
    logger.info("incident created id=%s severity=%s service=%s",
                new_incident.id, new_incident.severity, new_incident.service_name)
    return new_incident

@app.post("/incidents/{incident_id}/resolve", response_model=IncidentResponse)
def resolve_incident(incident_id: int, db: Session = Depends(get_db)):
    inc = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    inc.status = "Resolved"
    inc.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(inc)
    incidents_resolved.add(1)
    logger.info("incident resolved id=%s", inc.id)
    return inc

if os.getenv("CHAOS_ENABLED", "false").lower() == "true":
    @app.get("/chaos/error")
    def chaos_error():
        logger.error("chaos endpoint triggered deliberate failure")
        raise HTTPException(status_code=500, detail="Deliberate failure")