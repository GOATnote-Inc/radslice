# Contributing

Solo-maintained research benchmark; issues and PRs welcome.

Setup: `uv venv .venv && uv pip install -e ".[dev]"`. Test: `pytest -q` (hermetic; no live API calls). Lint: `ruff check . && ruff format --check src tests`.

PRs target `main`; required checks: test (3.10/3.12/3.13) and smoke. One focused change per PR; tests required for behavior changes. Never commit anything under `results/` or corpus images without a provenance row in `corpus/image_sources.yaml`.

Contact: b@thegoatnote.com
