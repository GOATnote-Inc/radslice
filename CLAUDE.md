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

## Install Extras
- `pip install -e .` — Core install (uncompressed DICOMs work out of the box)
- `pip install -e ".[dicom-codecs]"` — Adds `pylibjpeg` + `pylibjpeg-libjpeg` (JPEG Lossless) + `pylibjpeg-openjpeg` (JPEG 2000) for compressed DICOM transfer syntaxes
- `pip install -e ".[dev]"` — Dev/test dependencies

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

## Agent Teams

5 agents in `.claude/agents/`, 3 team workflows in `.claude/commands/`.

| Agent | Model | Role |
|-------|-------|------|
| eval-lead | opus | Campaign orchestrator, budget gatekeeper, decision trace author |
| eval-operator | sonnet | Executes `radslice run`, reports raw metrics |
| radiology-analyst | opus | Per-modality/anatomy analysis, Class A harm mapping |
| corpus-strategist | sonnet | Saturation detection, suite evolution proposals |
| program-auditor | sonnet | Coverage gaps, calibration drift, risk debt review |

| Command | Description |
|---------|-------------|
| `/evaluate [model] [modality]` | Full 5-phase evaluation campaign |
| `/evolve [condition] [modality]` | Generate harder task variants |
| `/audit` | Program self-audit |

Rules in `.claude/rules/`: `agents.md` (file ownership, [PROPOSED CHANGES]), `safety.md` (determinism, cross-vendor judging), `results.md` (index.yaml, immutability).

## Governance

- **Decision framework**: `governance/DECISION_FRAMEWORK.md` — BLOCK/ESCALATE/CLEAR gates
- **Lifecycle**: `governance/EVALUATION_LIFECYCLE.md` — 5-phase campaign model
- **Cadence**: `governance/OPERATIONAL_CADENCE.md` — daily/weekly/event-driven

## Suite Membership Tracking

Tasks belong to one of three suites: **capability** (active evaluation), **regression** (discriminates models), **retired** (saturated).

- Membership tracked in `results/suite_membership.yaml`
- Promotion: task discriminates between models → regression
- Retirement: pass@5 > 0.95 for all models across 3+ consecutive runs → retired (needs evolution)
- `radslice suite-update` updates tracking and proposes promotions/retirements

## Additional CLI Commands

- `radslice saturation` — Detect saturated tasks across evaluation runs
- `radslice suite-update` — Update suite membership from results
- `radslice cross-repo` — Correlate findings with LostBench
- `radslice calibration` — Check calibration drift (Layer 0 vs Layer 2)
- `make audit` — Run program self-audit
- `make calibrate` — Run calibration check

## Modification Zones (Protected)

These paths require `[PROPOSED CHANGES]` pattern from analysis agents:
- `governance/` — Decision framework, lifecycle, cadence docs
- `.claude/` — Agent definitions, commands, rules
- `results/index.yaml` — Experiment manifest
- `results/suite_membership.yaml` — Suite membership
- `results/risk_debt.yaml` — Risk debt register
- `configs/calibration/` — Calibration set and human grades

## Cross-Repo Context
- **OpenEM** (`openem-corpus`): Tasks reference conditions by `condition_id` (reference only, no runtime import)
- **LostBench** (`lostbench`): 65 tasks have `lostbench_scenario_id` for cross-cutting safety analysis
- **Cross-repo correlation**: `radslice cross-repo` compares RadSlice and LostBench findings by condition
- **Architecture doc**: `scribegoat2/docs/CROSS_REPO_ARCHITECTURE.md` covers all 5 GOATnote repos
- No runtime imports from any other GOATnote repo — RadSlice is independently installable
