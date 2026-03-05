# rc1.1 Task Remediation Plan

**Date:** 2026-03-06
**Source:** Judge concordance analysis of 40 unsolved tasks from rc1.0 corrected evaluation
**Scope:** Image re-sourcing, near-threshold prompt engineering, suite membership updates

## Background

rc1.0 corrected evaluation (cross-vendor LLM judge regrade) identified 40/51 tasks unsolved by both GPT-5.2 and Opus 4.6. Concordance analysis categorizes these into three actionable tiers:

| Category | Count | Action |
|---|---|---|
| IMAGE_MISMATCH (data quality) | 6 | Re-source images before rc1.1 |
| Near-threshold (score 0.40-0.50) | 7 | Priority prompt engineering |
| Firmly unsolved (model failure) | 27 | Hold in capability suite, no task changes |

## 1. IMAGE_MISMATCH: Re-Source 6 Images

These tasks fail because the provided image does not match the task's clinical scenario. Both models and both judges agree on failure. The issue is data quality, not model capability.

### Tasks Requiring New Images

| Task | Condition | Current Source | Issue | Re-Source Strategy |
|---|---|---|---|---|
| CT-027 | Foreign body aspiration | `ct/openem/foreign-body-aspiration.png` | Image does not show intraluminal bronchial foreign body | NCI IDC: search pediatric chest CT with endobronchial lesion; MultiCaRe: PMC case reports of bronchial foreign body |
| CT-048 | Open fracture | `ct/openem/open-fracture.png` | Image does not clearly show soft tissue disruption communicating with fracture | MultiCaRe: PMC case reports of open tibial fracture with CT; RadImageNet: extremity CT with fracture |
| CT-097 | Acute angle-closure glaucoma | `ct/openem/acute-angle-closure-glaucoma.png` | Orbital CT does not show shallow anterior chamber vs contralateral eye | MultiCaRe: PMC case reports of CT showing shallow anterior chamber; Eurorad: orbital CT cases |
| MRI-007 | Cauda equina syndrome | `mri/openem/cauda-equina-syndrome.png` | MRI does not show large central disc extrusion compressing cauda equina | MultiCaRe: PMC case reports of lumbar MRI with CES; NCI IDC: lumbar spine MRI with disc herniation |
| MRI-031 | HSV encephalitis | `mri/openem/hsv-encephalitis.png` | Image does not show temporal lobe FLAIR hyperintensity pattern | MultiCaRe: PMC case reports of HSV encephalitis MRI; Eurorad: brain MRI with temporal lobe signal |
| MRI-035 | Spinal epidural abscess | `mri/openem/spinal-epidural-abscess.png` | MRI does not show rim-enhancing epidural collection | MultiCaRe: PMC case reports of spinal epidural abscess; Eurorad: thoracic spine MRI with epidural collection |

### Re-Sourcing Process

1. **Search primary sources** (NCI IDC, MultiCaRe) for CC-BY-4.0 images matching the ground truth
2. **Validate image-task alignment** before replacing: verify key findings are visible
3. **Update `image_ref`** in task YAML
4. **Update corpus manifest** with new source metadata and SHA-256 checksum
5. **Run single-task smoke test** against both models to confirm non-degenerate scores
6. **Do NOT modify pattern_checks or ground_truth** -- the task definitions are correct, only the images are wrong

### Acceptance Criteria

- All 6 tasks produce non-zero scores (>0.05) for at least one model on smoke test
- Image checksum matches manifest entry
- Source license is CC-BY-4.0 or more permissive
- Clinical radiologist confirms image matches ground truth key findings (optional but recommended)

## 2. Near-Threshold Tasks: Priority for Prompt Engineering

These 7 tasks have at least one trial scoring 0.40-0.50, meaning models are close to passing. Small prompt or pattern improvements may flip them.

