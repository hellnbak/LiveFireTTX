.PHONY: run clean smoke

run:
	uvicorn app.main:app --reload

smoke:
	python -c "from app.main import app; assert app.title == 'LiveFireTTX'; print('Smoke test passed')"

clean:
	rm -rf generated livefirettx.db __pycache__ .pytest_cache
	find app -type d -name __pycache__ -prune -exec rm -rf {} +
