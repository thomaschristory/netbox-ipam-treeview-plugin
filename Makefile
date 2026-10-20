COMPOSE = docker compose -f dev/docker-compose.yml
EXEC = $(COMPOSE) exec -T
PY = /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py
SEED = shell -c "exec(open('/plugin/dev/scripts/seed.py').read())"

.PHONY: test test-netbox lint format dev down restart logs static seed seed-big reseed dist docs docs-serve

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

# Zensical publishes every file under docs_dir and has no exclude setting, so the site is built
# from a staging copy of the files git can see (tracked, or untracked but not ignored). Files
# excluded locally through .gitignore or .git/info/exclude never reach site/.
DOCS_STAGE = build/docs-src

docs:
	rm -rf $(DOCS_STAGE) site
	mkdir -p $(DOCS_STAGE)
	git ls-files -z --cached --others --exclude-standard -- docs mkdocs.yml CHANGELOG.md \
		| tar --null -T - -cf - | tar -xf - -C $(DOCS_STAGE)
	cd $(DOCS_STAGE) && uv run --locked --project $(CURDIR) --group docs zensical build --strict
	mv $(DOCS_STAGE)/site site
	@if find site -path '*superpowers*' | grep -q .; then echo "site/ contains superpowers files"; exit 1; fi

# Serves the working tree directly, including locally excluded files; for local preview only.
docs-serve:
	uv run --group docs zensical serve
