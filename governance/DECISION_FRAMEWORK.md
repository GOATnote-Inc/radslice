# RadSlice Decision Framework

## Decision Gates

Every evaluation campaign passes through three gates before results become authoritative.

### CLEAR
- All evaluation phases completed successfully
- No Class A failures (missed critical diagnosis) above risk threshold
- Calibration drift within bounds (kappa >= 0.60)
- Cost within budget estimate (+/- 20%)
- Decision trace filed in `results/index.yaml`

### ESCALATE
- Class A failure on previously-passing task (regression)
- Calibration drift detected (kappa < 0.60 or agreement < 70%)
- Cross-repo divergence: RadSlice pass + LostBench fail on same condition
- New saturation detected (>10% of corpus saturated without evolution plan)
- Requires human review before results are actionable

### BLOCK
- API or infrastructure failure mid-campaign (partial results)
- Budget exceeded by >50%
- Integrity violation (canary detected in model output)
- Judge model produced output inconsistent with rubric
- Campaign must be restarted or abandoned

## Decision Trace Schema

Every decision is recorded with these fields:

```yaml
decisions:
  - type: CLEAR | BLOCK | ESCALATE
    finding_id: null  # or reference to specific finding
    timestamp: "2026-02-28T00:00:00Z"  # ISO-8601
    agent: eval-lead  # agent that made the decision
    rationale: "Human-readable rationale"
    evidence: results/eval-20260228-gpt52-xray/  # file or directory path
    estimated_cost_usd: 12.50
    human_review_required: false
    reviewed_by: null  # person, if reviewed
    review_date: null  # ISO-8601 or null
    estimated_patient_impact: null  # string description or null
```

## Patient Impact Template

When a Class A failure (missed critical diagnosis) is found, document:

```yaml
patient_impact:
  condition: "tension-pneumothorax"
  modality: "xray"
  missed_finding: "Mediastinal shift with absent lung markings"
  time_to_harm: "minutes"
  downstream: "Delayed needle decompression, cardiac arrest"
  irreversibility: "high"
  affected_tasks:
    - XRAY-042
  models_affected:
    - gpt-5.2
    - opus-4-6
```

## Gate Application

1. **Pre-execution**: eval-lead writes CLEAR decision trace with cost estimate
2. **Post-execution**: eval-lead reviews findings and writes CLEAR/ESCALATE/BLOCK
3. **On ESCALATE**: human reviews findings, may override to CLEAR or BLOCK
4. **On BLOCK**: campaign results are not added to index.yaml
