# RadSlice v2: Agentic Radiology Benchmark

**RADSLICE-ARC-002 | Architecture Specification**
**Status:** Draft | **Date:** 2026-03-03

---

## 1. Thesis

Single-image radiology interpretation is a solved problem *statement* — the answer
is "models can't do it." Hong et al. 2026 ("Chatting Ain't Diagnosing") confirmed
a 20% fundamental error rate across all frontier models on a single head CT, with
clinically meaningful variability even among concordant models. RadSlice rc0.5
independently confirms this: 0% judge-only pass rate for both GPT-5.2 and Opus 4.6
across 26 pathology-validated tasks.

This is the HumanEval moment for radiology. Models were terrible at coding in 2022.
Nobody benchmarks coding with multiple-choice questions anymore — they use SWE-bench,
which tests whether agents can navigate real repositories, use tools, and produce
working patches. RadSlice v2 makes the same leap: from "can a model describe a
picture" to "can an agentic system perform the radiologist workflow."

A radiologist doesn't look at one picture. They scroll through 300 CT slices, adjust
window/level for different tissues, switch between series (axial/coronal/sagittal,
with and without contrast), measure lesions, compare with priors. It's an agentic
workflow — tool orchestration over a volume, not pattern recognition on a single
image.

### Structural Parallels

| Dimension | SWE-bench | EnterpriseBench | RadSlice v2 |
|-----------|-----------|-----------------|-------------|
| **Unit of work** | GitHub issue in a real repo | Business task in a simulated startup | Imaging study with real DICOM |
| **Tool interface** | Shell, editor, git, tests | CRM, email, spreadsheets, databases | DICOM navigator, windowing, measurement |
| **What fails** | Navigation, context management, tool use | Search strategy, tool orchestration, grounding | Series selection, windowing, systematic coverage |
| **Grading** | Execution-based (tests pass) | Rubric-based (binary factual checks) | Rubric-based (factual + workflow + tool-use) |
| **Baseline** | ~2% (2023) → ~50% (2025) | ~31% (Opus 4.6, 2026) | 0% (rc0.5, 2026) — tracking from floor |
| **Insight** | Coding is tool use, not syntax recall | Enterprise work is tool orchestration | Radiology is navigation + windowing + reasoning |

### The Progression

```
Coding                           Radiology (RadSlice)
─────────────────────────────    ─────────────────────────────────
HumanEval (multiple choice)      rc0.5: single image, free-text → 0%
SWE-bench (real repos, tools)    rc1+: DICOM volumes, nav tools, structured output
Devin/Claude Code (workflow)     Full study: series selection, priors, reporting
```

---

## 2. DICOM Tool Interface

The tool schema defines how agents interact with imaging studies. Designed for
MCP compatibility — each tool is a discrete function call with typed parameters
and structured returns.

### 2.1 Tool Definitions

