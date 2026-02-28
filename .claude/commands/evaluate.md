# /evaluate [model] [modality]

Run a full evaluation campaign for a model on a modality (or all modalities).

## Usage

```
/evaluate <model> <modality>
```

- `model`: gpt-5.2, opus-4-6, sonnet-4-6, gemini-2.5-pro
- `modality`: xray, ct, mri, ultrasound, all (default: all)

## Team Structure

### 1. Eval Lead (orchestrator)
- **Agent definition:** eval-lead
- **Model:** opus
- **Tasks:** Scope campaign, estimate cost, write decision traces, synthesize report, govern
- **Active in:** Phase 1, Phase 4, Phase 5

### 2. Eval Operator (executor)
- **Agent definition:** eval-operator
- **Model:** sonnet
- **Tasks:** Execute `radslice run`, report raw metrics
- **Blocked until:** Phase 1 complete
- **Active in:** Phase 2

### 3. Radiology Analyst (clinical analysis)
- **Agent definition:** radiology-analyst
- **Model:** opus
- **Tasks:** Per-modality/anatomy breakdown, failure classification, Class A harm mapping
- **Blocked until:** Phase 2 complete
- **Active in:** Phase 3

### 4. Corpus Strategist (saturation)
- **Agent definition:** corpus-strategist
- **Model:** sonnet
- **Tasks:** Saturation detection, suite evolution proposals
- **Blocked until:** Phase 2 complete
- **Active in:** Phase 3

## Phases

### Phase 1: Scope (eval-lead)
1. Load `results/index.yaml` for prior campaign history
2. Load `results/suite_membership.yaml` for current suite composition
3. Compute cost estimate from `configs/model_pricing.yaml`
4. Write pre-execution decision trace
5. Hand off parameters to eval-operator

### Phase 2: Execute (eval-operator)
1. Run evaluation:
   ```bash
   radslice run --model MODEL --provider PROVIDER --model-id MODEL_ID \
     --n-trials 3 --output-dir results/eval-DATE-MODEL-MODALITY/ \
     --modality MODALITY --cache --judge-model JUDGE
   ```
2. Report: task count, pass rate, Class A count, output directory

### Phase 3: Analyze (parallel: radiology-analyst + corpus-strategist)
1. **radiology-analyst**: per-modality breakdown, Class A harm mapping
2. **corpus-strategist**: saturation check, suite update proposals

### Phase 4: Report (eval-lead)
1. Synthesize analysis into markdown summary
2. Highlight regressions, new Class A, saturation changes

### Phase 5: Govern (eval-lead)
1. Update `results/index.yaml`
2. Create risk debt for Class A failures
3. Apply/reject suite membership proposals
4. Write final decision trace (CLEAR / ESCALATE / BLOCK)

## Lead Behavior

Use **delegate mode**. eval-lead:
- Plans and authorizes (Phase 1)
- Delegates execution to eval-operator (Phase 2)
- Delegates analysis to radiology-analyst + corpus-strategist (Phase 3)
- Synthesizes and governs (Phase 4-5)
- Never executes `radslice run` directly

## Example Spawn

```
Create an agent team to evaluate GPT-5.2 on X-ray tasks.

Teammates:
- "operator" using eval-operator agent: Execute radslice run for gpt-5.2 on xray modality
- "analyst" using radiology-analyst agent: Analyze results, map Class A failures
- "strategist" using corpus-strategist agent: Check saturation, propose suite updates

Use delegate mode. I scope the campaign, authorize execution, synthesize analysis, and make governance decisions. I do not execute evaluations directly.
```

## After Completion

- [ ] Campaign entry written to `results/index.yaml`
- [ ] Risk debt entries created for any Class A failures
- [ ] Suite membership proposals reviewed (accepted/rejected)
- [ ] Final decision trace written (CLEAR/ESCALATE/BLOCK)
- [ ] Markdown summary available for human review
