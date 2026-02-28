# Evaluation Lifecycle

## 5-Phase Campaign Model

Every evaluation campaign follows five phases. Each phase has designated agents.

### Phase 1: Scope
**Agent:** eval-lead

- Load `results/index.yaml` for prior campaign history
- Load `results/audit_log.yaml` for recent audit findings
- Load `results/suite_membership.yaml` for current suite composition
- Compute cost estimate from `configs/model_pricing.yaml`
- Write pre-execution decision trace (type: CLEAR, with cost estimate)
- Define evaluation parameters: model, modality, n_trials, output directory

### Phase 2: Execute
**Agent:** eval-operator

- Run `radslice run` with parameters from Phase 1
- Report raw metrics: pass rate, Class A count, output directory
- Stop immediately on API error (fail-loud)
- Never interpret results — report only

### Phase 3: Analyze
**Agents:** radiology-analyst (parallel), corpus-strategist (parallel)

- **radiology-analyst**: Per-modality breakdown, failure classification, clinical harm mapping on every Class A
- **corpus-strategist**: Saturation detection, suite evolution proposals, coverage analysis

### Phase 4: Report
**Agent:** eval-lead

- Synthesize analysis from Phase 3 into markdown summary
- Highlight regressions, new Class A failures, saturation changes
- Reference prior campaigns from index.yaml for trends

### Phase 5: Govern
**Agent:** eval-lead

- Update `results/index.yaml` with campaign entry
- Create risk debt entries for unresolved Class A failures
- Apply or reject suite membership proposals (using `[PROPOSED CHANGES]` pattern)
- Write final decision trace (CLEAR / ESCALATE / BLOCK)
- If ESCALATE: flag for human review

## Agent-Phase Matrix

| Agent | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|-------|---------|---------|---------|---------|---------|
| eval-lead | Scope | — | — | Report | Govern |
| eval-operator | — | Execute | — | — | — |
| radiology-analyst | — | — | Analyze | — | — |
| corpus-strategist | — | — | Analyze | — | — |
| program-auditor | — | — | — | — | — |

The program-auditor operates independently via the `/audit` command, not within evaluation campaigns.