```yaml
tools:
  navigate_study:
    description: >
      List all available series in the current imaging study.
      Returns metadata for each series including modality, description,
      slice count, and spatial parameters.
    params: {}
    returns:
      type: array
      items:
        series_id: string        # SeriesInstanceUID (truncated for readability)
        description: string      # SeriesDescription DICOM tag
        modality: string         # CT, MR, US, DX, CR
        slice_count: integer     # Number of instances in series
        body_part: string        # BodyPartExamined
        contrast: boolean        # Inferred from SeriesDescription
        plane: string            # axial | coronal | sagittal | oblique | 3d
        slice_thickness_mm: float

  get_slice:
    description: >
      Retrieve a single slice from a series, rendered at the current
      window/level settings. Slice can be specified by number or
      anatomical landmark.
    params:
      series_id: string          # Required
      slice_number: integer      # 0-indexed, OR:
      landmark: string           # e.g. "carina", "L4-L5", "circle_of_willis"
    returns:
      image: base64_png          # Rendered at current window/level
      metadata:
        slice_location_mm: float
        instance_number: integer
        pixel_spacing_mm: [float, float]

  get_slice_range:
    description: >
      Retrieve multiple slices from a series. Useful for scrolling
      through a region of interest.
    params:
      series_id: string
      start: integer             # First slice (0-indexed)
      end: integer               # Last slice (exclusive)
      step: integer              # Default 1; use >1 for overview
    returns:
      type: array
      items:
        image: base64_png
        slice_number: integer
        slice_location_mm: float

  set_window:
    description: >
      Set the display window/level for subsequent image retrievals.
      Use presets for standard tissue types, or specify custom values.
    params:
      preset: string             # One of the named presets below, OR:
      window: integer            # Custom window width (HU)
      level: integer             # Custom window center (HU)
    presets:
      brain:          { window: 80,   level: 40  }
      subdural:       { window: 200,  level: 75  }
      stroke:         { window: 40,   level: 40  }
      bone:           { window: 2000, level: 500 }
      lung:           { window: 1500, level: -600 }
      mediastinal:    { window: 350,  level: 50  }
      soft_tissue:    { window: 400,  level: 50  }
      abdomen:        { window: 350,  level: 40  }
      liver:          { window: 150,  level: 70  }
      pe:             { window: 700,  level: 100 }   # PE protocol
      angiography:    { window: 600,  level: 170 }
    returns:
      current_preset: string
      window: integer
      level: integer

  measure:
    description: >
      Measure distance or area between points on the current slice.
      Coordinates are in pixel space; results returned in mm/mm².
    params:
      series_id: string
      slice_number: integer
      type: string               # "linear" | "area" | "hounsfield"
      points: array              # [[x1,y1], [x2,y2]] for linear;
                                 # polygon for area; single point for HU
    returns:
      value: float
      unit: string               # "mm", "mm²", or "HU"
      mean_hu: float             # For area measurements

  compare_series:
    description: >
      Display two series side-by-side at a matched anatomical level.
      Useful for comparing pre/post contrast, or different reconstructions.
    params:
      series_id_1: string
      series_id_2: string
      slice_number: integer      # In series_1 coordinate space
      match_by: string           # "location" (mm) | "number" | "landmark"
    returns:
      image_1: base64_png
      image_2: base64_png
      location_1_mm: float
      location_2_mm: float
      match_quality: string      # "exact" | "interpolated" | "approximate"

  get_study_info:
    description: >
      Get clinical context from DICOM metadata. Includes patient
      demographics, study description, and clinical indication if available.
    params: {}
    returns:
      study_description: string
      clinical_history: string   # From DICOM tag (0008,1080) or (0010,21B0)
      patient_age: string
      patient_sex: string
      study_date: string
      institution: string
      referring_physician: string
```

### 2.2 Tool Orchestration Patterns

What separates competent interpretation from random tool calls:

**Systematic coverage protocol** (what radiology residents learn in year 1):
1. `navigate_study` — inventory what series are available
2. `get_study_info` — read clinical indication
3. For each relevant series:
   - `set_window` to appropriate preset
   - `get_slice_range` with step=5 for overview scroll
   - Identify regions of interest
   - `get_slice` for targeted review at regions of interest
   - `set_window` to alternate presets (e.g., bone after soft tissue)
4. `compare_series` for pre/post contrast or multiplanar correlation
5. `measure` for any lesions or structures requiring quantification

**Anti-patterns the benchmark detects:**
- Examining only 1-2 slices of a 300-slice volume
- Never changing window/level from default
- Ignoring available series (e.g., reviewing only axial when coronal exists)
- Not comparing pre/post contrast when both are available
- Measuring without switching to appropriate window preset

---

## 3. Task Difficulty Levels

### Level 0 — Single Image Baseline (rc0.5)
**Preserved as floor measurement.** The existing rc0.5 corpus: single image per
task, free-text response, no tools. Measures: can the model interpret a static
picture at all?

- Tasks: 26 (14 X-ray, 12 CT) + Phase 2 US/MRI
- Tools: None (image provided inline)
- Grading: Pattern + LLM judge (current 3-layer)
- Current: 0% judge-only pass rate

