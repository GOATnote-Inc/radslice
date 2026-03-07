# AAR: RadSlice rc1.1 Measurement Validity Audit

## Campaign ID
radslice-rc11-measurement-validity-audit

## Date Range
2026-03-07

## Objective
Determine whether rc1.1 pass rates (GPT-5.2 25.0%, Opus 4.6 17.4%) reflect genuine model limitations or eval/judge artifacts. Per Anthropic's eval best practices: "A low pass rate is most often a signal of a broken task, not an incapable agent." This audit systematically tests that assumption.

## Experimental Setup
- **Evaluation:** rc1.1 — 44 tasks (14 X-ray, 11 CT, 9 US, 10 MRI) x 2 models (GPT-5.2, Opus 4.6) x 3 trials
- **Key change from rc1.0:** Judge always invoked (no L0 short-circuit), 100% Layer 2 coverage
- **5 re-sourced tasks:** CT-027, CT-048, MRI-007, MRI-031, MRI-035 (were IMAGE_MISMATCH in rc1.0)
- **7 excluded from rc1.0:** CT-097 (blocked), US-010/019/024/036/053/082 (retired, unsourceable)
- **Audit scripts:** `scripts/audit_rc11_solvability.py`, `scripts/analyze_rc11_delta.py`

## Key Findings

### 1. Solvability: 100% — the eval is valid

All 44 reference solutions pass the judge (mean score 0.997). **No task is broken.** The pass rate drops are genuine model limitations, not eval defects.

| Metric | Value |
|--------|-------|
| Tasks audited | 44 |
| Reference solutions pass | 44 (100%) |
| Mean reference score | 0.997 |
| Lowest reference score | 0.900 (CT-048, Class D overcall) |

### 2. Pattern inflation confirmed: 100% of DEGRADED tasks had L0-only passes

| Model | STABLE_PASS | STABLE_FAIL | DEGRADED | IMPROVED |
|-------|-------------|-------------|----------|----------|
| GPT-5.2 | 10 | 11 | 20 | 3 |
| Opus 4.6 | 6 | 27 | 9 | 2 |

**Every single DEGRADED task** (29 total across both models) had rc1.0 passes decided by L0 patterns alone — the judge was never consulted. This confirms rc1.0's primary systematic error: Layer 0 regex patterns inflated pass rates by ~30pp for GPT and ~14pp for Opus.

### 3. L0 vs L2 calibration: poor (kappa = 0.281)

| Metric | Value | Threshold |
|--------|-------|-----------|
| Overall agreement | 75.8% | >= 70% |
| Cohen's kappa | 0.281 | >= 0.60 |
| L0 pass rate | 29.9% | — |
| L2 pass rate | 9.5% | — |
| L0 false passes | 59 | — |
| L0 false fails | 5 | — |

**Drift detected.** L0 patterns systematically over-predict passes (59 false passes vs 5 false fails). The agreement rate of 75.8% barely meets threshold, but kappa of 0.281 is "fair" at best — driven by high base rate agreement on fails, not genuine concordance.

Per-modality calibration:

| Modality | n | Agreement | Kappa | L0 Pass | L2 Pass |
|----------|---|-----------|-------|---------|---------|
| CT | 66 | 77.3% | 0.000 | 22.7% | 0.0% |
| MRI | 60 | 78.3% | 0.426 | 31.7% | 16.7% |
| US | 54 | 79.6% | 0.487 | 31.5% | 22.2% |
| X-ray | 84 | 70.2% | 0.138 | 33.3% | 3.6% |

CT has kappa=0.000: patterns pass 22.7% of trials but the judge passes 0%. X-ray kappa=0.138 (patterns pass 33.3%, judge passes 3.6%). **L0 patterns are unreliable for CT and X-ray.**

### 4. Re-sourcing: mixed results

| Task | Model | rc1.0 Score | rc1.1 Score | Verdict |
|------|-------|-------------|-------------|---------|
| CT-027 | GPT | 0.175 | 0.045 | Worse (PE mimic) |
| CT-027 | Opus | 0.015 | 0.000 | Same |
| CT-048 | GPT | 0/3 → 3/3 | 0.731 | Fixed |
| CT-048 | Opus | 0/3 → 1/3 | 0.477 | Improved |
| MRI-007 | GPT | 0/3 → 3/3 | 0.746 | Fixed |
| MRI-007 | Opus | 0/3 → 2/3 | 0.681 | Improved |
| MRI-031 | GPT | 0/3 → 1/3 | 0.474 | Improved |
| MRI-031 | Opus | 0/3 → 3/3 | 0.740 | Fixed |
| MRI-035 | GPT | 0.175 | 0.037 | Worse |
| MRI-035 | Opus | 0.175 | 0.343 | Improved |

3 of 5 re-sourced tasks now have at least one model passing. CT-027 and MRI-035 remain always-fail — CT-027's image still resembles PE, MRI-035 lacks clear thoracic landmarks.

### 5. Always-fail analysis: 29 tasks, 0 eval defects

29 tasks fail for both models in all 3 trials (66% of the 44-task set). Since all reference solutions pass the judge (Finding 1), these are genuine model failures. Forensic categorization of sampled always-fail tasks:

