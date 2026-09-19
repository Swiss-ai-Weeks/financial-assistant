# ClaimGraph Desk
#
#   make setup   install backend + frontend dependencies
#   make dev     run the API (:8080) and the UI (:5173)
#
#   make news    download GDELT news into the local archive
#
# On the GPU box, additionally:
#
#   make llm     serve Nemotron on the two H100s (:8000)
#   make search  start SearXNG for wider web retrieval (:8888)

PYTHON  ?= python3
VENV    := .venv
BIN     := $(VENV)/bin
API_PORT ?= 8080

.DEFAULT_GOAL := help

.PHONY: help setup dev api web build serve news llm search test lint reset

help:
	@awk '/^# /{sub(/^# ?/,"");print} /^$$/{exit}' Makefile

$(VENV):
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip

setup: $(VENV)
	$(BIN)/pip install -q -e ".[dev]"
	cd frontend && npm install --no-audit --no-fund
	@test -f .env || cp .env.example .env
	@echo "Ready. Run: make dev"

dev:
	@API_PORT=$(API_PORT) ./scripts/dev.sh

api:
	$(BIN)/uvicorn financial_assistant.api.main:app --reload --port $(API_PORT)

web:
	cd frontend && npm run dev

# One process, one port: the API serves the built UI.
build:
	cd frontend && npm run build

serve: build
	$(BIN)/uvicorn financial_assistant.api.main:app --host 0.0.0.0 --port $(API_PORT)

# Resumable. Pass options with ARGS, e.g. ARGS="--universe".
news:
	$(BIN)/python scripts/download_gdelt.py $(ARGS)

llm:
	./scripts/serve_llm.sh

search:
	docker compose -f infra/docker-compose.yml up -d searxng

test:
	$(BIN)/python -m pytest -q
	cd frontend && npm run lint

lint:
	cd frontend && npm run lint

# Forget the edited book and past investigations; keep caches.
reset:
	rm -rf data/state
