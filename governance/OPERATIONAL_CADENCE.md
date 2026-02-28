# Operational Cadence

## Scheduled Operations

### Daily (~$5-15)
- **Audit check**: `radslice calibration` on calibration set (pattern-only, no API cost)
- **Regression scan**: Compare latest results to prior run (pattern-only)
- Triggered by: CI or manual

### Weekly (~$30-60)
- **Full sweep**: `radslice run` on calibration set + regression suite with LLM judge
- **Saturation check**: `radslice saturation` across recent results
- **Suite update**: `radslice suite-update` to promote/retire tasks
- Triggered by: scheduled or eval-lead

### Event-Driven
- **New model intake**: Full corpus evaluation when new model version released
  - Cost: ~$50-100 (all 320 tasks, n=3, LLM judge)
  - Triggers: saturation re-assessment, regression detection, cross-repo correlation
- **Post-fix validation**: Re-run failed tasks after grading or pattern fix
  - Cost: ~$5-20 (targeted subset)
- **Corpus evolution**: Generate new tasks when saturation threshold reached
  - Cost: ~$10-30 (generation + validation run)

## Cost Model

Per-run cost depends on:
- Number of tasks (320 full, 30 calibration, variable regression suite)
- Number of trials (n=1 smoke, n=3 standard, n=5 high-confidence)
- Judge cost (pattern-only = $0, LLM judge = ~$0.05-0.15 per task)
- Vision tokens (dominant cost for multimodal — ~$0.10-0.50 per image per model)

Reference: `configs/model_pricing.yaml` for per-token pricing.

## Budget Controls

- eval-lead computes cost estimate before every campaign (Phase 1)
- Campaigns exceeding estimate by >50% trigger BLOCK
- Weekly budget cap: $100 (configurable)
- Monthly budget cap: $500 (configurable)
