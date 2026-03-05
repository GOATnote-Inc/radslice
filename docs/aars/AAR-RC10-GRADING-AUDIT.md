# AAR: RadSlice rc1.0 Grading Audit

## Campaign ID
radslice-rc10-grading-audit

## Date Range
2026-03-03 to 2026-03-05

## Objective
Evaluate the measurement validity of the RadSlice rc1.0 evaluation (51 tasks x 2 models x 3 trials) by auditing every always-fail and always-pass grade for false negatives and false positives. Determine whether observed model performance differences (GPT-5.2 56.2% vs Opus 4.6 31.4%) reflect genuine capability gaps or grading pipeline artifacts.

## Experimental Setup
- **Evaluation:** rc1.0 — 51 tasks (14 X-ray, 12 CT, 15 US, 10 MRI) x 2 models (GPT-5.2, Opus 4.6) x 3 trials
- **Audit scope:** All always-fail grades (0/3 trials pass) and all always-pass grades (3/3 trials pass) for both models
- **Audit method:** Manual review of Layer 0 pattern matches, Layer 2 judge scores, model transcripts, and source images
- **Audit script:** `scripts/audit_rc10_grading.py` -> `results/rc10-grading-audit.json`

## Key Findings

1. **14 false negatives identified.** Of the 14, 6 are IMAGE_MISMATCH (source image does not contain the target pathology), 5 are AMBIGUOUS (image interpretation is genuinely unclear), and 3 are GENUINE (model clearly fails on unambiguous pathology). The 6 IMAGE_MISMATCH tasks inflate failure rates by ~12% of the denominator.

2. **13 false positives identified.** 11 are VALID (model response is clinically acceptable despite not matching exact ground truth patterns), 2 are RUBRIC_EASY (passing threshold too low). False positives are less concerning than false negatives for safety evaluation but still distort pass rates.

3. **Layer 0 decides 100% of GPT always-fail grades.** All 42 GPT always-fail observations were decided by deterministic regex pattern matching alone (Layer 0). The LLM judge (Layer 2) was never consulted. This means GPT's failure profile is entirely determined by pattern coverage — genuine capability gaps may be masked by pattern misses.

4. **6 IMAGE_MISMATCH tasks must be excluded from clinical risk assessment.** CT-027, CT-048, CT-097, MRI-007, MRI-031, MRI-035 fail because source images lack target pathology. These are data quality issues, not model capability failures. Corrected denominator: 45 tasks (not 51).

5. **Opus dominates the risk debt register.** Of 28 risk debt entries derived from this audit, 16 are Opus-only failures, 5 are GPT-only, and 7 affect both models. This asymmetry is consistent with LostBench findings where GPT-5.2 consistently outperforms Opus on safety-critical tasks.

6. **CT is the weakest modality for both models.** GPT 30.6%, Opus 8.3% on CT tasks. This is driven by complex anatomy (deep neck space, orbital compartment) and imaging ambiguity (soft tissue windows). CT tasks should be prioritized for image re-sourcing and pattern refinement.

## Root Causes

**RC-1: Image sourcing quality.** 6 of 51 tasks (12%) have source images that do not contain the target pathology. These were sourced from public datasets (NCI IDC, MultiCaRe) where image-condition alignment was assumed from metadata but not radiologist-verified.

**RC-2: Layer 0 pattern over-reliance.** Layer 0 regex patterns are designed as high-precision pre-filters, but when they reach a confident match, they short-circuit the LLM judge entirely. For GPT's always-fail cases, this means the judge never sees the response — pattern gaps become invisible capability gaps.

**RC-3: Ambiguous imaging.** 5 of 14 FN are genuinely ambiguous — reasonable radiologists would disagree on the diagnosis from the image alone. These represent a measurement floor for any automated evaluation system using static images.

## Corrective Actions

| Action | Status | Owner |
|--------|--------|-------|
| Re-source 6 IMAGE_MISMATCH images from NCI IDC / MultiCaRe | Open | eval-lead |
| Lower Layer 0 confidence threshold to force Layer 2 consultation on borderline matches | Open | eval-lead |
| Tighten 2 overly permissive patterns (RUBRIC_EASY false positives) | Open | eval-lead |
| Radiologist review of 5 AMBIGUOUS cases for ground truth adjudication | Open | eval-lead |
| Populate risk_debt.yaml with 28 entries from audit findings | Complete | eval-lead |
| Exclude IMAGE_MISMATCH tasks from all downstream analysis | Complete | eval-lead |

## Lessons Learned

1. **Image-condition alignment must be radiologist-verified.** Public dataset metadata is insufficient for ground truth. Every image used in evaluation must have at least one verification that the target pathology is visible and unambiguous.

2. **Layer 0 short-circuiting masks capability.** When deterministic patterns confidently decide a grade, the LLM judge never runs. This is efficient but creates a blind spot — the pattern engine becomes the bottleneck for measurement validity, not the judge. Future versions should run both layers and flag discordance.

3. **Measurement validity audits must precede clinical risk assessment.** The risk debt register (28 entries) was populated only after excluding IMAGE_MISMATCH and classifying AMBIGUOUS cases. Without this audit, 6 entries would have been spurious.

4. **CT requires dedicated attention.** CT tasks involve complex 3D anatomy projected onto 2D slices, windowing sensitivity, and anatomic ambiguity. Pass rates (GPT 30.6%, Opus 8.3%) are far below other modalities. Image sourcing, pattern coverage, and ground truth for CT should be prioritized in the next evaluation cycle.

5. **Cross-model asymmetry analysis is essential.** The 19 GPT-only vs 3 Opus-only pass pattern reveals systematic capability differences, not random variation. Asymmetric failures should drive risk debt prioritization and corrective image sourcing.
