# Agent Coordination Rules

## File Ownership

| File | Owner | Others |
|------|-------|--------|
| `results/index.yaml` | eval-lead | read-only |
| `results/risk_debt.yaml` | eval-lead | read-only |
| `results/suite_membership.yaml` | eval-lead | read-only (corpus-strategist proposes) |
| `results/audit_log.yaml` | program-auditor | read-only |
| `results/*/grades.jsonl` | eval-operator | immutable after write |
| `results/*/transcripts.jsonl` | eval-operator | immutable after write |
| `configs/tasks/` | eval-lead (approves) | corpus-strategist proposes, eval-operator generates |

## Safety-Critical Zones

These paths require `[PROPOSED CHANGES]` pattern — never direct modification by analysis agents:
- `results/suite_membership.yaml`
- `results/risk_debt.yaml`
- `results/index.yaml`
- `configs/tasks/` (new or modified tasks)
- `configs/calibration/`

## [PROPOSED CHANGES] Pattern

Analysis agents (radiology-analyst, corpus-strategist) propose changes like:
```
[PROPOSED CHANGES]
<description of what should change and why>
[END PROPOSED CHANGES]
```
eval-lead reviews and applies or rejects.

## Model Selection

| Agent | Model | Rationale |
|-------|-------|-----------|
| eval-lead | opus | Deep reasoning for governance decisions |
| eval-operator | sonnet | Fast execution, no deep reasoning needed |
| radiology-analyst | opus | Clinical reasoning for harm mapping |
| corpus-strategist | sonnet | Strategy selection, no clinical reasoning |
| program-auditor | sonnet | Structured audit, no deep reasoning |

## Fail-Loud Protocol

- eval-operator: stop on any API error, report immediately
- radiology-analyst: flag if grades.jsonl is malformed or empty
- corpus-strategist: flag if suite_membership.yaml is inconsistent with task counts
- program-auditor: flag if audit_log.yaml is corrupted

## Immutable Results

Once `grades.jsonl` and `transcripts.jsonl` are written to a results directory, they are **never modified**. Re-grading produces a separate file (`grades_regraded.jsonl`).

## Determinism

- All evaluations: temperature=0.0, seed=42
- All scoring: deterministic (no random sampling except bootstrap CI with fixed seed=42)
- All task generation: reproducible with same inputs
