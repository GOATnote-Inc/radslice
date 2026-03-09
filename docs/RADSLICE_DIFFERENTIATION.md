# RadSlice: Differentiation Brief

## What Existing Benchmarks Measure

Current radiology AI benchmarks optimize for one variable: **accuracy at scale**.

| Benchmark | Focus | Scale | Safety Analysis |
|-----------|-------|-------|----------------|
| CheXpert | Chest X-ray classification | 224,316 images | No |
| VinDr-CXR | Chest X-ray finding detection | 18,000 images | No |
| OmniMedVQA | Visual question answering | 127,995 QA pairs | No |
| RadBench | Multi-task radiology | 5 tasks/datasets | No |
| MIMIC-CXR | Report generation | 377,110 images | No |

These benchmarks answer: "How often is the model correct?" They do not answer: "When the model is wrong, how dangerous is the error?"

## What RadSlice Measures Differently

RadSlice measures **clinical safety failure modes** in emergency radiology — not accuracy.

### Harm-Weighted Failure Classification

Every failure is classified by clinical severity:

- **Class A** — Missed critical diagnosis (could directly cause patient death or irreversible harm)
- **Class B** — Significant diagnostic error (wrong diagnosis with clinical consequences)
- **Class C** — Partial interpretation (incomplete but not dangerous)
- **Class D** — Minor errors only

CheXpert tells you model accuracy is 87%. RadSlice tells you the Class A failure rate on hemorrhagic stroke is 100%, the time to hematoma expansion is < 1 hour, and both frontier models fail this condition.

### Time-to-Harm Weighting

Every task maps to an OpenEM condition with structured time-to-harm data. This transforms "the model misidentifies cardiac tamponade" into "the model misidentifies a condition where the patient dies in 15 minutes without intervention."

Of 41 unresolved safety findings:
- 20% involve conditions with < 1 hour to irreversible harm
- 39% involve conditions with < 6 hours
- 61% involve conditions with < 24 hours

### Cross-Modal Correlation with LostBench

No other radiology benchmark links imaging findings to text-based clinical reasoning evaluation on the same conditions. RadSlice cross-references 65 tasks to LostBench emergency scenarios, enabling classification:

- **Confirmed blind spots**: Model fails both image interpretation AND text reasoning on the same condition (fat embolism syndrome, hemorrhagic stroke)
- **Imaging-specific gaps**: Model reasons correctly in text but cannot interpret the image (acute ischemic stroke on DWI, testicular torsion on Doppler)

This distinction matters for model improvement: a confirmed blind spot requires training data, while an imaging-specific gap requires visual encoder improvements.

### Physician Adjudication Protocol

RadSlice implements a 4-tier physician adjudication framework with structured tooling, append-only records, and rubric governance. Existing benchmarks have ground truth; RadSlice has ground truth *plus* a systematic process for challenging, validating, and extending it.

## Concrete Example

> **CheXpert** reports that a model achieves 87% AUC on chest X-ray classification.
>
> **RadSlice** reports that GPT-5.2 has a 0% pass rate on fat embolism syndrome across both chest X-ray and brain MRI, time to irreversible injury < 24 hours with up to 36% mortality in the fulminant form, and the same failure pattern appears in LostBench text-based clinical reasoning evaluation — making this a confirmed cross-modal blind spot rather than a visual perception gap.
>
> One number tells you how often the model is right. The other tells you *exactly where the model is dangerous and why*.

## What This Enables

For **AI safety teams**: Targeted pre-deployment testing on the specific conditions and modalities where models fail most dangerously.

For **model developers**: Actionable failure taxonomy that distinguishes visual perception gaps (improve the encoder) from knowledge gaps (improve training data) from reasoning gaps (improve the reasoning pipeline).

For **clinical deployment**: Evidence-based exclusion criteria — conditions where AI-assisted interpretation should require mandatory human verification.

For **regulatory bodies**: A framework for evaluating radiology AI safety that goes beyond aggregate accuracy to condition-level, harm-weighted failure analysis.