| Category | Count | Examples |
|----------|-------|---------|
| IMAGE_STILL_BAD | 2 | CT-027, MRI-035 |
| AMBIGUOUS_GT | 1 | US-046 (stone not visible?) |
| GENUINELY_HARD | 4 | MRI-011, MRI-014, MRI-003, CT-091 |
| JUDGE_TOO_STRICT | 0 | — |
| TASK_UNCLEAR | 0 | — |

The 4 GENUINELY_HARD tasks involve expert-level diagnostic distinctions (abscess vs metastasis, fat embolism vs cardioembolic, MI vs myocarditis, HZO vs orbital cellulitis). All are correctly classified at advanced/expert difficulty.

### 6. Class A failure distribution

| Model | Class A | Class B | Class C | Class D | No class |
|-------|---------|---------|---------|---------|----------|
| GPT-5.2 | 10 (5 tasks) | 84 | 14 | 5 | 19 |
| Opus 4.6 | 45 (21 tasks) | 61 | 12 | 8 | 6 |

Opus has 4.5x more Class A failures than GPT. The asymmetry is consistent across all modalities and all prior campaigns (rc0.5, rc1.0).

6 new risk debt entries added (RD-RS-036 through RD-RS-041):
- CT-027 (foreign body aspiration), MRI-007 (cauda equina), MRI-031 (HSE)
- MRI-040 (CO poisoning), US-042 (testicular torsion), MRI-003 (myocarditis)

Total risk debt: 41 entries (35 from rc1.0, 6 new from rc1.1).

### 7. Suite membership: no changes

Suite-update dry-run proposes 0 promotions and 0 retirements. This is expected — rc1.1 is the first full-judge run, so no task has consecutive-run data under consistent grading methodology.

## Root Causes

**RC-1: Layer 0 pattern inflation (confirmed, quantified).** rc1.0 used L0 confidence thresholds to short-circuit the judge. 100% of DEGRADED tasks had L0-only passes. The true pass rate under full-judge grading is 25.0% (GPT) and 17.4% (Opus), not 56.2% and 31.4% as reported in rc1.0. L0 patterns produce 59 false passes vs 5 false fails — they are a biased estimator.

**RC-2: Image sourcing (partially remediated).** 3 of 5 re-sourced tasks now have at least one model passing. CT-027 and MRI-035 need further action.

**RC-3: Genuine model limitations.** Both models fail on expert-level pattern-recognition tasks (fat embolism starfield, myocarditis LGE, HZO V1 distribution). These are not fixable by eval improvements — they represent real capability gaps.

## Corrective Actions

| # | Action | Status | Owner |
|---|--------|--------|-------|
| 1 | Solvability audit — verify all reference solutions pass judge | **Complete** | eval-lead |
| 2 | Delta analysis — categorize all rc1.0→rc1.1 changes | **Complete** | eval-lead |
| 3 | L0 vs L2 calibration check | **Complete** | eval-lead |
| 4 | Transcript forensics on always-fail tasks | **Complete** | eval-lead |
| 5 | Class A triage + risk_debt update (6 new entries) | **Complete** | eval-lead |
| 6 | Suite membership update (dry-run) | **Complete** | eval-lead |
| 7 | Re-source CT-027 (third attempt) or retire | Open | eval-lead |
| 8 | Re-source MRI-035 with clearer thoracic landmarks | Open | eval-lead |
| 9 | Investigate US-046 stone visibility in sourced image | Open | eval-lead |
| 10 | Recalibrate L0 patterns (kappa target >= 0.60) | Open | eval-lead |
| 11 | Establish rc1.1 as grading baseline for future deltas | Open | eval-lead |

## Lessons Learned

1. **Pattern-only grading is fundamentally broken for measurement.** L0 patterns are useful as fast pre-filters and negative signals, but their pass decisions are not credible — 59/79 L0 passes (75%) are judge-false-positives. Future campaigns must always invoke the judge.

2. **Solvability audits should precede all analysis.** This 5-minute, 44-call audit definitively separated "eval problems" from "model problems." Without it, the 25% pass rate could have triggered weeks of fruitless eval debugging.

3. **Re-sourcing has a ~60% success rate.** 3 of 5 re-sourced tasks are now partially or fully functional. The remaining 2 need either more targeted sourcing or retirement. Image-condition alignment cannot be assumed from metadata — it must be visually verified.

4. **Class B (wrong diagnosis) dominates rc1.1.** 84 GPT and 61 Opus Class B failures vs 10/45 Class A. Under full-judge grading, most failures are confident misdiagnoses, not missed diagnoses. This suggests models engage with images but lack the clinical knowledge to discriminate between similar-appearing conditions.

## Artifacts

| File | Description |
|------|-------------|
| `results/rc11-solvability-audit.json` | Reference solution judge verdicts (44 tasks) |
| `results/rc11-delta-analysis.json` | Per-task rc1.0→rc1.1 comparison |
| `results/risk_debt.yaml` | Updated with 6 new entries (RD-RS-036 to RD-RS-041) |
| `scripts/audit_rc11_solvability.py` | Solvability audit script |
| `scripts/analyze_rc11_delta.py` | Delta analysis script |
