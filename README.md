# Incident Hub: Incident Tracking with an AI On-Call Agent

An incident-management hub that receives alerts from a monitoring stack, keeps a timeline of notes for each incident, and uses an **on-call agent** to investigate automatically. When an alert fires, the agent gathers evidence from metrics, logs and traces, opens an incident, and writes a diagnostic note for the responder.

## Live demo

- **Production dashboard:** https://incident-hub-prod-web.onrender.com
- **Production API docs:** https://incident-hub-esv5.onrender.com/docs


Note: the services run on Render's free plan. The first request after a period of inactivity can take up to a minute while the backend wakes up, and the free database expires after 30 days, so the live demo may stop working after that.


> **Scope note.** In this project the hub monitors **itself**, and failures are injected on purpose with a chaos endpoint so the whole alert-to-agent pipeline can be demonstrated. Everything after the injected failure (metrics, alert rule, webhook, agent, incident, note) runs for real. In real use the same pipeline would watch other services. See [Future work](#future-work).

## Problem

When production breaks, responders lose time gathering context: alerts, error rates, logs and traces live in different tools, and the first investigation step starts only after a human is paged. Teams also lose the story of what happened, because triage notes are scattered across chat threads.

This project gives responders one place that shows what is broken, what the monitoring data says, and what has been tried, and it automates the first investigation step so a human starts with evidence rather than from zero.

## What the system does

1. **Incident tracking.** Create incidents with a service name, title and severity (P1 to P4). Incidents go from `Investigating` to `Resolved`, with timestamps.
2. **Timeline notes.** Humans and the on-call agent add notes to an incident. The dashboard shows them, with agent notes labelled.
3. **Dashboard.** A single-page UI shows a status badge, active outages, incident IDs and an expandable timeline per incident.
4. **Observability.** The backend emits traces, metrics and structured JSON logs (with trace IDs) through OpenTelemetry to Tempo, Prometheus and Grafana.
5. **Alerting.** A Grafana alert rule fires when more than 5% of requests return 5xx for one minute.
6. **On-call agent.** A webhook service receives the alert, runs three evidence tools (Prometheus query, recent error logs, error traces from Tempo) and posts a diagnostic note on a new incident. It uses Claude to summarise when `ANTHROPIC_API_KEY` is set and a rule-based summary otherwise.

## Architecture

```
                 +-----------+       +-------------------+
 Browser ------> | frontend  | ----> | backend (FastAPI) | ----> PostgreSQL
                 +-----------+       +---------+---------+
                                               | OTLP (traces + metrics)
                                               v
                                      +------------------+
                                      |  OTel Collector  |
                                      +----+--------+----+
                                   traces  |        |  metrics
                                           v        v
                                        Tempo    Prometheus
                                            \      /
                                             v    v
                                             Grafana --alert webhook--> on-call agent
                                                                             |
                  reads:  Prometheus, Tempo, backend /internal/logs          |
                  writes: POST /incidents, POST /incidents/{id}/notes -------+
```

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Pydantic |
| Database | PostgreSQL (SQLite in tests) |
| Frontend | HTML, Tailwind CSS (CDN), vanilla JavaScript |
| Tests | pytest, FastAPI TestClient |
| Containers | Docker, Docker Compose |
| CI/CD | GitHub Actions, GitHub Environments, Render |
| Observability | OpenTelemetry, OTel Collector, Tempo, Prometheus, Grafana |
| Agent | FastAPI webhook service, optional Claude API |

## Project structure

```
backend/            FastAPI app, models, telemetry setup, tests
frontend/           index.html dashboard, config.js (API address)
oncall-agent/       alert webhook receiver and diagnostic agent
observability/      collector, Tempo, Prometheus and Grafana provisioning
                    (datasources, dashboard, alert rule, contact point)
.github/workflows/  ci.yml, cd.yml
docker-compose.yml
AGENTS.md           instructions for AI coding agents
```

## Run locally

Requirement: Docker Desktop.

```
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:3000 | Dashboard |
| http://localhost:8000/docs | API docs (Swagger) |
| http://localhost:3001 | Grafana (dashboard "Incident Hub Overview", alert rules) |
| http://localhost:9090 | Prometheus |
| http://localhost:9000/health | On-call agent |

Optional: create a `.env` file in the repo root with `ANTHROPIC_API_KEY=sk-ant-...` to enable LLM summaries in the agent. Without it the agent writes a rule-based note. Never commit `.env`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/incidents` | List incidents, newest first |
| POST | `/incidents` | Create an incident |
| POST | `/incidents/{id}/resolve` | Mark an incident resolved |
| GET | `/incidents/{id}/notes` | List timeline notes |
| POST | `/incidents/{id}/notes` | Add a timeline note |
| GET | `/internal/logs` | Recent logs for the agent (requires `X-Internal-Token`) |
| GET | `/chaos/error` | Deliberate 500; exists only when `CHAOS_ENABLED=true` |

## Tests

```
cd backend
pip install -r requirements.txt
pytest
```

Tests use a SQLite file and disable OpenTelemetry, so no other services are needed. They cover the health check, creating, listing and resolving incidents, and timeline notes. CI runs the same command.

## CI/CD

**CI** (`.github/workflows/ci.yml`) runs on every push and pull request to `main`: install dependencies, run pytest, then build the backend Docker image.

**CD** (`.github/workflows/cd.yml`) runs after CI succeeds on `main`:

1. `deploy-dev` triggers the Render deploy hooks for the dev backend and frontend, then smoke-tests `/health`.
2. `deploy-prod` is bound to the `production` GitHub Environment, which requires **manual approval** from a reviewer. After approval it deploys production and smoke-tests it.

Render auto-deploy is off for every service, so deployments happen only through this pipeline.

## Deployment (Render)

| Environment | Backend | Frontend | Database |
|---|---|---|---|
| dev | Docker web service | Static site | Database in the shared Render Postgres |
| prod | Docker web service | Static site | Separate database (`incident_prod`) in the same instance |

Each static site generates `config.js` at build time from its `API_URL` variable, so each frontend talks to its own backend. Only the application is deployed to Render. The observability stack and the on-call agent run through Docker Compose.

## Observability and alerting

- **Traces:** FastAPI and SQLAlchemy are auto-instrumented. Each request produces a trace with database spans nested under it (Grafana, Explore, Tempo).
- **Metrics:** HTTP request count and latency from the instrumentation, plus business counters `incidents_created` and `incidents_resolved`.
- **Logs:** JSON, with `trace_id` and `span_id` on each line so a log entry can be matched to its trace.
- **Dashboard:** request rate by status, p95 latency, 5xx ratio, and incidents by severity.
- **Alert:** "High 5xx error rate" fires when the 5xx ratio stays above 5% for one minute.

### Demonstrating the alert flow (fault injection)

A healthy app never fails on cue, so the project includes a chaos endpoint, enabled only locally with `CHAOS_ENABLED=true`. To run the demo:

1. Start the stack and send failing requests (PowerShell):
   ```
   1..60 | ForEach-Object { try { Invoke-WebRequest http://localhost:8000/chaos/error -UseBasicParsing | Out-Null } catch {} ; Start-Sleep -Milliseconds 200 }
   ```
2. In Grafana, under Alerting, Alert rules, watch the rule go Pending and then Firing.
3. Grafana calls the agent webhook. A new P1 incident appears in the dashboard with an `oncall-agent` note containing the evidence.

You can also test the agent alone by posting a sample alert payload to `http://localhost:9000/alert`.

## On-call agent design

- It can only create incidents and add notes. It cannot restart, scale or modify anything.
- Log content is passed to the LLM as data, with an instruction not to follow it, because log text can be attacker-controlled.
- When the alert resolves, the agent adds a note but leaves the incident open, so a human confirms and closes it.
- If the LLM call fails or no key is set, it falls back to a rule-based summary.

## Known limitations

- Failures are injected for the demo; the hub currently monitors only itself.
- Dev and prod share one Render Postgres instance (two databases), so they are isolated by database, not by infrastructure.
- Render deploy hooks are fire-and-forget. The smoke test shows the service is up, not that this exact commit is live.
- The observability stack and the agent run locally through Docker Compose, not on Render.
- The agent keeps its alert-to-incident mapping in memory, so it is lost on restart and a repeated alert could create a duplicate incident.
- The log buffer served to the agent is in memory and holds only recent lines. Loki would be the production replacement.
- The API has no user authentication. Only the internal logs endpoint is protected, by a shared token.
- Database tables are created with `create_all`; there are no migrations.

## Future work

- Monitor other services: send their telemetry to the same collector, add alert rules per service, and filter the agent's evidence queries by service.
- Run the hub separately from the services it watches, so an outage does not take down the incident tool too.
- Persist the agent's alert mapping and add an automated test for the webhook handler.
- Add authentication, paging (Slack or phone), and database migrations (Alembic).
- Replace the in-memory log buffer with Loki.

## Project board

Task tracking: [GitHub Projects board](https://github.com/users/IoakeimKyrgiafinis/projects/3)
