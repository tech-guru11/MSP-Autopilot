# Background Jobs

MSP Autopilot uses Celery with Redis for background work. Redis is both the
broker and the result backend.

## Components

- `backend/config/celery.py`: Celery application and Django settings binding.
- `backend/config/__init__.py`: exports the Celery app for `-A config`.
- `backend/incidents/tasks.py`: investigation task with retries.
- `backend/incidents/views.py`: queues async investigations and returns `202`.
- `backend/config/views.py`: task status endpoint backed by `AsyncResult`.

## Configuration

```bash
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
CELERY_TASK_ALWAYS_EAGER=false
CELERY_TASK_TIME_LIMIT=300
CELERY_TASK_SOFT_TIME_LIMIT=240
CELERY_RESULT_EXPIRES=3600
```

Tests default `CELERY_TASK_ALWAYS_EAGER=true`, so they do not require Redis.
CI also starts Redis and forces eager mode.

## Running locally

```bash
redis-server
make worker
```

The worker command runs `celery -A config worker --loglevel=INFO` from
`backend/`.

## Async investigation

The investigation endpoint is synchronous by default. Pass `run_async: true`
to queue it:

```bash
curl -X POST http://localhost:8000/api/incidents/<id>/investigate/ \
  -H "Authorization: Token <key>" \
  -H "X-Organization-ID: <org-id>" \
  -H "Content-Type: application/json" \
  -d '{"evidence": {"observations": {"http_status": 503}}, "run_async": true}'
```

Response:

```json
{
  "task_id": "57a2882c-64b6-471d-9c4c-f359750ce344",
  "status": "queued",
  "status_url": "/api/tasks/57a2882c-64b6-471d-9c4c-f359750ce344/"
}
```

Poll the status URL for the Celery state and result.

## Retry behavior

`run_investigation_task` retries transient failures up to three times with
exponential backoff. Validation errors such as a non-investigable incident
status are not retried.

If the broker is unavailable when an async investigation is requested, the API
returns `503` instead of accepting work that cannot be queued.

## Docker Compose

Compose starts Redis and a worker:

```bash
docker compose up --build
```

The backend and worker share the same image and `backend/` volume. The worker
connects to `redis://redis:6379/0`.
