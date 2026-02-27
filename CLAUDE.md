# RadSlice — Multimodal Radiology LLM Benchmark

## Project Overview
Benchmarks frontier multimodal LLMs (GPT-5.2, Claude Opus/Sonnet 4.6, Gemini 2.5 Pro) on radiology image interpretation across CT, MRI, X-ray, and Ultrasound.

## Architecture
- **Task YAMLs** define evaluation cases with ground truth, pattern checks, grading rubrics
- **Providers** abstract multimodal LLM APIs (OpenAI, Anthropic, Google)
- **Executor** runs NxM matrix (tasks × models × trials) with concurrency limits
- **3-Layer Grading**: Layer 0 (deterministic patterns) → Layer 2 (LLM radiologist judge)
- **Scoring**: pass@k, pass^k, Wilson CI, bootstrap CI
- **Analysis**: per-modality, per-anatomy breakdowns, regression detection

## Key Commands
- `make test` — Run all tests (no API keys needed)
- `make smoke` — Smoke tests only
- `make lint` — Ruff lint + format check
- `radslice run` — Execute evaluation matrix
- `radslice grade` — Grade existing results
- `radslice analyze` — Generate analysis reports
- `radslice report` — Compare runs, generate reports
- `radslice corpus download` — Fetch corpus images
- `radslice corpus validate` — Validate task YAMLs

## Conventions
- Frozen dataclasses for all domain objects (Task, GradeResult, etc.)
- Async-first execution and grading
- JSONL streaming for results (resumable)
- Cross-vendor LLM judge (never self-judge)
- temperature=0.0, seed=42 for reproducibility
- Wilson CI on all proportions
- Images gitignored; `corpus/download.py` fetches with checksums

## File Layout
- `src/radslice/` — All source code
- `configs/tasks/` — Task YAMLs by modality
- `configs/models/` — Provider config YAMLs
- `configs/matrices/` — Sweep configs
- `corpus/` — Manifest, download script, annotations
- `tests/` — 200+ tests, no API keys required
- `results/` — Gitignored, populated by runs