### Level 1 — Single Finding, Single Series
*"Identify the pneumothorax. Report: side, size estimate, tension features."*

The agent receives a DICOM series (5-20 slices spanning the finding) and must
use tools to navigate and characterize a single known finding.

- Slices: 5-20 from one series
- Tools needed: `navigate_study`, `get_slice_range`, `set_window`
- Rubric: 4-6 binary checks
- Example rubric:
  ```yaml
  rubric:
    - check: "Agent called navigate_study"
      type: tool_use
      required: true
    - check: "Agent used lung window preset"
      type: tool_use
      required: true
    - check: "Agent identified pneumothorax"
      type: factual
      required: true
    - check: "Agent correctly lateralized (right/left)"
      type: factual
      required: true
    - check: "Agent assessed tension features"
      type: factual
      required: false
    - check: "Agent examined ≥80% of provided slices"
      type: workflow
      required: false
  ```

### Level 2 — Multiple Findings, Single Series
*"Interpret this chest CT. Report all significant findings."*

Full series with multiple pathologies. Tests systematic coverage — does the agent
scroll the entire volume, use multiple window presets, and detect findings across
different tissue types?

- Slices: 50-150 from one series
- Tools needed: `navigate_study`, `get_slice_range`, `set_window` (multiple presets), `measure`
- Rubric: 8-15 binary checks covering each expected finding + workflow metrics
- Example rubric:
  ```yaml
  rubric:
    # Factual
    - check: "Identified right lower lobe consolidation"
      type: factual
      required: true
    - check: "Identified pleural effusion"
      type: factual
      required: true
    - check: "Identified rib fracture"
      type: factual
      required: false
    # Tool use
    - check: "Used lung window for parenchymal evaluation"
      type: tool_use
      required: true
    - check: "Used bone window for skeletal evaluation"
      type: tool_use
      required: true
    - check: "Used mediastinal window for soft tissue"
      type: tool_use
      required: false
    # Workflow
    - check: "Examined ≥80% of slices"
      type: workflow
      required: true
    - check: "Used ≥2 different window presets"
      type: workflow
      required: true
  ```

### Level 3 — Cross-Series Correlation
*"Compare pre and post contrast. Characterize the liver lesion."*

Multiple series from one study. Tests the agent's ability to select the right
series, correlate findings across sequences, and use comparison tools.

- Slices: 200+ across 3-6 series
- Tools needed: All tools including `compare_series` and `measure`
- Rubric: 10-20 binary checks including cross-series correlation
- Example rubric additions:
  ```yaml
  - check: "Compared pre and post contrast at lesion level"
    type: tool_use
    required: true
  - check: "Measured lesion in ≥2 dimensions"
    type: tool_use
    required: true
  - check: "Characterized enhancement pattern (arterial/portal/delayed)"
    type: factual
    required: true
  ```

### Level 4 — Full Study Interpretation
*"Generate a structured radiology report for this trauma CT."*

Complete DICOM study with all clinical context. Tests the full radiologist
workflow: series selection strategy, systematic coverage, structured reporting.

- Slices: 500+ across all available series
- Tools needed: All tools, strategic series selection
- Output: Structured radiology report (findings, impressions, recommendations)
- Rubric: 15-25 binary checks + report structure assessment
- Example rubric additions:
  ```yaml
  - check: "Report includes Findings section"
    type: report_structure
    required: true
  - check: "Report includes Impression section"
    type: report_structure
    required: true
  - check: "Findings are organized by anatomical system"
    type: report_structure
    required: false
  - check: "Report includes actionable recommendations"
    type: report_structure
    required: false
  - check: "Agent examined all available series"
    type: workflow
    required: true
  ```

---

## 4. IDC Sourcing Strategy

### 4.1 Why IDC

