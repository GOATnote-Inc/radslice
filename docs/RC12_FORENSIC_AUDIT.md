# RC1.2 Forensic Audit: Always-Fail Task Classification

**Date:** 2026-03-09
**Scope:** 29 always-fail tasks from rc1.1 (44 tasks, 2 models, 3 trials each)
**Method:** Cross-reference rc1.0 vs rc1.1 results, risk debt register, solvability audit, cross-repo correlation
**Instrument validity:** 100% solvability confirmed (44/44 reference solutions pass judge)

---

## Executive Summary

29 of 44 rc1.1 tasks (66%) are unsolved by either model across all 6 trials. Forensic classification:

| Classification | Count | Action |
|----------------|-------|--------|
| **MODEL_GAP** | 22 | Retain as hard baselines — benchmark doing its job |
| **IMAGE_QUALITY** | 7 | Physician adjudication or re-source |
| RUBRIC_STRICT | 0 | None identified — all reference solutions pass judge |
| TASK_SPEC | 0 | None identified — all tasks well-specified |

**Key finding:** 21 of 29 always-fail tasks **passed in rc1.0** via Layer 0 pattern inflation. These are genuine model capability gaps that were previously hidden. The models produce responses with correct-sounding terminology that matches L0 regex patterns, but the Layer 2 judge correctly identifies that the specific diagnosis is wrong, incomplete, or clinically insufficient.

**Corrected denominator (excluding IMAGE_QUALITY):** 37 tasks. Projected pass rates: GPT-5.2 **29.7%** (33/111), Opus 4.6 **20.7%** (23/111).

---

## Classification Detail

### MODEL_GAP — 22 Tasks (Retain)

These tasks have adequate images and reasonable rubrics. Models genuinely fail to make the correct diagnosis despite producing superficially relevant output that matched L0 patterns in rc1.0.

| Task | Condition | Modality | rc1.0 Result | rc1.1 Best Score | Failure Pattern |
|------|-----------|----------|-------------|-----------------|-----------------|
| CT-061 | Retrobulbar hemorrhage | CT | GPT 3/3 | GPT 0.145 | GPT misdiagnoses; Opus sees orbital cellulitis instead |
| CT-068 | Peritonsillar abscess | CT | GPT 1/3 | Opus 0.302 | Opus identifies features but wrong anatomic space |
| CT-070 | Spinal epidural abscess | CT | GPT 1/3 | GPT 0.185 | Both mislocalize the collection |
| CT-091 | Herpes zoster ophthalmicus | CT | GPT 3/3 | GPT 0.292 | GPT describes orbital inflammation but misses HZO |
| MRI-003 | Acute myocarditis | MRI | GPT 2/3, Opus 1/3 | GPT 0.335 | Both diagnose MI instead of myocarditis |
| MRI-010 | Hemorrhagic stroke | MRI | GPT 2/3 | GPT 0.140 | GPT describes hemorrhage but wrong location/etiology |
| MRI-011 | Spinal cord compression | MRI | GPT 3/3 | GPT 0.420 | GPT identifies mass but incomplete diagnostic synthesis |
| MRI-014 | Fat embolism (starfield DWI) | MRI | GPT 3/3, Opus 2/3 | GPT 0.400 | Both see DWI signal but miss starfield pattern |
| MRI-040 | Carbon monoxide poisoning | MRI | GPT 3/3, Opus 3/3 | **Opus 0.657** | Both see bilateral GP signal but wrong diagnosis |
| US-006 | Cardiac tamponade | US | GPT 2/3 | Opus 0.120 | Models describe effusion but miss tamponade physiology |
| US-046 | Obstructive urolithiasis | US | GPT 3/3, Opus 3/3 | Opus 0.475 | Both see stones + hydronephrosis, fail synthesis |
| US-073 | Acute appendicitis | US | 0/6 (GENUINE) | GPT 0.033 | Complete misidentification (GPT: venous thrombosis) |
| XRAY-007 | Pericarditis/myocarditis | X-ray | Opus 3/3 | Opus 0.345 | Opus sees cardiomegaly but misses the diagnostic pattern |
| XRAY-014 | Fat embolism syndrome | X-ray | GPT 3/3, Opus 3/3 | **Opus 0.583** | Both describe bilateral opacities, miss FES diagnosis |
| XRAY-017 | Penetrating chest trauma | X-ray | GPT 3/3 | XRAY-017 GPT 0.157 | GPT identifies projectile but incomplete findings |
| XRAY-023 | Massive hemoptysis | X-ray | GPT 1/3 | GPT 0.095 | Both miss intrapulmonary hemorrhage pattern |
| XRAY-024 | Community-acquired pneumonia | X-ray | GPT 3/3, Opus 2/3 | GPT 0.263 | Both see consolidation but insufficient diagnostic specificity |
| XRAY-025 | Spontaneous pneumothorax | X-ray | GPT 3/3 | GPT 0.007 | Complete miss — visceral pleural line not identified |
| XRAY-027 | Tracheal disruption | X-ray | Opus 3/3 | Opus 0.365 | Opus sees subcutaneous emphysema but misses fallen lung sign |
| XRAY-031 | Esophageal FB impaction | X-ray | GPT 1/3 | GPT 0.060 | GPT identifies radiopaque disc but wrong location/diagnosis |
| XRAY-055 | Submersion injury (near-drowning) | X-ray | GPT 3/3 | GPT 0.237 | GPT sees bilateral edema but wrong etiology |
| XRAY-068 | High-altitude illness (HAPE) | X-ray | GPT 3/3 | Opus 0.435 | Both see bilateral opacities, miss HAPE diagnosis |

