# RadSlice — Multimodal Radiology LLM Evaluation Benchmark

**Document Type:** Technical Specification
**Document ID:** RADSLICE-TSD-001
**Maintained by:** GOATnote Inc.
**Responsible Engineer:** B, M.D. — Chief Engineer, GOATnote Inc.
**Repository:** [github.com/GOATnote-Inc/radslice](https://github.com/GOATnote-Inc/radslice)
**License:** Apache 2.0

| Revision | Date | Author | Description |
|----------|------|--------|-------------|
| 0.1.0 | 2026-02-27 | GOATnote | Initial framework implementation: task schema, grading pipeline, CLI |
| 0.2.0 | 2026-02-28 | GOATnote | Recursive self-improvement architecture: saturation detection, governance |
| 0.3.0 | 2026-02-28 | GOATnote | DICOM-native image pipeline, corpus provenance mapping, smoke test config |
| 1.0.0-rc | Pending | — | First end-to-end evaluation run with image-backed tasks |

---

## 1.0 Regulatory Scope Statement

### 1.1 Purpose

RadSlice is an evaluation benchmark for assessing the diagnostic image interpretation capabilities of frontier vision-language models (VLMs) across four radiological modalities: X-ray, computed tomography (CT), magnetic resonance imaging (MRI), and ultrasound (US). It measures whether commercially deployed or research-stage AI systems can correctly identify clinically significant findings, assign appropriate diagnoses, localize pathology, and avoid hallucinated findings when presented with real medical images.

### 1.2 Intended Regulatory Context

RadSlice is designed to support the following regulatory and policy workflows:

- **Pre-deployment safety evaluation** of AI/ML systems that interpret medical images, as referenced in the FDA's January 2025 draft guidance "Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations" and the IMDRF's 10 Guiding Principles for Good Machine Learning Practice (GMLP), finalized January 2025.
- **Post-market performance monitoring** of AI/ML-based SaMD, consistent with the FDA's Total Product Lifecycle (TPLC) approach and Predetermined Change Control Plan (PCCP) framework (final guidance, December 2024).
- **High-risk AI system evaluation** under the EU AI Act (Regulation 2024/1689), where AI systems used in emergency healthcare patient triage and medical device diagnostics are classified as high-risk under Annex III, Section 5(d) and Article 6(1) respectively. EU AI Act high-risk obligations for Annex III systems apply from August 2, 2026, with Annex I (medical device) systems following by August 2, 2027 (subject to Digital Omnibus revision extending to December 2, 2027).
- **Congressional and governmental policy review** of AI safety in healthcare, providing empirical evidence of model-specific performance patterns and failure modes.

### 1.3 Classification

RadSlice is an **evaluation tool**. It is not a medical device, does not perform clinical diagnosis, and does not constitute clinical validation of any model for deployment. Its outputs are evaluation metrics that inform safety assessments conducted by qualified parties. RadSlice does not meet the definition of Software as a Medical Device (SaMD) under the FDA's SaMD framework or the IMDRF SaMD definition (N12), as it does not provide information used to make clinical decisions about individual patients.

### 1.4 Applicable Standards and Guidance

| Standard / Guidance | Relevance to RadSlice |
|---|---|
| FDA Draft Guidance: AI-Enabled Device Software Functions (Jan 2025) | Evaluation data structure, TPLC documentation |
| FDA Final Guidance: PCCP for AI-Enabled DSFs (Dec 2024) | Benchmark versioning and change control methodology |
| IMDRF GMLP Guiding Principles (Jan 2025) | Representative data, bias evaluation, performance monitoring |
| EU AI Act Annex III Section 5(d), Art. 6(1) | High-risk classification criteria for healthcare AI |
| EU AI Act Annex IV | Technical documentation requirements for high-risk AI |
| ISO 13485:2016 Section 7.3 | Design verification and validation documentation model |
| IEC 62304:2006+A1:2015 | Software lifecycle processes for medical device software |
| DICOM PS3.15 Annex E | Attribute Confidentiality Profiles for image de-identification |
| HIPAA Privacy Rule Section 164.514(b)(2) | Safe Harbor de-identification standard |

---

## 2.0 Benchmark Architecture

### 2.1 Task Specification

RadSlice defines 320 evaluation tasks spanning 133 unique clinical conditions from the OpenEM emergency medicine corpus. Each task specifies a clinical condition, imaging modality, ground truth diagnosis, expected radiological findings, and grading criteria. Tasks are organized by modality:

| Modality | Tasks | Unique Conditions | Difficulty Distribution |
|---|---|---|---|
| X-ray | 72 | 72 | 8 basic / 20 intermediate / 39 advanced / 5 expert |
| CT | 106 | 106 | 3 basic / 28 intermediate / 64 advanced / 11 expert |
| MRI | 53 | 53 | 1 basic / 6 intermediate / 40 advanced / 6 expert |
| Ultrasound | 89 | 89 | 9 basic / 31 intermediate / 30 advanced / 19 expert |
| **Total** | **320** | **133 unique** | 21 basic / 85 intermediate / 175 advanced / 39 expert |

65 tasks include cross-references to LostBench safety persistence scenarios (e.g., `MTR-016`), enabling cross-benchmark analysis of whether models that correctly identify emergency findings on imaging also maintain those recommendations under conversational pressure.

### 2.2 Image Pipeline

RadSlice implements a DICOM-native image pipeline (`src/radslice/dicom.py`) that preserves clinical correctness through the full processing chain:

- **DICOM loading** via pydicom with RescaleSlope/RescaleIntercept application for Hounsfield Unit conversion
- **Clinically validated window presets** (CT soft tissue, lung, bone, brain, liver, abdomen) with fallback to DICOM-embedded Window Center/Width tags, then histogram-based auto-windowing
- **Photometric interpretation handling** including MONOCHROME1 inversion (where high pixel values represent dark regions)
- **Multi-frame DICOM support** for cine ultrasound and cardiac imaging
- **Format detection** via DICOM magic bytes at offset 128, with transparent routing between DICOM and raster (PNG/JPEG) paths

### 2.3 Grading Pipeline

Three-layer grading with documented determinism properties:

| Layer | Method | Deterministic | API Dependency | Implementation |
|---|---|---|---|---|
| Layer 0 | Regex pattern matching for required findings, laterality, diagnosis | Yes — fully reproducible | None | `src/radslice/grading/patterns.py` |
| Layer 2 | Cross-vendor LLM radiologist judge (5-dimension rubric) | No — subject to model versioning, temperature, non-deterministic sampling | External LLM API | `src/radslice/grading/judge.py` |

**Scoring dimensions** (Layer 2):

| Dimension | Weight | Measures |
|---|---|---|
| Diagnostic accuracy | 0.35 | Correct primary diagnosis and differentials |
| Finding detection | 0.25 | Identification of required and optional findings |
| Anatomic precision | 0.15 | Correct localization and laterality |
| Clinical relevance | 0.15 | Appropriate urgency assessment and follow-up |
| False positive control | 0.10 | Absence of hallucinated findings |

**Inter-rater reliability:** Physician-adjudicated calibration methodology achieving Cohen's kappa = 1.000 on calibration set, validated across the GOATnote evaluation program (LostBench, OpenEM).

**Metrics:** pass@k (probability at least 1 of k trials passes), pass^k (probability all k trials pass — deployment safety gate), Wilson confidence intervals on all proportions, 10,000-sample bootstrap CI for composite scores, two-proportion z-test for regression detection between runs.

---

## 3.0 Corpus Provenance and Data Sourcing

### 3.1 Sourcing Principles

All corpus images are sourced from established, peer-reviewed, government-funded or institutionally maintained medical imaging repositories. No images are scraped from the open web, generated synthetically, or sourced from non-standard channels. Every image source is documented with dataset identifier (DOI where available), license type, de-identification standard applied by the source, and access method.

### 3.2 Primary Open-Access Sources (No Registration Required)

| Source | Modalities | Format | License | De-identification Standard | Access Method |
|---|---|---|---|---|---|
| NCI Imaging Data Commons (IDC) | CT, MRI, X-ray, PET | DICOM | CC-BY (95%+ of collections) | TCIA pipeline: DICOM PS3.15 Annex E, HIPAA Safe Harbor Section 164.514(b)(2) | Google Cloud / AWS public buckets; Python API (`idc-index`) |
| TCIA (Cancer Imaging Archive) | CT, MRI, X-ray, US | DICOM | CC-BY / data citation required (per collection) | DICOM PS3.15 Annex E with TCIA Submission De-identification Process | REST API (NBIA Data Retriever); free public download |
| OsiriX DICOM Library | CT, MRI, cardiac, angio | DICOM (JPEG2000 transfer syntax) | Research/teaching use | Source-specific; pre-de-identified teaching cases | Direct HTTP download |
| MIMBCD-UI (UTA4/UTA7) | Ultrasound, MRI, mammography | DICOM | CC-BY-SA 4.0 | DICOM PS3.15 compliant | GitHub repositories |
| DICOM Library (.com) | Mixed community uploads | DICOM | Varies by upload | Contributor-managed | Direct download |

**NCI Imaging Data Commons** is the primary recommended source. It provides 85+ TB of harmonized DICOM data across all four RadSlice modalities under CC-BY licensing, accessible from public cloud buckets with zero registration, and queryable by modality and body part via the `idc-index` Python package. All IDC data passes through the TCIA de-identification pipeline, which implements the DICOM PS3.15 Attribute Confidentiality Profile aligned with HIPAA Safe Harbor.

### 3.3 Secondary Sources (Free Registration)

| Source | Content | Notes | Access |
|---|---|---|---|
| LIDC-IDRI (via TCIA) | 1,018 chest CTs + 290 CXRs; 4-radiologist annotations | Gold standard for lung CT evaluation | Free TCIA account |
| NLST | 26,254 low-dose chest CTs | CC-BY 4.0 | Free TCIA account |
| RSNA Intracranial Hemorrhage | 25,000+ annotated cranial CTs | From Kaggle RSNA challenge | Kaggle account |
| ChestX-ray14 (NIH) | 112,120 frontal CXRs; 14 disease labels | PNG format (not DICOM); massive scale | NIH download portal |
| FastMRI (Facebook AI/NYU) | Knee + brain MRI | Research data use agreement | NYU application |
| MMOTU | Ovarian ultrasound | Open access | Direct download |
| MITEA | 3D echocardiography; 134 subjects | GitHub | Direct download |

### 3.4 Credentialed Sources (Optional — Not Required for Core Evaluation)

| Source | Content | Credentialing | Notes |
|---|---|---|---|
| VinDr-CXR (PhysioNet) | 18,000 annotated CXRs; DICOM native | PhysioNet Credentialed Data Use Agreement | Enhances CXR coverage; not redistributable |
| MIMIC-CXR (PhysioNet) | 377,110 CXRs with radiology reports | PhysioNet CDUA + institutional IRB | Enables report-grounded evaluation |

### 3.5 Modality-Specific Sourcing Map

| Modality | RadSlice Conditions (examples) | Primary Source | Secondary Sources |
|---|---|---|---|
| X-ray | Acute heart failure, pneumonia, pneumothorax | IDC chest collections; LIDC-IDRI CXR subset | ChestX-ray14 (PNG); VinDr-CXR (credentialed) |
| CT | Pulmonary embolism, limb ischemia, intracranial hemorrhage | IDC; TCIA CTA collections; RSNA PE Detection (Kaggle CTPA) | LIDC-IDRI (lung CT); OsiriX cardiac/abdomen CTA |
| MRI | Aortic dissection, stroke, spinal cord compression | IDC thoracic MRI; OsiriX renal/cardiac MRA | FastMRI (knee/brain; DUA required) |
| Ultrasound | Echocardiography, ectopic pregnancy, AAA | MIMBCD-UI (breast US); MMOTU (ovarian US); MITEA (3D echo) | TCIA gynecologic and cardiac echo collections |

### 3.6 Corpus Completeness Status

| Component | Status | Detail |
|---|---|---|
| Task specifications (YAML) | 320/320 authored | All 133 OpenEM imaging-relevant conditions covered |
| Image-backed tasks (validated) | 7/320 (smoke test) | Smoke test covers 4 modalities; see `corpus/image_sources.yaml` |
| Full corpus target | 320 images | One validated image per task, sourced per Sections 3.2-3.4 |

**Image source mapping** is maintained in `corpus/image_sources.yaml`. Each entry includes: image path, source repository, source-specific identifier, SHA-256 checksum, original format, license identifier, and window preset (for DICOM CT).

---

## 4.0 Evaluation Integrity

### 4.1 Chain of Custody

Every evaluation run produces the following auditable record:

1. **Configuration:** Matrix YAML specifying models under test, trial count, concurrency, judge model, and grading parameters (`configs/matrices/`)
2. **Raw responses:** Per-task model outputs with timestamps, token counts, and API request metadata (`results/{run-id}/transcripts.jsonl`)
3. **Grading records:** Layer 0 pattern match results and Layer 2 judge scores with full rubric breakdowns (`results/{run-id}/grades.jsonl`)
4. **Aggregate metrics:** Per-modality, per-anatomy, per-difficulty breakdowns with confidence intervals (`results/{run-id}/analysis/`)
5. **Run index entry:** Appended to `results/index.yaml` with run ID, timestamp, corpus version hash, pipeline commit SHA, model identifiers, and configuration file reference

### 4.2 Reproducibility Requirements

A run is reproducible given:

- Corpus version hash (SHA-256 of `corpus/image_sources.yaml` + all image files)
- Pipeline commit SHA (git)
- Model identifier with version string (e.g., `claude-opus-4-6`, `gpt-5.2`)
- Configuration file (matrix YAML)
- Judge model identifier with version string

Layer 0 scores are fully deterministic and reproducible across environments. Layer 2 scores are subject to LLM non-determinism; reproducibility is bounded by the judge model's sampling variance. Bootstrap CI quantifies this variance.

### 4.3 Failure Classification

RadSlice uses a 4-class clinical severity taxonomy for grading failures, consistent with the GOATnote evaluation program:

| Class | Severity | Definition | Example |
|---|---|---|---|
| A | Critical | Missed life-threatening diagnosis or recommended dangerous action | Failed to identify tension pneumothorax; recommended discharge for STEMI |
| B | Major | Missed clinically significant finding that would change management | Failed to identify pulmonary embolism on CTPA |
| C | Moderate | Incomplete findings or imprecise localization that could delay care | Identified pneumonia but wrong lobe; missed associated effusion |
| D | Minor | Suboptimal but clinically acceptable response | Correct diagnosis with incomplete differential; missing severity grading |

---

## 5.0 Data Governance

### 5.1 Protected Health Information

No committed file in this repository contains Protected Health Information (PHI) as defined by the HIPAA Privacy Rule. All corpus images are sourced from repositories that have independently performed de-identification prior to public release:

- **TCIA and IDC collections** implement de-identification per DICOM PS3.15 Annex E (Attribute Confidentiality Profile) aligned with HIPAA Safe Harbor (Section 164.514(b)(2)), including removal of the 18 HIPAA-specified identifier categories, cleaning of burned-in pixel annotations, and replacement of DICOM UIDs.
- **MIMBCD-UI datasets** are de-identified per institutional protocols and released under CC-BY-SA 4.0.
- **OsiriX Library cases** are de-identified teaching cases curated for educational use.

### 5.2 Incidental PHI Discovery Policy

If any PHI is discovered in a committed file at any point:

1. The file is immediately removed from the repository and all branches
2. Git history is rewritten to expunge the file (`git filter-repo`)
3. The source dataset maintainers are notified
4. The incident is logged in `corpus/phi_incident_log.yaml` with date, file, discovery method, and remediation actions
5. The responsible party for this policy is the Chief Engineer of GOATnote Inc.

### 5.3 License Compliance

Each corpus image's license is recorded in `corpus/image_sources.yaml`. RadSlice complies with all source dataset licenses, including:

- **CC-BY:** Attribution provided in image source mapping and any published results
- **CC-BY-SA:** Derivative works (grading annotations) shared under same license
- **Data citation required:** Source dataset citations included in published results
- **Research/teaching only:** Images from restricted-license sources are not redistributed; users download directly from the source

### 5.4 Credentialed Data Handling

Datasets requiring credentialed access (PhysioNet VinDr-CXR, MIMIC-CXR) are never committed to this repository. The download pipeline (`corpus/download.py`) fetches these datasets to the user's local filesystem only after the user provides their own credentials. The `corpus/image_sources.yaml` mapping references these images by expected path and checksum without including the image data.

---

## 6.0 Known Challenges

### 6.1 Technical Challenges

| Challenge | Impact | Mitigation |
|---|---|---|
| Compressed transfer syntax DICOMs (JPEG Lossless, JPEG 2000) require codec libraries not included in base install | `RuntimeError` with install instructions at pixel decode time | `pip install radslice[dicom-codecs]` installs `pylibjpeg`, `pylibjpeg-libjpeg` (JPEG/JPEG-LS), and `pylibjpeg-openjpeg` (JPEG 2000); uncompressed DICOMs work without codecs |
| Multi-value WindowCenter/WindowWidth DICOM tags | pydicom returns `MultiValue` list; incorrect handling produces wrong windowing | Explicit `MultiValue` detection with first-value extraction in `dicom.py` |
| Layer 2 judge non-determinism | Score variance between identical runs | Bootstrap CI quantifies variance; Layer 0 provides deterministic lower bound |
| PhysioNet-credentialed datasets cannot be redistributed | Limits out-of-box reproducibility for VinDr-CXR / MIMIC-CXR tasks | All core tasks (320) sourceable from non-credentialed repositories; credentialed sources enhance but are not required |

### 6.2 Coverage Challenges

| Gap | Detail | Status |
|---|---|---|
| 52 of 185 OpenEM conditions lack imaging workup | Non-imaging conditions (e.g., anaphylaxis, DKA) excluded by design | By design — RadSlice evaluates imaging interpretation only |
| Pediatric imaging underrepresented in open-access sources | Most open DICOM repositories contain adult imaging | Actively sourcing pediatric collections from TCIA and IDC |
| 3D volumetric evaluation not yet implemented | Current pipeline evaluates single-slice or single-frame images | Planned for v2.0; architecture supports multi-frame DICOM |

---

## 7.0 Versioning and Audit Trail

### 7.1 Version Scheme

RadSlice maintains independent version tracking for three components:

| Component | Version Source | Current |
|---|---|---|
| Pipeline (code) | Git commit SHA + semantic version in `pyproject.toml` | 0.3.0 |
| Corpus (images + task specs) | SHA-256 hash of `corpus/image_sources.yaml` | Pre-release |
| Evaluation runs | Run ID (timestamp + model + config hash) in `results/index.yaml` | No completed runs |

### 7.2 Authoritative Records

- **Run history:** `results/index.yaml` — append-only log of all evaluation runs with full parameter capture
- **Audit log:** `results/audit_log.yaml` — records configuration changes, corpus updates, and grading pipeline modifications
- **Commit history:** Atomic commits preserving audit trail: (1) pipeline code + tests, (2) corpus sources + smoke results, (3) documentation updates. History is never squashed.

### 7.3 Review Cadence

This document is reviewed and updated upon each release that modifies the evaluation pipeline, corpus composition, or grading methodology. The revision history table at the top of this document serves as the authoritative change log.

---

## 8.0 Cross-Repository Context

RadSlice is part of the GOATnote Evaluation Program, a suite of benchmarks evaluating AI safety in healthcare:

| Repository | Purpose | Relationship to RadSlice |
|---|---|---|
| [LostBench](https://github.com/GOATnote-Inc/lostbench) | Multi-turn safety persistence benchmark | 65 RadSlice tasks cross-reference LostBench scenarios via `lostbench_scenario_id` |
| [ScribeGoat2](https://github.com/GOATnote-Inc/scribegoat2) | Multi-agent clinical triage research framework | Shares clinical condition taxonomy and grading methodology |
| [OpenEM](https://github.com/GOATnote-Inc/openem-corpus) | Emergency medicine knowledge base | RadSlice conditions derive from OpenEM's 185-condition corpus via `condition_id` |
| [SafeShift](https://github.com/GOATnote-Inc/safeshift) | Inference optimization safety benchmark | Evaluates whether quantization/batching degrades RadSlice task performance |

Architecture documentation: [CROSS_REPO_ARCHITECTURE.md](https://github.com/GOATnote-Inc/scribegoat2/blob/main/docs/CROSS_REPO_ARCHITECTURE.md)

---

## 9.0 Installation and Usage

### 9.1 Requirements

- Python 3.10+
- `pydicom >= 2.4` (DICOM loading)
- `numpy >= 1.24` (pixel array operations)
- `Pillow >= 10.0` (image encoding)
- API keys: `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` (for model evaluation and LLM judge)

### 9.2 Installation

```bash
pip install -e ".[dev]"
```

### 9.3 Corpus Validation

```bash
radslice corpus validate --tasks-dir configs/tasks
```

### 9.4 Running an Evaluation

```bash
# Source API keys
set -a && source .env && set +a

# Run evaluation matrix
radslice run --matrix configs/matrices/opus_smoke.yaml \
  --output-dir results/eval-YYYYMMDD-model-description/ \
  --cache --judge-model gpt-5.2

# Analyze results
radslice analyze --results results/eval-YYYYMMDD-model-description/ \
  --per-modality --per-anatomy
```

### 9.5 CLI Reference

| Command | Description |
|---|---|
| `radslice run` | Run evaluation matrix (tasks x models x trials) |
| `radslice grade` | Re-grade existing results with different judge/settings |
| `radslice analyze` | Per-modality, per-anatomy breakdowns with CI |
| `radslice report` | Generate comparison reports between runs |
| `radslice corpus validate` | Validate task YAMLs against schema |
| `radslice corpus download` | Fetch corpus images with checksum verification |

---

## 10.0 Project Layout

```
src/radslice/
  cli.py              CLI entry point
  task.py             Task dataclass and loader
  executor.py         Async matrix executor
  image.py            Image loading with DICOM/raster routing
  dicom.py            DICOM loading, windowing, metadata extraction
  scoring.py          pass@k, pass^k, Wilson CI, bootstrap
  analysis.py         Per-modality/anatomy breakdowns
  report.py           Report generation and comparison
  corpus/             Manifest, download, validation
  grading/
    patterns.py       Layer 0 deterministic checks
    judge.py          Layer 2 LLM radiologist judge
    rubric.py         Rubric definitions
  providers/
    base.py           Provider protocol
    openai.py         GPT-5.2
    anthropic.py      Opus/Sonnet 4.6
    google.py         Gemini 2.5 Pro
    cache.py          Disk-cached wrapper

configs/
  tasks/{xray,ct,mri,ultrasound}/   320 task YAMLs (OpenEM-grounded)
  models/                            Per-model configs
  matrices/                          Sweep configs
  rubrics/                           Grading rubric

corpus/
  image_sources.yaml                 Per-image provenance mapping
  download.py                        Per-source downloaders

tests/                               1,305+ tests (no API keys required)

results/
  index.yaml                         Run history
  audit_log.yaml                     Change audit trail
```

---

## 11.0 Test Suite

1,305+ automated tests covering framework plumbing, scoring mathematics, grading logic, task schema validation, DICOM loading, windowing, and image pipeline routing. All tests run without API keys or network access using synthetic DICOM fixtures.

```bash
make test        # Full suite
make lint        # ruff check + format
make smoke       # Smoke tests only
```

---

**License:** Apache 2.0

**Citation:** If using RadSlice in published work, cite this repository and the applicable source datasets per their respective license requirements.
