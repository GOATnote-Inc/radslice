.PHONY: test lint smoke format install clean audit calibrate sourcing-progress discover validate-images

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

sourcing-progress:
	python scripts/sourcing_progress.py

discover:
	python scripts/discover_multicare.py --batch configs/tasks/xray/ --top 3
	python scripts/discover_multicare.py --batch configs/tasks/ct/ --top 3

validate-images:
	python scripts/validate_pathology.py --all --model gpt-5.2 --update-sources

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
