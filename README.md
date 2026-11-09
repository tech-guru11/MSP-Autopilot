# MSP Autopilot

MSP Autopilot is a Django + PostgreSQL backend for managed-service-provider
incident response. It ingests alerts, correlates them into incidents, runs
evidence-grounded AI-style diagnostics, and manages policy-controlled
remediation with human approval.

## Stack

- Python 3.14, Django 6.1, Django REST Framework
- PostgreSQL 18
- Redis 8 and Celery for background investigations
- Pydantic for investigation output contracts
- Optional Strands Agents / Amazon Bedrock integration
- React + Vite frontend scaffold

## Quick start

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
# edit .env with your PostgreSQL credentials and DJANGO_SECRET_KEY
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py seed_demo
.venv/bin/python backend/manage.py runserver
```

In separate terminals, start Redis and a Celery worker for async
investigations:

```bash
redis-server
make worker
```

Demo users created by `seed_demo` are `admin`, `engineer`, and `viewer` with
password `demo-password` (newly created users only).

### Docker

```bash
cp .env.example .env
docker compose up --build
```

Backend: `http://localhost:8000`  
Frontend: `http://localhost:3000`

## Authentication

Token authentication is enabled for API clients:

```bash
curl -X POST http://localhost:8000/api-token-auth/ \
  -d "username=engineer&password=demo-password"
```

Send `Authorization: Token <key>` and `X-Organization-ID: <uuid>` with API
requests. Session authentication is also supported for the browsable API and
admin.

## Roles

Membership roles are enforced per organization:

| Role | Read | Write | Approve remediation | Manage members |
| --- | --- | --- | --- | --- |
| `viewer` | yes | no | no | no |
| `engineer` | yes | yes | no | no |
| `admin` | yes | yes | yes | yes |

## Main API routes

| Route | Purpose |
| --- | --- |
| `GET /health/` | Liveness and database readiness |
| `POST /api-token-auth/` | Obtain API token |
| `GET /api/me/` | Current user and memberships |
| `/api/organizations/` | Organizations the user belongs to |
| `/api/memberships/` | Organization membership management (admin) |
| `/api/customers/` | Tenant-scoped customers |
| `/api/assets/` | Tenant-scoped assets |
| `/api/alerts/` | Alert list/retrieve and `POST` ingestion |
| `/api/incidents/` | Incident CRUD and list filters |
| `POST /api/incidents/{id}/transition/` | Apply a validated state transition |
| `GET /api/incidents/{id}/events/` | Incident timeline |
| `POST /api/incidents/{id}/investigate/` | Run diagnostic investigation (sync or `run_async`) |
| `GET /api/tasks/{task_id}/` | Check a background task result |
| `/api/remediation-actions/` | Propose/list remediation actions |
| `POST /api/remediation-actions/{id}/approve/` | Admin approval |
| `POST /api/remediation-actions/{id}/reject/` | Admin rejection |
| `POST /api/remediation-actions/{id}/execute/` | Execute approved action |
| `POST /api/remediation-actions/{id}/rollback/` | Roll back executed action |

List endpoints support `search`, field filters, and `ordering` query params.

## Investigation engine

`backend/ai_engine/` contains:

- Pydantic schemas for structured investigation output
- A deterministic diagnostic engine for database exhaustion, CPU saturation,
  deployment regression, DNS failure, and insufficient-evidence cases
- Read-only Strands tools for service health, database metrics, logs, and
  deployments
- An optional Strands agent with a safety-focused system prompt

The deterministic engine is the working baseline. To enable the Strands agent,
install `strands-agents` and configure a supported Bedrock model.

Investigations persist to `Investigation` and `Evidence`, write an incident
timeline event, and never change incident status by themselves.

## Background jobs

Celery uses Redis as both broker and result backend:

```bash
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

Start Redis and a worker:

```bash
redis-server
make worker
```

The investigation endpoint stays synchronous by default. Add `run_async: true`
to queue it on Celery:

```bash
curl -X POST http://localhost:8000/api/incidents/<id>/investigate/ \
  -H "Authorization: Token <key>" \
  -H "X-Organization-ID: <org-id>" \
  -H "Content-Type: application/json" \
  -d '{"evidence": {"observations": {"http_status": 503}}, "run_async": true}'
```

The response is `202 Accepted` with a `task_id` and `status_url`. Poll
`/api/tasks/{task_id}/` for the Celery state and result. Tests run Celery in
eager mode, so they do not require Redis.

Docker Compose includes Redis and a worker service:

```bash
docker compose up --build
```

See `docs/BACKGROUND_JOBS.md` for task retries, status polling, and worker
configuration.

## Remediation policy

`backend/incidents/services/policy.py` defines the action catalog and risk
levels. Critical actions such as deleting a database or changing IAM policy are
prohibited. Medium/high-risk actions require administrator approval. Execution
is simulated by default (`REMEDIATION_EXECUTION_MODE=simulate`) and never
changes infrastructure.

## Tests

```bash
.venv/bin/python backend/manage.py test \
  accounts organizations customers infrastructure incidents config \
  ai_engine.test_diagnostics ai_engine.test_tools
```

Or:

```bash
make test
```

## Project layout

```text
backend/
  accounts/          custom user, /api/me
  organizations/     organizations, memberships, roles, tenant context
  customers/         customers
  infrastructure/    assets
  incidents/         alerts, incidents, investigations, remediation, tasks
  ai_engine/         schemas, diagnostics, tools, optional agent
  config/            settings, URLs, middleware, health, Celery app
frontend/            React + Vite scaffold
docs/                design and security notes
```

## Security notes

- Tenant scope is enforced by `X-Organization-ID` membership checks and
  tenant-filtered querysets.
- The AI agent has read-only tools only; recommendations are data, not actions.
- Prompt-injection defenses treat logs and retrieved content as untrusted.
- Critical remediation actions are blocked by policy.
- Human approval is required for medium/high-risk actions.
- See `docs/LESSON6_SECURITY.md` for the Lesson 6 threat discussion.

## Next steps

- Replace simulated remediation executors with least-privilege provider adapters.
- Add real monitoring/log/deployment integrations.
- Add periodic SLA checks and alert-processing jobs on Celery.
- Add notifications/escalation integrations (email exists; Slack/PagerDuty next).
- Expand the frontend into a full operations dashboard.
