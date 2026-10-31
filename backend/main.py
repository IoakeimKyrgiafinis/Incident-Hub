from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging
from telemetry import setup_telemetry, incidents_created, incidents_resolved
from fastapi import Header
from telemetry import LOG_BUFFER
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


class NoteCreate(BaseModel):
    body: str
    author: Optional[str] = "human"


class NoteResponse(BaseModel):
    id: int
    incident_id: int
    author: str
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


@app.post("/incidents/{incident_id}/notes", response_model=NoteResponse)
def add_note(incident_id: int, payload: NoteCreate, db: Session = Depends(get_db)):
    if not db.query(models.Incident).filter(models.Incident.id == incident_id).first():
        raise HTTPException(status_code=404, detail="Incident not found")
    note = models.Note(incident_id=incident_id, author=payload.author, body=payload.body)
    db.add(note)
    db.commit()
    db.refresh(note)
    logger.info("note added incident=%s author=%s", incident_id, payload.author)
    return note


@app.get("/incidents/{incident_id}/notes", response_model=List[NoteResponse])
def list_notes(incident_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Note)
        .filter(models.Note.incident_id == incident_id)
        .order_by(models.Note.created_at)
        .all()
    )


@app.get("/internal/logs")
def internal_logs(level: str = "ERROR", limit: int = 50,
                  x_internal_token: Optional[str] = Header(default=None)):
    if x_internal_token != os.getenv("INTERNAL_TOKEN", "dev-token"):
        raise HTTPException(status_code=403, detail="Forbidden")
    order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_level = order.get(level.upper(), 3)
    rows = [r for r in LOG_BUFFER if order.get(r.get("level"), 1) >= min_level]
    return rows[-limit:]