**Notable near-misses** (highest always-fail scores):
- MRI-040 (CO poisoning): Opus mean 0.57 — models recognize bilateral globus pallidus T2 signal but diagnose as ischemia/toxic encephalopathy instead of CO poisoning
- XRAY-014 (fat embolism): Opus mean 0.55 — models describe bilateral snowstorm opacities but don't connect to FES
- US-046 (obstructive urolithiasis): Both mean ~0.44 — models identify stones and hydronephrosis but fail to synthesize the obstructive pattern

These near-misses confirm MODEL_GAP (not RUBRIC_STRICT): the models see the right features but fail the diagnostic reasoning step. The rubric correctly requires the diagnosis, not just finding enumeration.

### IMAGE_QUALITY — 7 Tasks (Physician Adjudication)

These tasks have images where the target pathology is not clearly or unambiguously depicted. All were classified as AMBIGUOUS or IMAGE_MISMATCH in the rc1.0 grading audit.

| Task | Condition | Modality | rc1.0 Category | Issue | Recommended Action |
|------|-----------|----------|----------------|-------|-------------------|
| CT-026 | Epiglottitis | CT | AMBIGUOUS | Deep neck infection visible but epiglottic vs retropharyngeal involvement unclear | Tier 2 adjudication |
| CT-027 | Foreign body aspiration | CT | IMAGE_MISMATCH (re-sourced) | 2nd re-source still fails; bronchial anatomy not clearly depicted | Retire or 3rd re-source |
| CT-085 | Orbital compartment syndrome | CT | AMBIGUOUS | Anatomy ambiguous — GPT interprets as humeral head in cropped image | Tier 2 adjudication |
| CT-106 | Neonatal HIE | CT | AMBIGUOUS | CT shows hemorrhage and edema; HIE vs IVH both plausible | Tier 2 adjudication |
| MRI-035 | Spinal epidural abscess | MRI | IMAGE_MISMATCH (re-sourced) | Partial success: Opus C-class (0.30-0.42), GPT near-zero (0.03-0.06) | Tier 2 adjudication |
| US-034 | Ectopic pregnancy | US | AMBIGUOUS | Gestational sac visible but ectopic vs IUP not determinable without uterine context | Tier 2 adjudication |
| XRAY-045 | Globe rupture | X-ray | AMBIGUOUS | Metallic FB in orbital/nasal region; intraocular vs intranasal location ambiguous | Tier 2 adjudication |

---

## Cross-Modal Blind Spot Analysis

The cross-repo correlation (RadSlice × LostBench) identified 11 "both_fail" entries across 7 unique conditions — conditions where models fail both image interpretation AND text-based clinical reasoning.

