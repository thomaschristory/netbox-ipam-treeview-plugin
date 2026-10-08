COMPOSE = docker compose -f dev/docker-compose.yml
EXEC = $(COMPOSE) exec -T
PY = /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py
SEED = shell -c "exec(open('/plugin/dev/scripts/seed.py').read())"

.PHONY: test test-netbox lint format dev down restart logs static seed seed-big reseed dist

test:
	uv run pytest -v

test-netbox:
	$(EXEC) -e DEBUG=false netbox $(PY) test --keepdb --noinput --parallel 1 /plugin/tests_netbox

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

dev:
	$(COMPOSE) up -d --build --wait --wait-timeout 1200

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart netbox netbox-worker

logs:
	$(COMPOSE) logs -f netbox

static:
	$(EXEC) -u root netbox $(PY) collectstatic --no-input -v 0

seed:
	$(EXEC) netbox $(PY) $(SEED)

seed-big:
	$(EXEC) -e SEED_SCALE=5 netbox $(PY) $(SEED)

reseed:
	$(EXEC) -e SEED_RESET=1 netbox $(PY) $(SEED)

dist:
	rm -rf dist
	uv build
	uvx twine check --strict dist/*
