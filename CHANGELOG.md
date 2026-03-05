# Changelog

## [Unreleased]
- Add post-run judge coverage guardrail (exit code 2 on silent fallback)
- Fix context-aware L0 pattern matching to reduce false passes

## [rc1.0] - 2026-03-03
- Full 4-modality evaluation: 51 tasks x 2 models x 3 trials
- Published results: GPT-5.2 56.2%, Opus 4.6 31.4% (later corrected)
- Corrected pass rates: GPT 17.6%, Opus 13.7% (306 grades lacked judge)
- Grading audit: 14 FN, 13 FP identified
- rc1.1 remediation plan: 6 IMAGE_MISMATCH tasks blocked, 7 near-threshold flagged
- Risk debt register populated (28 entries)
- Calibration baseline established

## [rc0.5] - 2026-03-03
- Preliminary evaluation with pattern-only grading
- Corpus fixes: wrong-modality images, laterality mismatches

## [0.3.0] - 2026-02-28
- DICOM-native image pipeline with optional codec support
- Corpus provenance tracking and regulatory-grade README
- Agent teams: 5 agents, 3 commands (/evaluate, /evolve, /audit)
- Governance framework: decision gates, lifecycle, cadence

## [0.2.0] - 2026-02-26
- 330 tasks grounded in 133 OpenEM conditions
- Cross-repo correlation with LostBench (65 tasks)
- 3-layer grading: patterns, heuristics, LLM judge
- Incidental detection and report audit task types

## [0.1.0] - 2026-02-24
- Initial implementation: 200-task corpus across 4 modalities
- CLI: run, grade, analyze, report, corpus commands
- Providers: OpenAI, Anthropic, Google
