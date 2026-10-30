# AI Agent Instructions - Incident Hub

## Tech Stack
- **Backend:** Python / FastAPI, SQLAlchemy, Pydantic, Pytest
- **Database:** PostgreSQL (with SQLite for local testing)
- **Frontend:** HTML5 / Tailwind CSS
- **DevOps:** Docker, Docker Compose, GitHub Actions CI/CD

## Core Architecture Rules
1. **Single Command Start:** `docker compose up --build` must boot up the database, backend API, and frontend server.
2. **API Contract:** Backend endpoints must remain clean and documented via FastAPI's automatic OpenAPI spec (`/docs`).
3. **Observability:** Key request logs must propagate trace IDs.