NCI Imaging Data Commons provides what PubMed Central case photos cannot:
- **Real DICOM** — full volumetric series, not screenshots
- **CC-BY licensed** — >95% of holdings, no registration required
- **Clinical metadata** — DICOM tags provide age, sex, study description, series info
- **Multi-series studies** — pre/post contrast, multiplanar reconstructions
- **Massive scale** — 95 TB, 161 collections, 79,889 cases

### 4.2 Collection Selection by Level

**Level 0 (Single Image — current PMC sourcing):**
MultiCaRe/PMC case report images. CC-BY. Single representative images.
Already sourced for X-ray and CT. Phase 2 extends to US and MRI.

**Level 1 (Single Series, 5-20 slices):**
Extract short slice ranges from IDC collections:

| Modality | Collection | Why |
|----------|-----------|-----|
| CT | LIDC-IDRI (1,010 patients) | Lung nodule detection, well-annotated |
| CT | CT-ORG (140 patients) | Multi-organ segmentations, diverse anatomy |
| CT | COVID-19-NY-SBU (1,384 patients) | Lung pathology, acute findings |
| MRI | TCGA-GBM (607 patients) | Brain tumors, multi-sequence |
| MRI | TCGA-LGG (516 patients) | Brain tumors, complementary to GBM |
| US | B-mode-and-CEUS-Liver (120 patients) | Liver lesion characterization |
| US | ReMIND (114 patients) | 3D intraoperative brain US |

**Level 2-3 (Full Series / Multi-Series):**

| Collection | Modality | Series/Study | Why |
|-----------|----------|-------------|-----|
| Duke-Breast-Cancer-MRI (922) | MRI | DCE: pre + 3+ post-contrast | Enhancement pattern characterization |
| PROSTATEx (346) | MRI | T2W + DWI + DCE (3-6 series) | Multi-parametric interpretation |
| Prostate-MRI-US-Biopsy (1,151) | MRI + US | MR/US fusion, 3D volumes | Cross-modality correlation |
| TCGA-KIRC (537) | CT + MRI | Multi-sequence kidney | Lesion characterization |
| CPTAC-PDA (195) | CT + MRI + US | Pancreatic, multi-modal | Cross-modality study |
| CMB-CRC (74) | CT + MRI + US | Longitudinal multi-timepoint | Prior comparison |

**Level 4 (Complete Studies):**
CMB collections (BRCA, CRC, MEL, MML) provide longitudinal, multi-modality,
multi-timepoint studies with clinical context — the closest public analog to a
real clinical imaging workflow.

### 4.3 Selection Criteria

For each level, studies are selected by:
1. **CC-BY license** (verified in idc-index `license_short_name`)
2. **Pathology presence** — confirmed by collection description + annotation data
3. **Series completeness** — required number of slices present
4. **Image quality** — no corrupted DICOM, reasonable pixel spacing
5. **Condition match** — DICOM metadata or annotations confirm relevant pathology

### 4.4 Querying IDC

```python
from idc_index import IDCClient

client = IDCClient.client()

# Find CC-BY MRI brain studies with multiple series
query = """
SELECT
    collection_id,
    PatientID,
    StudyInstanceUID,
    SeriesInstanceUID,
    SeriesDescription,
    Modality,
    instanceCount,
    series_size_MB,
    license_short_name
FROM index
WHERE Modality = 'MR'
  AND BodyPartExamined = 'BRAIN'
  AND license_short_name = 'CC BY 4.0'
  AND instanceCount >= 20
ORDER BY collection_id, PatientID, SeriesNumber
"""
results = client.sql_query(query)

# Download a specific series
client.download_dicom_series(
    seriesInstanceUID=["1.2.840.xxxxx"],
    downloadDir="./corpus/dicom/"
)
```

---

## 5. Radiology Interpretation Skill

Following Anthropic's agent skills design — progressive disclosure of domain
knowledge that agents can discover and load dynamically.

### 5.1 Skill Structure

