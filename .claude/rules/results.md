# Results Rules

## index.yaml Is Source of Truth

`results/index.yaml` is the canonical experiment manifest. Every evaluation campaign that completes Phase 5 (Govern) gets an entry. Format:

```yaml
experiments:
  - id: eval-20260228-gpt52-xray
    date: "2026-02-28"
    model: gpt-5.2
    modality: xray
    n_tasks: 72
    n_trials: 3
    pass_rate: 0.583
    class_a_count: 2
    ers: 8
    decision: CLEAR
    results_dir: results/eval-20260228-gpt52-xray/
    cost_estimated_usd: 12.50
    cost_actual_usd: null
    notes: ""
```

## Directory Naming Convention

```
results/eval-{YYYYMMDD}-{model}-{modality}/
```

Examples:
- `results/eval-20260228-gpt52-xray/`
- `results/eval-20260228-opus46-ct/`
- `results/eval-20260228-full-all/` (full matrix)

## Contents of a Results Directory

| File | Written By | Immutable |
|------|-----------|-----------|
| `grades.jsonl` | eval-operator | Yes |
| `transcripts.jsonl` | eval-operator | Yes |
| `tasks_dir.txt` | eval-operator | Yes |
| `grades_regraded.jsonl` | grade command | Yes (separate file) |
| `analysis.json` | radiology-analyst | Yes |
| `saturation.json` | corpus-strategist | Yes |

## Immutability

Results are **write-once, read-many**. Never:
- Modify existing grades.jsonl
- Delete results directories
- Overwrite transcripts

Re-grading creates `grades_regraded.jsonl` as a separate artifact.

## Cached Results

Response cache is per-output-directory at `{output_dir}/.cache/`. Cache entries are keyed by SHA-256 of (model, messages, temperature, seed). Cached responses include integrity hashes; corrupted entries are quarantined to `.cache_corrupted/`.
