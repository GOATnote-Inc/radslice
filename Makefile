.PHONY: test lint smoke format install clean audit calibrate

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v --tb=short

smoke:
	python -m pytest tests/ -v -k "smoke" --tb=short

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

audit:
	python scripts/run_audit.py --results-dirs $$(ls -d results/eval-* 2>/dev/null || echo "")

calibrate:
	radslice calibration --results-dirs $$(ls -d results/eval-* 2>/dev/null || echo "")

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