```
skills/radiology-interpretation/
  SKILL.md                    # Frontmatter + table of contents
  protocols/
    systematic-coverage.md    # How to not miss findings
    windowing-guide.md        # When to use which preset
    measurement-standards.md  # How to measure lesions correctly
    series-selection.md       # Which series to look at first
  anatomy/
    chest.md                  # Chest-specific interpretation
    abdomen.md                # Abdomen-specific
    brain.md                  # Neuro-specific
    spine.md                  # Spine-specific
    msk.md                    # Musculoskeletal
  reporting/
    structured-template.md    # Report format
    impression-writing.md     # How to write impressions
    critical-findings.md      # What requires immediate communication
  reference/
    hounsfield-units.md       # Tissue density reference
    normal-measurements.md    # Normal values for common structures
    contrast-phases.md        # Arterial/portal/delayed timing
```

### 5.2 SKILL.md Frontmatter

```yaml
---
name: radiology-interpretation
version: "1.0"
description: >
  Systematic interpretation of medical imaging studies using DICOM
  navigation tools. Covers CT, MRI, ultrasound, and radiograph
  interpretation with appropriate windowing, measurement, and
  structured reporting.
triggers:
  - "interpret"
  - "radiology"
  - "DICOM"
  - "imaging study"
load_order:
  - protocols/systematic-coverage.md
  - protocols/windowing-guide.md
progressive_disclosure:
  always_load:
    - protocols/systematic-coverage.md
  load_on_modality:
    ct: [protocols/windowing-guide.md, anatomy/chest.md]
    mr: [anatomy/brain.md, reference/contrast-phases.md]
    us: [protocols/measurement-standards.md]
  load_on_task:
    report_generation: [reporting/structured-template.md]
    measurement: [protocols/measurement-standards.md, reference/normal-measurements.md]
---
```

### 5.3 Core Protocol: Systematic Coverage

The protocol a radiology resident learns in week one, packaged as agent
instructions:

```markdown
# Systematic Coverage Protocol

## Before Looking at Images
1. Read the clinical indication (`get_study_info`)
2. Inventory available series (`navigate_study`)
3. Plan your approach based on the clinical question

## Series Selection Priority
- **Trauma CT:** Start with soft tissue windows on axial, then bone,
  then check coronal/sagittal reformats
- **Stroke CT/MRI:** Start with DWI (MRI) or non-contrast (CT) at
  the level of the basal ganglia, then systematic superior-to-inferior
- **Chest CT:** Lung windows first (full scroll), then mediastinal,
  then bone windows for ribs/spine
- **Abdomen CT:** Soft tissue first, then check liver windows,
  then bone for spine

## The Scroll
- Never examine fewer than 50% of slices in a series
- Use step=3-5 for initial overview, then step=1 for regions of interest
- Check the edges: lung apices, costophrenic angles, adrenals,
  bowel in the pelvis

## Window/Level Discipline
- You MUST use ≥2 window presets on any CT study
- Lung findings are invisible on soft tissue windows (and vice versa)
- Bone fractures require bone windows
- Subdural hematomas require subdural windows (not standard brain)

## Don't-Miss Checklist
For every study, explicitly check:
- [ ] Lung apices / costophrenic recesses
- [ ] Heart size and pericardium
- [ ] Mediastinal contour
- [ ] Bones visible on the study
- [ ] Soft tissues
- [ ] Any tubes, lines, or devices
```

### 5.4 Key Insight

The skill doesn't give agents the *answers* — it gives them the *procedural
knowledge*. A skill-equipped agent that systematically scrolls through 300
slices with appropriate windowing will outperform a skill-less agent that
looks at 3 slices on default settings, even if both have identical medical
knowledge. This is the tool-orchestration gap that RadSlice v2 measures.

---

## 6. Grading Architecture

### 6.1 Three Rubric Types

**Factual rubrics** — binary checks on diagnostic content:
```yaml
- check: "Identified pneumothorax"
  type: factual
  method: llm_judge  # or pattern match
  required: true
  weight: 0.3
```

**Tool-use rubrics** — binary checks on tool call traces:
```yaml
- check: "Used lung window preset"
  type: tool_use
  method: trace_audit  # deterministic check of tool call log
  required: true
  weight: 0.2
```

