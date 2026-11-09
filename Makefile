PYTHON ?= .venv/bin/python
MANAGE = $(PYTHON) backend/manage.py

.PHONY: install migrate run worker test check seed docker-up docker-down lint format frontend-install frontend-dev frontend-build

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

migrate:
	$(MANAGE) migrate

run:
	$(MANAGE) runserver 0.0.0.0:8000

worker:
	cd backend && ../.venv/bin/celery -A config worker --loglevel=INFO

test:
	$(MANAGE) test accounts organizations customers infrastructure incidents config ai_engine.test_diagnostics ai_engine.test_tools

check:
	$(MANAGE) check
	$(MANAGE) makemigrations --check --dry-run

seed:
	$(MANAGE) seed_demo

docker-up:
	docker compose up --build

docker-down:
	docker compose down

lint:
	.venv/bin/ruff check backend

format:
	.venv/bin/ruff format backend

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build
