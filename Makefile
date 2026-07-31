.PHONY: run clean smoke test

PYTHON ?= python3

run:
	$(PYTHON) -m uvicorn app.main:app --reload

smoke:
	$(PYTHON) -c "from app.main import app; assert app.title == 'LiveFireTTX'; print('Smoke test passed')"

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf generated livefirettx.db __pycache__ .pytest_cache
	find app -type d -name __pycache__ -prune -exec rm -rf {} +
