PYTHON ?= python3

.PHONY: test lint smoke format install clean audit calibrate sourcing-progress discover validate-images source-phase1

install:
	pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

smoke:
	$(PYTHON) -m pytest tests/ -v -k "smoke" --tb=short

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

audit:
	$(PYTHON) scripts/run_audit.py --results-dirs $$(ls -d results/eval-* 2>/dev/null || echo "")

calibrate:
	radslice calibration --results-dirs $$(ls -d results/eval-* 2>/dev/null || echo "")

sourcing-progress:
	$(PYTHON) scripts/sourcing_progress.py

discover:
	$(PYTHON) scripts/discover_multicare.py --batch configs/tasks/xray/ --top 3
	$(PYTHON) scripts/discover_multicare.py --batch configs/tasks/ct/ --top 3

validate-images:
	$(PYTHON) scripts/validate_pathology.py --all --model gpt-5.2 --update-sources

source-phase1:
	$(PYTHON) scripts/source_phase1.py --modality all --limit 100 --model gpt-5.2 --resume

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
