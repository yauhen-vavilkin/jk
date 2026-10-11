# The gate, in one command. Every target is the command the README documents.
.DEFAULT_GOAL := check
UV := uv run --locked --offline

.PHONY: bootstrap check check-python check-web build serve fixtures docker-up docker-down

bootstrap:
	uv sync --locked
	cd web && npm ci

check: check-python check-web

check-python:
	$(UV) pytest -q
	$(UV) ruff check .
	$(UV) ruff format --check .
	git diff --check

check-web:
	cd web && npm run typecheck && npm test && npm run build

build:
	cd web && npm ci && npm run build

serve: build
	$(UV) jk serve

# Look at the panel with fixture data, without a controller.
fixtures:
	$(UV) python -m tests.fixture_server --port 8799 --dist web/dist

# The web panel in Docker; README "Run it in Docker".
docker-up:
	docker compose up -d

docker-down:
	docker compose down
