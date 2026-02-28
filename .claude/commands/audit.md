# /audit

Run a program self-audit: coverage, calibration, risk debt, saturation, governance.

## Usage

```
/audit
```

No arguments. Audits the full program state.

## Team Structure

### 1. Eval Lead (reviewer)
- **Agent definition:** eval-lead
- **Model:** opus
- **Tasks:** Review audit findings, plan next evaluation, write decision trace if needed
- **Active in:** Phase 2

### 2. Program Auditor (auditor)
- **Agent definition:** program-auditor
- **Model:** sonnet
- **Tasks:** Run all audit checks, write audit_log.yaml entry
- **Active in:** Phase 1

## Phases

### Phase 1: Audit (program-auditor)
1. **Coverage analysis**: Load all 320 task YAMLs, check which have results in recent campaigns
2. **Calibration drift**: Run `radslice calibration` on calibration set
3. **Risk debt review**: Load `results/risk_debt.yaml`, check open entries and age
4. **Saturation check**: Run `radslice saturation` across recent result directories
5. **Governance review**: Count campaigns since last audit, check ESCALATE traces
6. Write structured entry to `results/audit_log.yaml`

### Phase 2: Review (eval-lead)
1. Review audit findings
2. If critical findings: write decision trace (ESCALATE)
3. Plan next evaluation based on coverage gaps
4. Update risk debt if audit reveals new concerns

## After Completion

- [ ] Audit entry written to `results/audit_log.yaml`
- [ ] Critical findings flagged to eval-lead
- [ ] Next evaluation planned (if coverage gaps found)
- [ ] Decision trace written (if ESCALATE needed)