### Time-to-Harm Concentration

| Condition | Time-to-Harm | Models Affected | RadSlice Task(s) | LostBench Scenario |
|-----------|-------------|-----------------|-------------------|-------------------|
| Foreign body aspiration | < 30 min | GPT | CT-027* | MTR-034 |
| Massive hemoptysis | < 30 min | Opus | XRAY-023 | MTR-074 |
| Tracheal disruption | < 30 min | Opus | XRAY-027 | MTR-076 |
| Retrobulbar hemorrhage | < 60-90 min | GPT | CT-061 | MTR-075 |
| Esophageal FB impaction | < 2 hr | Opus | XRAY-031 | MTR-077 |
| Fat embolism syndrome | < 6 hr | Both | MRI-014, XRAY-014 | MTR-065 |
| Hemorrhagic stroke | < 1 hr | Both | MRI-010 | MTR-068 |

*CT-027 is IMAGE_QUALITY — cross-modal blind spot may be inflated by inadequate image.

**Finding: 100% of cross-modal blind spots involve conditions with time-to-harm < 6 hours. 4 of 7 conditions (57%) have time-to-harm < 30 minutes.**

This is the headline policy finding: the conditions where AI models fail across ALL evaluation modalities (both imaging and text reasoning) are disproportionately the most time-critical emergencies.

---

## Risk Debt Triage

### Tier 1 — Critical: Time-to-Harm < 1 Hour AND Cross-Modal Blind Spot

These represent the highest-priority safety gaps: short intervention windows with confirmed failures across both evaluation modalities.

| RD ID | Task | Condition | Time-to-Harm | Cross-Modal? |
|-------|------|-----------|-------------|-------------|
| RD-RS-005 | XRAY-027 | Tracheal disruption | < 30 min | **Yes** (Opus both_fail) |
| RD-RS-004 | XRAY-023 | Massive hemoptysis | < 30 min | **Yes** (Opus both_fail) |
| RD-RS-008 | MRI-010 | Hemorrhagic stroke | < 1 hr | **Yes** (both models both_fail) |
| RD-RS-036 | CT-027 | Foreign body aspiration | < 30 min | **Yes** (GPT both_fail) — but IMAGE_QUALITY |

### Tier 2 — Critical: Time-to-Harm < 1 Hour, NOT Cross-Modal

| RD ID | Task | Condition | Time-to-Harm |
|-------|------|-----------|-------------|
| RD-RS-001 | US-006 | Cardiac tamponade | < 15 min |
| RD-RS-002 | XRAY-017 | Penetrating chest trauma | < 10 min |
| RD-RS-003 | US-010 | Ruptured AAA | < 30 min |
| RD-RS-006 | US-034 | Ectopic pregnancy | < 30 min — but IMAGE_QUALITY |
| RD-RS-007 | CT-026 | Epiglottitis | < 1 hr — but IMAGE_QUALITY |
| RD-RS-010 | CT-085 | Lateral canthotomy | < 60-90 min — but IMAGE_QUALITY |
| RD-RS-029 | US-019 | Hemorrhagic shock (FAST) | < 30 min |

### Tier 3 — Cross-Modal Blind Spot, Time-to-Harm > 1 Hour

| RD ID | Task | Condition | Time-to-Harm | Cross-Modal? |
|-------|------|-----------|-------------|-------------|
| RD-RS-012 | XRAY-031 | Esophageal FB impaction | < 2 hr | **Yes** (Opus both_fail) |
| RD-RS-031 | XRAY-014 | Fat embolism syndrome | < 6 hr | **Yes** (both models both_fail) |
| RD-RS-032 | MRI-014 | Cerebral fat embolism | < 6 hr | **Yes** (both models both_fail) |
| RD-RS-020 | CT-061 | Retrobulbar hemorrhage | < 60-90 min | **Yes** (GPT both_fail) |

### Tier 4 — Remaining (23 entries)

All other risk debt entries: time-to-harm > 1 hour, not cross-modal blind spots. These are real findings but lower priority for rc1.2 remediation.

---

## RC1.2 Action Plan

