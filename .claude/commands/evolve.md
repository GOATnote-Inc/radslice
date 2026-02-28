# /evolve [condition] [modality]

Generate harder task variants for a saturated condition/modality pair.

## Usage

```
/evolve <condition> <modality>
```

- `condition`: OpenEM condition ID (e.g., tension-pneumothorax)
- `modality`: xray, ct, mri, ultrasound

## Team Structure

### 1. Eval Lead (approver)
- **Agent definition:** eval-lead
- **Model:** opus
- **Tasks:** Approve generated tasks, update suite_membership.yaml, write decision trace
- **Active in:** Phase 4

### 2. Corpus Strategist (planner)
- **Agent definition:** corpus-strategist
- **Model:** sonnet
- **Tasks:** Analyze saturation, select variation dimensions, recommend variants
- **Active in:** Phase 1

### 3. Eval Operator (generator)
- **Agent definition:** eval-operator
- **Model:** sonnet
- **Tasks:** Execute task generation script
- **Blocked until:** Phase 1 complete
- **Active in:** Phase 2

### 4. Radiology Analyst (validator)
- **Agent definition:** radiology-analyst
- **Model:** opus
- **Tasks:** Validate generated tasks, check ground truth, verify difficulty escalation
- **Blocked until:** Phase 2 complete
- **Active in:** Phase 3

## Phases

### Phase 1: Strategize (corpus-strategist)
1. Check saturation status for target condition/modality
2. Analyze failure patterns from recent results
3. Select variation dimension(s):
   - `image_quality_degradation`
   - `sparse_clinical_history`
   - `differential_complexity`
   - `incidental_findings`
   - `laterality_traps`
   - `multi_system_pathology`
4. Recommend number of variants (default: 3)

### Phase 2: Generate (eval-operator)
1. Find source task for the condition/modality:
   ```bash
   grep -r "condition_id: CONDITION" configs/tasks/MODALITY/
   ```
2. Generate variants:
   ```bash
   python scripts/generate_tasks.py --source-task SOURCE_TASK \
     --variation VARIATION --output-dir configs/tasks/MODALITY/ \
     --n-variants 3
   ```
3. Report generated task IDs and paths

### Phase 3: Validate (radiology-analyst)
1. Load generated task YAMLs
2. Check ground truth completeness
3. Verify pattern coverage (>= 2 required patterns)
4. Confirm difficulty is escalated from parent
5. Validate condition_id references valid OpenEM condition

### Phase 4: Approve (eval-lead)
1. Review generated tasks and validation report
2. Accept or reject each task
3. If accepted: update `results/suite_membership.yaml`
4. Write decision trace

## After Completion

- [ ] New task YAMLs in `configs/tasks/<modality>/`
- [ ] Tasks added to capability suite in `suite_membership.yaml`
- [ ] Decision trace written
- [ ] Parent task flagged for potential retirement
