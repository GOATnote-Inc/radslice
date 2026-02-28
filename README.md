# RadSlice

Multimodal radiology LLM benchmark. Evaluates frontier vision-language models on radiological image interpretation across four modalities: X-ray, CT, MRI, and Ultrasound. Every task is grounded in a real clinical condition from the [OpenEM](https://github.com/GOATnote-Inc/openem-corpus) emergency medicine corpus.

## Why RadSlice

Multimodal LLMs are increasingly used for radiology triage and decision support, but there is no standardized benchmark that tests across modalities, anatomy regions, and difficulty levels with clinically rigorous grading. RadSlice fills this gap with:

- **320 tasks** across 133 OpenEM conditions and 4 imaging modalities, linked by `condition_id`
- **65 cross-references** to LostBench safety persistence scenarios for cross-cutting analysis
- **3-layer grading** combining deterministic pattern checks with cross-vendor LLM radiologist judges
- **Statistically grounded metrics** — pass@k, pass^k, Wilson confidence intervals, bootstrap CI, regression detection

## Quick start

```bash
# Install
pip install -e ".[dev]"

# Validate the corpus
radslice corpus validate --tasks-dir configs/tasks

# Run a quick smoke test (requires OPENAI_API_KEY)
radslice run --matrix configs/matrices/quick_smoke.yaml --output-dir results/smoke

# Grade with a different judge
radslice grade --results results/smoke --judge-model claude-opus-4-6

# Analyze results
radslice analyze --results results/smoke --per-modality --per-anatomy
```

## Corpus

320 tasks grounded in 133 unique [OpenEM](https://github.com/GOATnote-Inc/openem-corpus) conditions (131 imaging-relevant out of 185 total). One task per condition×modality pair.

| Modality   | Tasks | Conditions | Difficulty spread |
|------------|-------|------------|-------------------|
| X-ray      | 72    | 72         | 8 basic, 20 intermediate, 39 advanced, 5 expert |
| CT         | 106   | 106        | 3 basic, 28 intermediate, 64 advanced, 11 expert |
| MRI        | 53    | 53         | 1 basic, 6 intermediate, 40 advanced, 6 expert |
| Ultrasound | 89    | 89         | 9 basic, 31 intermediate, 30 advanced, 19 expert |
| **Total**  | **320** | **133 unique** | **21 basic, 85 intermediate, 175 advanced, 39 expert** |

Each task YAML includes:
- `condition_id` linking to an OpenEM condition (e.g. `spontaneous-pneumothorax`)
- `lostbench_scenario_id` cross-reference where applicable (65 tasks, e.g. `MTR-016`)
- Ground truth with primary diagnosis, differentials, key findings, laterality, severity
- Required and optional pattern checks (regex)
- Reference radiologist solution

## Models tested

| Model | Provider |
|-------|----------|
| GPT-5.2 | OpenAI |
| Claude Opus 4.6 | Anthropic |
| Claude Sonnet 4.6 | Anthropic |
| Gemini 2.5 Pro | Google |

## Grading

Three-layer grading pipeline:

1. **Layer 0 — Deterministic patterns**: Regex checks for required findings, laterality, diagnosis mentions. Fast, reproducible, no API cost.
2. **Layer 2 — LLM radiologist judge**: Cross-vendor LLM grades the model response against the ground truth rubric across 5 dimensions.

Five scoring dimensions:

| Dimension | Weight | What it measures |
|-----------|--------|------------------|
| Diagnostic accuracy | 0.35 | Correct primary diagnosis and differentials |
| Finding detection | 0.25 | Required and optional findings identified |
| Anatomic precision | 0.15 | Correct localization and laterality |
| Clinical relevance | 0.15 | Appropriate urgency, follow-up recommendations |
| False positive control | 0.10 | Avoidance of hallucinated findings |

## Metrics

- **pass@k** — probability that at least 1 of k trials passes
- **pass^k** — probability that all k trials pass (deployment safety gate)
- **Wilson CI** — confidence intervals on all proportions
- **Bootstrap CI** — 10,000-sample bootstrap for composite scores
- **Two-proportion z-test** — regression detection between runs

## CLI reference

```
radslice run        Run evaluation matrix (tasks x models x trials)
radslice grade      Re-grade existing results with different judge/settings
radslice analyze    Per-modality, per-anatomy breakdowns with CI
radslice report     Generate comparison reports between runs
radslice corpus validate   Validate task YAMLs
radslice corpus download   Fetch corpus images with checksum verification
```

Key flags for `radslice run`:

| Flag | Description |
|------|-------------|
| `--matrix PATH` | Matrix config YAML (models, trials, concurrency) |
| `--n-trials N` | Trials per task (default: from matrix) |
| `--resume / --no-resume` | Resume from checkpoint |
| `--cache / --no-cache` | Cache API responses |
| `--pattern-only` | Skip LLM judge, patterns only |
| `--judge-model MODEL` | Override judge model |
| `--modality MOD` | Filter to one modality |
| `--max-concurrency N` | Parallel API calls |

## Project layout

```
src/radslice/
  cli.py              CLI entry point
  task.py             Task dataclass and loader
  executor.py         Async matrix executor
  scoring.py          pass@k, pass^k, Wilson CI, bootstrap
  analysis.py         Per-modality/anatomy breakdowns
  report.py           Report generation and comparison
  corpus/             Manifest, download, validation
  grading/
    patterns.py       Layer 0 deterministic checks
    judge.py          Layer 2 LLM radiologist judge
    rubric.py         Rubric definitions
  providers/
    base.py           Provider protocol
    openai.py         GPT-5.2
    anthropic.py      Opus/Sonnet 4.6
    google.py         Gemini 2.5 Pro
    cache.py          Disk-cached wrapper

configs/
  tasks/{xray,ct,mri,ultrasound}/   320 task YAMLs (grounded in OpenEM)
  models/                            Per-model configs
  matrices/                          Sweep configs (full, quick_smoke)
  rubrics/                           Grading rubric

tests/                1,218 tests, no API keys required
```

## Development

```bash
pip install -e ".[dev]"
make test        # pytest
make lint        # ruff check + format
make smoke       # smoke tests only
```

## License

Apache 2.0