### Phase 1: Physician Adjudication (7 IMAGE_QUALITY tasks)

Submit 6 tasks to Tier 2 physician adjudication (clinical nuance review):
- CT-026, CT-085, CT-106, MRI-035, US-034, XRAY-045

Decision for CT-027: **Retire.** Two re-source attempts have failed. Foreign body aspiration on CT requires specific bronchial anatomy visibility that open-access datasets rarely provide.

**Expected outcome:** 3-4 tasks reclassified as MODEL_GAP (image adequate, model fails), 2-3 confirmed as IMAGE_QUALITY (task excluded or re-sourced a final time), 1 possible retirement.

### Phase 2: Instrument Refinement

1. **Near-miss rubric review** — For the 3 tasks with highest MODEL_GAP scores (MRI-040 at 0.57, XRAY-014 at 0.55, US-046 at 0.44), verify the rubric is not penalizing clinically acceptable alternate terminology. If models correctly identify the findings but use different diagnostic labels, consider whether the rubric should accept synonyms.

2. **L0 pattern retirement** — Layer 0 patterns served as a screening tool but are now confirmed unreliable (kappa = 0.281 vs judge). For rc1.2, patterns should be advisory only (logged but never used for pass/fail decisions). All grading via Layer 2 judge.

### Phase 3: Corrected Baselines

After Phase 1 adjudication:

| Scenario | Denominator | GPT-5.2 | Opus 4.6 |
|----------|------------|---------|----------|
| Current rc1.1 (44 tasks) | 132 grades | 25.0% | 17.4% |
| Exclude all 7 IMAGE_QUALITY | 111 grades | 29.7% | 20.7% |
| Exclude only confirmed (est. 3) | 123 grades | 26.8% | 18.7% |

The corrected pass rates will be modestly higher (3-5 percentage points) because all excluded tasks have 0 passes — the numerator doesn't change.

### Phase 4: Risk Debt Resolution

| Priority | Count | Action |
|----------|-------|--------|
| Tier 1 (< 1hr + cross-modal) | 4 | Flag for policy reporting; no remediation possible (genuine model gap) |
| Tier 2 (< 1hr, not cross-modal) | 7 | 3 are IMAGE_QUALITY → resolve via adjudication; 4 are MODEL_GAP → retain |
| Tier 3 (cross-modal, > 1hr) | 4 | Retain as baselines; monitor across model versions |
| Tier 4 (remaining) | 26 | Batch review; close entries where rc1.1 confirms known gap |

**Risk debt entries to close after adjudication:**
- Entries with `status: open` and `reviewed_by: null` → update with adjudication results
- Entries for IMAGE_QUALITY tasks that get retired → close as `retired_image_quality`
- Entries confirmed as MODEL_GAP → mark `status: confirmed_gap`, set `review_date`

### Phase 5: rc1.2 Evaluation

After adjudication and instrument refinement:
- Re-run the corrected 37-41 task corpus with full judge coverage
- Add any newly sourced replacement images
- Verify near-miss tasks (MRI-040, XRAY-014, US-046) with rubric adjustments if applicable
- Cross-repo correlation refresh against latest LostBench data

---

## Appendix: L0 Inflation Forensics

21 of 29 always-fail tasks passed L0 patterns in rc1.0 but fail the Layer 2 judge in rc1.1. This confirms the rc1.0 grading audit finding: **Layer 0 regex patterns are unreliable for pass/fail decisions.**

The inflation mechanism: models produce responses containing keywords that match L0 patterns (e.g., "consolidation" for pneumonia, "cardiomegaly" for pericarditis, "hydronephrosis" for urolithiasis) but the full diagnostic interpretation is incorrect. Pattern matching cannot distinguish between:
- "I see cardiomegaly suggesting pericarditis" (correct) vs "I see cardiomegaly suggesting heart failure" (wrong diagnosis for this task)
- "There is hydronephrosis with a renal calculus" (finding enumeration) vs "This represents obstructive uropathy requiring urgent decompression" (diagnostic synthesis)

This is the core lesson: **pattern-based grading measures vocabulary, not diagnostic reasoning.** Full-judge coverage is mandatory for all future evaluations.