**Workflow rubrics** — binary checks on navigation patterns:
```yaml
- check: "Examined ≥80% of slices in primary series"
  type: workflow
  method: coverage_calc  # slices_viewed / total_slices
  required: true
  weight: 0.2
```

### 6.2 Grading Pipeline

```
Agent Response (text + tool call trace)
        │
        ├─ Layer 0: Tool-Use Audit (deterministic)
        │   - Parse tool call log
        │   - Check: which tools called, which presets used
        │   - Check: slice coverage percentage
        │   - Check: series coverage (did agent look at all series?)
        │   - Score: tool_use rubrics + workflow rubrics
        │
        ├─ Layer 1: Pattern Matching (deterministic)
        │   - Regex on final text output
        │   - Check: diagnosis mentioned, laterality stated, etc.
        │   - Score: factual rubrics where pattern-checkable
        │
        └─ Layer 2: LLM Judge (cross-vendor)
            - Receives: agent's final text + ground truth
            - Grades: factual rubrics not covered by patterns
            - Does NOT grade tool use (that's Layer 0)
            - Cross-vendor: GPT judges Opus, Opus judges GPT
```

### 6.3 Composite Score

Each task has a rubric with N binary checks. The score is:

```
score = Σ(check_passed × weight) / Σ(weight)
pass threshold = 0.70 (configurable per level)
```

The key improvement over rc0.5: **tool-use and workflow rubrics are
deterministic** (audited from the tool call trace, not LLM-judged). This
means >50% of the rubric is graded without any LLM judge involvement,
reducing the grading noise that plagues rc0.5.

### 6.4 Metrics

Preserved from rc0.5:
- pass@k, pass^k per task
- Wilson CI on all proportions
- Bootstrap CI for aggregate metrics
- Failure class taxonomy (A/B/C/D/E)

Added for v2:
- **Tool-use efficiency:** tools_called / minimum_tools_needed
- **Coverage score:** slices_examined / total_slices (per series)
- **Window diversity:** unique_presets_used / expected_presets
- **Series utilization:** series_examined / series_available
- **Navigation pattern:** sequential_scroll vs random_access ratio

---

## 7. Relationship to rc0.5

rc0.5 is not deprecated — it becomes **Level 0** in the v2 framework.

| Version | Level | What it measures | Image source | Tools |
|---------|-------|-----------------|-------------|-------|
| rc0.5 | 0 | Single-image pattern recognition | PMC case photos | None |
| v2 L1 | 1 | Tool-assisted single finding | IDC DICOM series | navigate, window, scroll |
| v2 L2 | 2 | Multi-finding systematic coverage | IDC full series | all basic tools |
| v2 L3 | 3 | Cross-series clinical correlation | IDC multi-series | compare, measure |
| v2 L4 | 4 | Full study interpretation | IDC complete study | all tools + skill |

### Migration Path

1. **rc1.0** (immediate): Add US + MRI images to Level 0 corpus. 4-modality
   single-image baseline. Same pipeline as rc0.5.
2. **v2-alpha**: Implement DICOM tool interface. Source Level 1 tasks from IDC.
   Run first agentic evaluation.
3. **v2-beta**: Add Levels 2-3. Implement skill system. Full rubric-based grading.
4. **v2-rc1**: Complete Level 4. Longitudinal study comparison. Structured reporting.

---

## 8. Implementation Roadmap

### Phase A: Level 0 Expansion (rc1.0) — Now

- Source 15 US + 10 MRI images from PMC/MultiCaRe (Phase 2 sourcing)
- Build 4-modality evaluation matrix
- Run cross-vendor eval: Opus + GPT on X-ray + CT + US + MRI
- Establish baseline across all modalities

### Phase B: Tool Interface (v2-alpha) — Next

