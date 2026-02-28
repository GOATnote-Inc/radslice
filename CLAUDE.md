# RadSlice — Multimodal Radiology LLM Benchmark

## Project Overview
Benchmarks frontier multimodal LLMs (GPT-5.2, Claude Opus/Sonnet 4.6, Gemini 2.5 Pro) on radiology image interpretation across X-ray, CT, MRI, and Ultrasound. Every task is grounded in a real clinical condition from the OpenEM emergency medicine corpus via `condition_id`.

## Corpus
- **320 tasks** across 133 unique OpenEM conditions (one per condition×modality pair)
- 72 X-ray, 106 CT, 53 MRI, 89 Ultrasound
- 65 tasks cross-referenced to LostBench scenarios (MTR/DEF IDs)
- Difficulty: 21 basic, 85 intermediate, 175 advanced, 39 expert
- `condition_id` (required) links each task to an OpenEM condition
- `lostbench_scenario_id` (optional) enables cross-repo safety analysis

## Architecture
- **Task YAMLs** define evaluation cases with ground truth, pattern checks, OpenEM condition links
- **Providers** abstract multimodal LLM APIs (OpenAI, Anthropic, Google)
- **Executor** runs NxM matrix (tasks × models × trials) with concurrency limits
- **3-Layer Grading**: Layer 0 (deterministic patterns) → Layer 2 (LLM radiologist judge)
- **Scoring**: pass@k, pass^k, Wilson CI, bootstrap CI, two-proportion z-test
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
- Every task YAML must have a valid `condition_id` referencing an OpenEM condition

## Grading Dimensions
| Dimension | Weight |
|-----------|--------|
| Diagnostic accuracy | 0.35 |
| Finding detection | 0.25 |
| Anatomic precision | 0.15 |
| Clinical relevance | 0.15 |
| False positive control | 0.10 |

## File Layout
- `src/radslice/` — All source code
  - `cli.py` — CLI entry point
  - `task.py` — Task dataclass, loader, validator (condition_id required)
  - `executor.py` — Async matrix executor
  - `scoring.py` — pass@k, pass^k, Wilson CI, bootstrap
  - `analysis.py` — Per-modality/anatomy breakdowns
  - `report.py` — Report generation and comparison
  - `corpus/` — Manifest, download, validation
  - `grading/patterns.py` — Layer 0 deterministic checks
  - `grading/judge.py` — Layer 2 LLM radiologist judge
  - `grading/rubric.py` — Rubric definitions
  - `providers/` — OpenAI, Anthropic, Google, disk-cached wrapper
- `configs/tasks/{xray,ct,mri,ultrasound}/` — 320 task YAMLs (OpenEM-grounded)
- `configs/models/` — Provider config YAMLs
- `configs/matrices/` — Sweep configs (full, quick_smoke)
- `configs/rubrics/` — Grading rubric
- `corpus/` — Manifest, download script, annotations
- `tests/` — 1,218 tests, no API keys required
- `results/` — Gitignored, populated by runs

## Cross-Repo Context
- **OpenEM** (`openem-corpus`): Tasks reference conditions by `condition_id` (reference only, no runtime import)
- **LostBench** (`lostbench`): 65 tasks have `lostbench_scenario_id` for cross-cutting safety analysis
- **Architecture doc**: `scribegoat2/docs/CROSS_REPO_ARCHITECTURE.md` covers all 5 GOATnote repos
- No runtime imports from any other GOATnote repo — RadSlice is independently installable
