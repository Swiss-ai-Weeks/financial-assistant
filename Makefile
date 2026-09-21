# Pythia
#
#   make setup   install backend + frontend dependencies
#   make dev     run the API and the UI with hot reload (for coding)
#   make serve   one port, built UI: for a machine opened in a browser
#
#   make news    download historical news into the local archive
#   make universe  download prices for the 3,200-security universe
#   make warm    pre-build the slow caches before a demo
#   make runs    which model produced each saved explanation
#   make forget-runs   drop them (before recording on the H100s)
#
# On the GPU box, additionally:
#
#   make llm     serve Nemotron on the two H100s (:8000)
#   make apertus serve Apertus, the Swiss open model (:8001)
#   make search  start SearXNG for wider web retrieval (:8888)

PYTHON  ?= python3
VENV    := .venv
BIN     := $(VENV)/bin
API_PORT ?= 8080

.DEFAULT_GOAL := help

.PHONY: help setup dev api web build serve news universe warm runs forget-runs llm apertus search test lint reset

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
	$(BIN)/uvicorn financial_assistant.api.main:app --reload --port $(API_PORT) --timeout-graceful-shutdown 3

web:
	cd frontend && npm run dev

# One process, one port: the API serves the built UI.
build:
	cd frontend && npm run build

# Use this when the machine is reached through a browser (VS
# Code web, Launchpad): forward or open the ONE port it prints.
serve: build
	@PORT=$$(./scripts/free_port.sh $(API_PORT)); \
	echo; echo "  Pythia: http://localhost:$$PORT   (forward or open this one port)"; echo; \
	$(BIN)/uvicorn financial_assistant.api.main:app --host 0.0.0.0 --port $$PORT --timeout-graceful-shutdown 3

# Resumable. Pass options with ARGS, e.g. ARGS="--universe".
news:
	$(BIN)/python scripts/download_news.py $(ARGS)

# Prices for every security of the catalogue (Russell 2500 +
# STOXX 600). Pair scans and discovery read this cache; they
# never download thousands of tickers inside a request.
# Resumable: fresh files are skipped.
universe:
	$(BIN)/python scripts/download_universe.py $(ARGS)

# Prices for the whole universe and the walk-forward analogue
# record (minutes for ~140 names). Both are cached on disk, so
# the first "I'm Feeling Lucky" of the demo is instant.
warm:
	$(BIN)/python scripts/warm.py

# Saved explanations and triage readings are replayed without a
# model, which is what makes a recording reproducible. It also
# means a run made with the hosted model during development
# would be replayed in the final recording. These two targets
# show, and remove, exactly that state. The book is untouched.
runs:
	@$(BIN)/python scripts/list_runs.py

forget-runs:
	rm -rf data/state/investigations data/state/triage
	@echo "Forgotten. Explain and triage will run again on the active LLM_PROFILE."

llm:
	./scripts/serve_llm.sh

apertus:
	./scripts/serve_apertus.sh

search:
	docker compose -f infra/docker-compose.yml up -d searxng

test:
	$(BIN)/python -m pytest -q
	cd frontend && npm test && npm run lint

lint:
	cd frontend && npm run lint

# Forget the edited book and past investigations; keep caches.
reset:
	rm -rf data/state