- Implement DICOM tool interface (`src/radslice/tools/`)
- Build tool execution sandbox (agent calls tools, gets images back)
- Source Level 1 studies from IDC (5-20 slices each)
- Write Level 1 task YAMLs with rubric-based grading
- Run first agentic eval: can models use navigate + window + scroll?

### Phase C: Skill System (v2-beta) — After

- Package radiology interpretation skill following Anthropic's standard
- Implement skill-aware executor (loads skill before sending task)
- Source Level 2-3 studies (multi-finding, multi-series)
- A/B test: skill-equipped vs baseline on same tasks
- Measure skill uplift as a function of task level

### Phase D: Full Study (v2-rc1) — Future

- Source Level 4 complete studies from IDC longitudinal collections
- Implement structured report generation and grading
- Add prior comparison capability (current + previous study)
- Full benchmark: Level 0-4 across 4 modalities, multiple models

---

## 9. Technical Decisions

### MCP Compatibility

The tool interface is designed as an MCP server. Each tool maps to an MCP
`tool` definition with JSON Schema parameters. This means:
- Any MCP-compatible agent can be evaluated
- Tool calls are logged as structured JSON for deterministic auditing
- The same tool server works with Claude, GPT, Gemini via their respective
  function-calling protocols

### DICOM Rendering

DICOM → PNG rendering happens server-side:
- `pydicom` for DICOM parsing
- Window/level application uses existing `src/radslice/dicom.py` infrastructure
- Agent receives rendered PNGs, never raw pixel data
- This is how clinical PACS viewers work — the viewer renders, the radiologist
  navigates

### State Management

The tool server maintains session state:
- Current window/level settings (persist across get_slice calls)
- Currently loaded study
- Tool call history (for grading audit)
- Slice access log (for coverage calculation)

### Cost Control

Agentic evaluation is expensive. Mitigation:
- Level 1 tasks use 5-20 slices (bounded token cost)
- Level 2+ tasks have max_tool_calls limit (e.g., 50 for L2, 100 for L3)
- Response caching (same as rc0.5: SHA-256 keyed)
- Progressive evaluation: run Level 1 first, only advance passing tasks to L2

---

## 10. References

- Hong et al. 2026. "Chatting Ain't Diagnosing: Diagnostic Variability and
  Fundamental Errors in Multimodal LLM Interpretation in Radiology."
  *Algorithms* 19(3):170. DOI: 10.3390/algorithms19030170.
  - 20% fundamental error rate (1/5 frontier models misidentified stroke as
    hemorrhage with wrong lateralization)
  - Clinically meaningful variability among concordant models
  - Conclusion: LLMs predict "what text a radiologist might have written"
    via distributional matching, not genuine diagnosis

- EnterpriseBench: CoreCraft (Surge AI, 2026).
  - Top score: 30.8% (Opus 4.6 with adaptive thinking)
  - Revealed core agent capabilities: tool use, planning, adaptability,
    groundedness, common sense
  - GPT-5.2 failed motherboard task via ineffective search strategies
  - Gemini failed cooling ticket via hallucinated shipping date from
    improper tool use
  - Key insight: these are tool orchestration failures, not knowledge failures

- NCI Imaging Data Commons (IDC).
  - 95 TB, 161 collections, 79,889 cases
  - CC-BY licensed, no registration required
  - Key US collections: B-mode-and-CEUS-Liver, ReMIND, Prostate-MRI-US-Biopsy
  - Key MRI collections: Duke-Breast-Cancer-MRI, PROSTATEx, TCGA-GBM/LGG
  - Key multi-modal: CMB-BRCA/CRC/MEL, CPTAC-PDA

- Anthropic Agent Skills (2026).
  - Progressive disclosure design: frontmatter → chapters → appendix
  - Skills extend general-purpose agents into specialized agents
  - Load information only as needed, composable resources

- RadSlice rc0.5 (this project, 2026-03-03).
  - 26 tasks, 2 models (Opus 4.6 + GPT-5.2), cross-vendor judging
  - 0% judge-only pass rate for both models
  - Confirms Hong et al. finding independently on pathology-validated corpus
