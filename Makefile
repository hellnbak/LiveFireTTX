.PHONY: run clean smoke test coverage lint typecheck security secret-scan build release-check docker-smoke app-container-smoke

PYTHON ?= python3

run:
	$(PYTHON) -m uvicorn app.main:app --reload

smoke:
	$(PYTHON) -c "from app.main import app; assert app.title == 'LiveFireTTX'; print('Smoke test passed')"

test:
	$(PYTHON) -m unittest discover -s tests -v

coverage:
	$(PYTHON) -m coverage run -m unittest discover -s tests
	$(PYTHON) -m coverage report

lint:
	$(PYTHON) -m ruff check app tests scripts
	$(PYTHON) -m compileall -q app tests scripts

typecheck:
	$(PYTHON) -m mypy app

security:
	$(PYTHON) -m pip_audit --local --skip-editable \
		--ignore-vuln PYSEC-2026-161 \
		--ignore-vuln PYSEC-2026-248 \
		--ignore-vuln PYSEC-2026-249 \
		--ignore-vuln PYSEC-2026-2280 \
		--ignore-vuln PYSEC-2026-2281

secret-scan:
	$(PYTHON) scripts/secret_scan.py

build:
	$(PYTHON) -m build

release-check: lint typecheck coverage smoke security secret-scan build

docker-smoke:
	bash scripts/docker_release_smoke.sh

app-container-smoke:
	bash scripts/app_container_smoke.sh

clean:
	rm -rf generated backups dist build *.egg-info livefirettx.db __pycache__ .pytest_cache .coverage .mypy_cache .ruff_cache .release-smoke
	find app -type d -name __pycache__ -prune -exec rm -rf {} +