| Task | Condition | Best GPT Score | Best Opus Score | Failure Class | Remediation |
|---|---|---|---|---|---|
| MRI-011 | Spinal cord compression | 0.53 | 0.03 | B (GPT), A/B (Opus) | GPT nearly passes -- review pattern_checks for over-strict matching; Opus has fundamental capability gap |
| MRI-014 | Fat embolism (cerebral) | 0.41 | 0.40 | A (both) | Both models close -- review if "starfield pattern" terminology in ground truth is too specific |
| US-019 | Hemorrhagic shock (FAST) | 0.44 | 0.68 | A (both) | Opus scores well but Class A override -- review if judge is requiring exact FAST protocol language |
| US-042 | Pyloric stenosis | 0.43 | 0.01 | C (GPT), B (Opus) | GPT nearly passes with Class C (minor detail wrong) -- review if anatomic precision weights penalize too heavily |
| US-046 | Obstructive urolithiasis | 0.51 | 0.51 | A (both) | Both at threshold but Class A override -- review if primary diagnosis criteria is too narrow |
| XRAY-027 | Tracheobronchial disruption | 0.15 | 0.42 | B (GPT), A (Opus) | Opus nearly passes -- review pattern overlap with pneumothorax |
| XRAY-068 | High-altitude illness | 0.18 | 0.42 | B (GPT), A/B (Opus) | Opus nearly passes -- review if HAPE vs HACE distinction is blocking pass |

### Prompt Engineering Actions

1. **Review Class A overrides on high-scoring trials** (US-019, US-046, MRI-014): When a model scores >0.50 on grading dimensions but gets Class A from the judge, check if the judge's failure classification is overly strict or if the model genuinely missed the primary diagnosis
2. **Audit pattern_checks for near-miss tasks**: MRI-011 (GPT 0.53), US-042 (GPT 0.43) -- check if regex patterns reject valid alternative phrasing
3. **Review grading dimension weights**: US-042 Class C suggests the model got the diagnosis right but lost points on precision -- check if the weight distribution is fair for that task type
4. **Do NOT lower the pass threshold** -- 0.50 is the minimum acceptable score. Instead, fix the task definitions or judge prompts if they're incorrectly penalizing correct answers

### Priority Order

1. US-019 and US-046 (both score >0.50 for Opus but fail on Class A -- highest ROI)
2. MRI-014 (both models score 0.40 -- most likely to flip for both)
3. MRI-011 (GPT already at 0.53 -- may flip with minor pattern fix)
4. US-042, XRAY-027, XRAY-068 (single-model near-misses)

## 3. Firmly Unsolved Tasks (27): No Task Changes

These 27 tasks score well below threshold (<0.40) for both models across all trials. They represent genuine model capability gaps. No task-level remediation is warranted.

### Action: Hold in capability suite

- These tasks remain in the **capability** suite for rc1.1
- They serve as the difficulty ceiling for current frontier models
- They should be the first tasks evaluated in rc1.1 to detect capability improvements
- 20 of 27 have risk debt entries (Class A failures) that remain open

### Modality Distribution (firmly unsolved)

| Modality | Count | Tasks |
|---|---|---|
| XRAY | 9 | XRAY-007, -017, -023, -024, -025, -031, -045, -052, -055 |
| US | 7 | US-006, -010, -034, -053, -073, -082 (excl. near-threshold) |
| CT | 7 | CT-026, -061, -068, -069, -070, -085, -091, -106 |
| MRI | 4 | MRI-003, -010, -040 (excl. near-threshold) |

## 4. Suite Membership Updates

### Summary of Changes

| Suite | Before | After | Delta |
|---|---|---|---|
| capability | 320 | 314 | -6 |
| blocked | 0 | 6 | +6 |
| regression | 0 | 0 | 0 |
| retired | 0 | 0 | 0 |

The 6 IMAGE_MISMATCH tasks move to a new **blocked** state (not retired -- they return to capability once images are re-sourced). No tasks are retired because no tasks are saturated (pass@5 > 0.95 for all models across 3+ runs).

## 5. rc1.1 Evaluation Plan

1. **Re-source 6 IMAGE_MISMATCH images** (prerequisite for rc1.1)
2. **Apply prompt engineering fixes** to 7 near-threshold tasks
3. **Run rc1.1 with judge enabled for both models** (corrective from calibration audit)
4. **Evaluate all 51 tasks from rc1.0** plus any new tasks from suite evolution
5. **Compare corrected rc1.1 vs corrected rc1.0** to measure improvement

## Appendix: Data Sources

- Judge concordance: `results/judge-concordance-unsolved.json`
- GPT regrade: `results/regrade-gpt52-rc10-20260306.json`
- Opus L0 regrade: `results/calibration-regrade-l0only-20260305.json`
- Corrected comparison: `results/rc10-corrected-comparison.json`
- Risk debt: `results/risk_debt.yaml`
- Grading audit AAR: `docs/aars/AAR-RC10-GRADING-AUDIT.md`
