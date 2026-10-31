from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app
import models
import os
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

# Use a local SQLite database for fast, isolated testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def setup_module(module):
    Base.metadata.create_all(bind=engine)

def teardown_module(module):
    Base.metadata.drop_all(bind=engine)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_create_incident():
    response = client.post(
        "/incidents",
        json={
            "service_name": "payment-api",
            "title": "Gateway timeout errors",
            "severity": "P1",
            "description": "Stripe webhooks failing"
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["service_name"] == "payment-api"
    assert data["severity"] == "P1"
    assert data["status"] == "Investigating"
    assert "id" in data

def test_get_incidents():
    response = client.get("/incidents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

def test_resolve_incident():
    # First create an incident to resolve
    create_res = client.post(
        "/incidents",
        json={
            "service_name": "auth-service",
            "title": "Token latency spike",
            "severity": "P2"
        }
    )
    inc_id = create_res.json()["id"]

    # Now resolve it
    resolve_res = client.post(f"/incidents/{inc_id}/resolve")
    assert resolve_res.status_code == 200
    resolved_data = resolve_res.json()
    assert resolved_data["status"] == "Resolved"
    assert resolved_data["resolved_at"] is not None

def test_add_and_list_notes():
    inc = client.post("/incidents", json={"service_name": "api", "title": "t"}).json()
    res = client.post(f"/incidents/{inc['id']}/notes", json={"body": "looking into it"})
    assert res.status_code == 200
    notes = client.get(f"/incidents/{inc['id']}/notes").json()
    assert len(notes) == 1 and notes[0]["body"] == "looking into it"