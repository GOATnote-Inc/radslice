#!/usr/bin/env python3
"""Red-team audit of rc1.0 grading: false negative & false positive analysis.

Reads grade and transcript data from both rc1.0 eval runs, cross-references
with task definitions and manual image review classifications to identify
systematic grading errors and compute corrected pass rates.

Usage:
    python scripts/audit_rc10_grading.py
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
GPT_DIR = REPO_ROOT / "results" / "eval-20260303-gpt52-rc10"
OPUS_DIR = REPO_ROOT / "results" / "eval-20260303-opus46-rc10"
TASKS_DIR = REPO_ROOT / "configs" / "tasks"
OUTPUT_PATH = REPO_ROOT / "results" / "rc10-grading-audit.json"

# ---------------------------------------------------------------------------
# Manual image review classifications (14 always-fail tasks)
# ---------------------------------------------------------------------------
IMAGE_REVIEW = {
    "CT-027": {
        "classification": "IMAGE_MISMATCH",
        "condition": "foreign-body-aspiration",
        "evidence": "Image is CXR of intubated patient, not CT with endobronchial FB",
    },
    "CT-048": {
        "classification": "IMAGE_MISMATCH",
        "condition": "open-fracture",
        "evidence": "Shows post-op hardware + intraop surgical photos, not acute CT",
    },
    "CT-097": {
        "classification": "IMAGE_MISMATCH",
        "condition": "acute-angle-closure-glaucoma",
        "evidence": "Image is OCT + B-scan ultrasound, not CT of orbits",
    },
    "MRI-007": {
        "classification": "IMAGE_MISMATCH",
        "condition": "cauda-equina-syndrome",
        "evidence": "Shows neurosarcoidosis (leptomeningeal enhancement), not disc herniation",
    },
    "MRI-031": {
        "classification": "IMAGE_MISMATCH",
        "condition": "hsv-encephalitis",
        "evidence": "Shows ACA infarction + T12 cord infarction, not temporal HSV",
    },
    "MRI-035": {
        "classification": "IMAGE_MISMATCH",
        "condition": "spinal-epidural-abscess",
        "evidence": "Shows LETM/NMOSD (intramedullary), not epidural abscess (extramedullary)",
    },
    "CT-026": {
        "classification": "AMBIGUOUS",
        "condition": "epiglottitis",
        "evidence": "Deep neck infection on CT, epiglottic vs retropharyngeal involvement unclear",
    },
    "CT-085": {
        "classification": "AMBIGUOUS",
        "condition": "lateral-canthotomy",
        "evidence": "Axial CT orbit but GPT sees humeral head -- cropped, ambiguous anatomy",
    },
    "CT-106": {
        "classification": "AMBIGUOUS",
        "condition": "neonatal-emergencies",
        "evidence": "CT head hemorrhage+edema -- HIE vs IVH both plausible",
    },
    "US-034": {
        "classification": "AMBIGUOUS",
        "condition": "ectopic-pregnancy",
        "evidence": "Gestational sac visible but ectopic vs IUP not determinable without uterine context",
    },
    "XRAY-045": {
        "classification": "AMBIGUOUS",
        "condition": "globe-rupture",
        "evidence": "Metallic FB in orbital/nasal region -- intraocular vs intranasal ambiguous",
    },
    "US-010": {
        "classification": "GENUINE",
        "condition": "ruptured-aaa",
        "evidence": "Image clearly shows aorta (labeled A/B/C), GPT misidentifies as appendicitis",
    },
    "US-073": {
        "classification": "GENUINE",
        "condition": "acute-appendicitis",
        "evidence": "POCUS appendicitis image, GPT sees venous thrombosis",
    },
    "US-082": {
        "classification": "GENUINE",
        "condition": "necrotizing-fasciitis",
        "evidence": "Labeled 'INF TO TESTIS SAG' with dirty shadowing, GPT sees hernia",
    },
}

# ---------------------------------------------------------------------------
# Cross-model gap classifications (from manual transcript review)
# ---------------------------------------------------------------------------
CROSS_MODEL_GAP = {
    # Opus-only (pass Opus, fail GPT)
    "CT-065": {
        "gap_type": "style_bias",
        "evidence": "Both see Ludwig's angina; GPT says peritonsillar/parapharyngeal (pattern miss)",
    },
    "XRAY-007": {
        "gap_type": "style_bias",
        "evidence": "Opus says cardiomegaly (matches), GPT says pleural effusion only",
    },
    "XRAY-027": {
        "gap_type": "style_bias",
        "evidence": "Opus says emphysema (matches), GPT says pneumothorax without emphysema",
    },
    # GPT-only (pass GPT 3/3, fail Opus 0/3) -- top 5
    "CT-061": {
        "gap_type": "capability",
        "evidence": "Opus cannot identify retrobulbar hemorrhage on CT (scores ~0.03, Class B)",
    },
    "US-042": {
        "gap_type": "capability",
        "evidence": "Opus cannot identify testicular torsion on US (scores ~0.00, Class B)",
    },
    "XRAY-055": {
        "gap_type": "capability",
        "evidence": "Opus cannot identify submersion injury on CXR (scores ~0.01, Class B)",
    },
    "CT-069": {
        "gap_type": "style_bias",
        "evidence": "Opus likely identifies abscess but uses wrong anatomic terminology (Class A)",
    },
    "US-026": {
        "gap_type": "style_bias",
        "evidence": "Opus scores 0.56-0.62, near threshold -- identifies features but misses pattern",
    },
}

# ---------------------------------------------------------------------------
# Task lists
# ---------------------------------------------------------------------------
ALWAYS_FAIL = sorted(IMAGE_REVIEW.keys())  # 14 tasks: both models fail all 3 trials

ALWAYS_PASS_OPUS = [  # 13 tasks: Opus passes all 3 trials
    # Both pass 3/3
    "MRI-023",
    "MRI-040",
    "US-024",
    "US-036",
    "US-046",
    "US-066",
    "US-069",
    "XRAY-014",
    "XRAY-039",
    # Opus-only 3/3
    "CT-065",
    "XRAY-007",
    "XRAY-027",
    # Mixed, Opus 3/3
    "MRI-005",
]

# Suspicious always-pass tasks (broad patterns may cause false positives)
SUSPICIOUS_PASS = {
    "XRAY-007": "RUBRIC_EASY",  # pattern matches cardiomegaly, not pericarditis
    "XRAY-027": "RUBRIC_EASY",  # pattern matches emphysema, not tracheal disruption
}

OPUS_ONLY = ["CT-065", "XRAY-007", "XRAY-027"]
GPT_ONLY_PICKS = ["CT-061", "US-042", "XRAY-055", "CT-069", "US-026"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_grades(results_dir: Path) -> dict[str, list[dict]]:
    """Load grades.jsonl, return {task_id: [grade_dicts]} sorted by trial."""
    grades: dict[str, list[dict]] = defaultdict(list)
    with open(results_dir / "grades.jsonl") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            g = json.loads(line)
            grades[g["task_id"]].append(g)
    # Sort by trial within each task
    for task_id in grades:
        grades[task_id].sort(key=lambda g: g.get("trial", 0))
    return dict(grades)


def load_transcripts(results_dir: Path) -> dict[str, list[dict]]:
    """Load transcripts.jsonl, return {task_id: [transcript_dicts]}."""
    transcripts: dict[str, list[dict]] = defaultdict(list)
    with open(results_dir / "transcripts.jsonl") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            if t.get("type") == "header":
                continue
            transcripts[t["task_id"]].append(t)
    return dict(transcripts)


def load_task_yaml(task_id: str) -> dict:
    """Load task YAML by ID, searching modality subdirectories."""
    for subdir in ["xray", "ct", "mri", "ultrasound", "incidental", "audit"]:
        path = TASKS_DIR / subdir / f"{task_id}.yaml"
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)
    raise FileNotFoundError(f"Task YAML not found: {task_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def best_response(transcripts: list[dict]) -> str:
    """Return the longest response (best attempt) from a set of trials."""
    if not transcripts:
        return ""
    return max(transcripts, key=lambda t: len(t.get("response", "") or "")).get("response", "")


def shortest_response(transcripts: list[dict]) -> str:
    """Return the shortest response from a set of trials."""
    if not transcripts:
        return ""
    valid = [t for t in transcripts if t.get("response")]
    if not valid:
        return ""
    return min(valid, key=lambda t: len(t["response"]))["response"]


def extract_primary_diagnosis(response: str) -> str:
    """Extract the primary diagnosis from a model response (best-effort)."""
    if not response:
        return "(empty response)"
    # Try structured headings
    for label in [
        r"(?:primary\s+)?diagnosis",
        r"assessment",
        r"impression",
        r"conclusion",
    ]:
        match = re.search(rf"(?i)(?:#+\s*)?{label}[:\s]*\**\s*(.+?)(?:\n|$)", response)
        if match:
            text = match.group(1).strip().strip("*").strip()
            if len(text) > 5:
                return text[:200]
    # Fallback: first substantive line
    for line in response.split("\n"):
        line = line.strip().lstrip("#").strip()
        if len(line) > 10 and not line.startswith("I ") and not line.startswith("Based on"):
            return line[:200]
    return response[:200]


def has_image_reasoning(response: str) -> dict:
    """Check for image-specific reasoning indicators in a response."""
    indicators = {
        "measurements": bool(re.search(r"\d+\.?\d*\s*(mm|cm|mL|HU)", response)),
        "laterality": bool(re.search(r"(?i)\b(left|right|bilateral|midline)\b", response)),
        "anatomic_landmarks": bool(
            re.search(
                r"(?i)\b(lobe|ventricle|cortex|mediastin|hilum|pleural|peritoneal|"
                r"fascial|parenchyma|sulcus|gyrus|foramen|fossa|sinus|tendon|ligament|"
                r"vertebr|disc|meniscus|capsule)\b",
                response,
            )
        ),
        "contrast_descriptions": bool(
            re.search(
                r"(?i)\b(hypodense|hyperdense|hyperintense|hypointense|echogenic|"
                r"hypoechoic|anechoic|radiopaque|radiolucent|enhancing|lucen[ct])\b",
                response,
            )
        ),
        "technique_references": bool(
            re.search(
                r"(?i)\b(PA view|AP view|axial|sagittal|coronal|transverse|"
                r"T1.weighted|T2.weighted|FLAIR|DWI|contrast|Doppler)\b",
                response,
            )
        ),
    }
    indicators["count"] = sum(1 for k, v in indicators.items() if k != "count" and v is True)
    return indicators


def classify_false_positive(task_id: str, response: str, task_yaml: dict) -> str:
    """Classify an always-pass task as VALID, RUBRIC_EASY, or PATTERN_LEAK."""
    if task_id in SUSPICIOUS_PASS:
        return SUSPICIOUS_PASS[task_id]

    # Check if primary diagnosis appears in response
    primary_dx = task_yaml.get("ground_truth", {}).get("primary_diagnosis", "")
    if primary_dx:
        # Extract key clinical terms (>= 4 chars, skip articles/prepositions)
        skip = {"with", "from", "that", "this", "have", "been", "were", "into", "upon", "over"}
        key_terms = [w for w in re.findall(r"\b\w{4,}\b", primary_dx.lower()) if w not in skip]
        if key_terms:
            response_lower = response.lower()
            matches = sum(1 for t in key_terms if t in response_lower)
            if matches >= max(1, len(key_terms) * 0.4):
                return "VALID"

    # Image-specific reasoning as fallback signal
    reasoning = has_image_reasoning(response)
    if reasoning["count"] >= 3:
        return "VALID"

    return "PATTERN_LEAK"


# ---------------------------------------------------------------------------
# Analysis: false negatives (14 always-fail tasks)
# ---------------------------------------------------------------------------
def analyze_false_negatives(
    gpt_grades: dict,
    opus_grades: dict,
    gpt_transcripts: dict,
    opus_transcripts: dict,
) -> list[dict]:
    """Analyze the 14 always-fail tasks using GPT's best response."""
    results = []
    for task_id in ALWAYS_FAIL:
        review = IMAGE_REVIEW[task_id]
        task_yaml = load_task_yaml(task_id)
        gt = task_yaml.get("ground_truth", {})

        # Best GPT response (longest)
        gpt_best = best_response(gpt_transcripts.get(task_id, []))

        # GPT grades for this task
        gpt_trials = gpt_grades.get(task_id, [])
        # Use trial with highest weighted_score for representative data
        best_grade = max(gpt_trials, key=lambda g: g.get("weighted_score", 0)) if gpt_trials else {}

        model_dx = extract_primary_diagnosis(gpt_best)

        entry = {
            "task_id": task_id,
            "condition": review["condition"],
            "classification": review["classification"],
            "evidence": review["evidence"],
            "expected_diagnosis": gt.get("primary_diagnosis", ""),
            "model_primary_diagnosis": model_dx,
            "detection_layer": best_grade.get("detection_layer"),
            "pattern_confidence": best_grade.get("pattern_result", {}).get("confidence"),
            "pattern_checks": best_grade.get("pattern_result", {}).get("checks", {}),
            "failure_class": best_grade.get("failure_class"),
            "weighted_score": best_grade.get("weighted_score"),
            "gpt_all_layer_0": all(g.get("detection_layer") == 0 for g in gpt_trials),
            "opus_all_layer_0": all(
                g.get("detection_layer") == 0 for g in opus_grades.get(task_id, [])
            ),
        }
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Analysis: false positives (13 always-pass Opus tasks)
# ---------------------------------------------------------------------------
def analyze_false_positives(
    opus_grades: dict,
    opus_transcripts: dict,
) -> list[dict]:
    """Analyze the 13 always-pass Opus tasks using shortest Opus response."""
    results = []
    for task_id in ALWAYS_PASS_OPUS:
        task_yaml = load_task_yaml(task_id)

        # Shortest Opus response (weakest signal that still passes)
        opus_short = shortest_response(opus_transcripts.get(task_id, []))

        # Opus grades for this task
        opus_trials = opus_grades.get(task_id, [])
        first_grade = opus_trials[0] if opus_trials else {}

        reasoning = has_image_reasoning(opus_short)
        classification = classify_false_positive(task_id, opus_short, task_yaml)

        entry = {
            "task_id": task_id,
            "condition": task_yaml.get("condition_id", ""),
            "classification": classification,
            "detection_layer": first_grade.get("detection_layer"),
            "pattern_confidence": first_grade.get("pattern_result", {}).get("confidence"),
            "pattern_checks": first_grade.get("pattern_result", {}).get("checks", {}),
            "weighted_score": first_grade.get("weighted_score"),
            "image_reasoning_indicators": {k: v for k, v in reasoning.items() if k != "count"},
            "image_reasoning_count": reasoning["count"],
            "response_length": len(opus_short),
        }
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Analysis: cross-model disagreement (3 Opus-only + 5 GPT-only)
# ---------------------------------------------------------------------------
def analyze_cross_model(
    gpt_grades: dict,
    opus_grades: dict,
    gpt_transcripts: dict,
    opus_transcripts: dict,
) -> list[dict]:
    """Analyze 8 cross-model disagreement tasks."""
    results = []
    task_ids = OPUS_ONLY + GPT_ONLY_PICKS

    for task_id in task_ids:
        task_yaml = load_task_yaml(task_id)
        gap = CROSS_MODEL_GAP[task_id]

        gpt_best = best_response(gpt_transcripts.get(task_id, []))
        opus_best = best_response(opus_transcripts.get(task_id, []))

        gpt_trials = gpt_grades.get(task_id, [])
        opus_trials = opus_grades.get(task_id, [])

        gpt_passes = sum(1 for g in gpt_trials if g.get("passed"))
        opus_passes = sum(1 for g in opus_trials if g.get("passed"))

        gpt_scores = [g.get("weighted_score", 0) for g in gpt_trials]
        opus_scores = [g.get("weighted_score", 0) for g in opus_trials]

        gpt_classes = [g.get("failure_class") for g in gpt_trials]
        opus_classes = [g.get("failure_class") for g in opus_trials]

        entry = {
            "task_id": task_id,
            "condition": task_yaml.get("condition_id", ""),
            "direction": "opus_only" if task_id in OPUS_ONLY else "gpt_only",
            "gap_type": gap["gap_type"],
            "evidence": gap["evidence"],
            "gpt_pass_rate": f"{gpt_passes}/3",
            "opus_pass_rate": f"{opus_passes}/3",
            "gpt_mean_score": round(sum(gpt_scores) / len(gpt_scores), 3) if gpt_scores else 0,
            "opus_mean_score": round(sum(opus_scores) / len(opus_scores), 3) if opus_scores else 0,
            "gpt_failure_classes": gpt_classes,
            "opus_failure_classes": opus_classes,
            "gpt_primary_diagnosis": extract_primary_diagnosis(gpt_best),
            "opus_primary_diagnosis": extract_primary_diagnosis(opus_best),
        }
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Corrected pass rates
# ---------------------------------------------------------------------------
def compute_corrected_rates(gpt_grades: dict, opus_grades: dict) -> dict:
    """Compute pass rates with IMAGE_MISMATCH and AMBIGUOUS tasks excluded."""
    mismatch = {t for t, r in IMAGE_REVIEW.items() if r["classification"] == "IMAGE_MISMATCH"}
    ambiguous = {t for t, r in IMAGE_REVIEW.items() if r["classification"] == "AMBIGUOUS"}
    all_tasks = set(gpt_grades.keys()) | set(opus_grades.keys())

    def _rates(task_set):
        gpt_t = sum(len(gpt_grades.get(t, [])) for t in task_set)
        gpt_p = sum(1 for t in task_set for g in gpt_grades.get(t, []) if g.get("passed"))
        opus_t = sum(len(opus_grades.get(t, [])) for t in task_set)
        opus_p = sum(1 for t in task_set for g in opus_grades.get(t, []) if g.get("passed"))
        return {
            "n_tasks": len(task_set),
            "gpt_pass_rate": round(gpt_p / gpt_t * 100, 1) if gpt_t else 0,
            "opus_pass_rate": round(opus_p / opus_t * 100, 1) if opus_t else 0,
            "gpt_passes": gpt_p,
            "gpt_trials": gpt_t,
            "opus_passes": opus_p,
            "opus_trials": opus_t,
        }

    corrected = all_tasks - mismatch
    optimistic = corrected - ambiguous

    return {
        "original": _rates(all_tasks),
        "mismatch_excluded": {
            **_rates(corrected),
            "excluded_tasks": sorted(mismatch),
        },
        "mismatch_and_ambiguous_excluded": {
            **_rates(optimistic),
            "excluded_tasks": sorted(mismatch | ambiguous),
        },
    }


# ---------------------------------------------------------------------------
# Systemic findings
# ---------------------------------------------------------------------------
def compute_systemic_findings(gpt_grades: dict, opus_grades: dict) -> dict:
    """Compute Layer 0 dominance statistics for extreme tasks."""
    # Always-fail: count Layer 0 across both models
    fail_l0_gpt = sum(
        1 for t in ALWAYS_FAIL for g in gpt_grades.get(t, []) if g.get("detection_layer") == 0
    )
    fail_total_gpt = sum(len(gpt_grades.get(t, [])) for t in ALWAYS_FAIL)

    fail_l0_opus = sum(
        1 for t in ALWAYS_FAIL for g in opus_grades.get(t, []) if g.get("detection_layer") == 0
    )
    fail_total_opus = sum(len(opus_grades.get(t, [])) for t in ALWAYS_FAIL)

    fail_l0 = fail_l0_gpt + fail_l0_opus
    fail_total = fail_total_gpt + fail_total_opus

    # Always-pass Opus: count Layer 0
    pass_l0 = sum(
        1 for t in ALWAYS_PASS_OPUS for g in opus_grades.get(t, []) if g.get("detection_layer") == 0
    )
    pass_total = sum(len(opus_grades.get(t, [])) for t in ALWAYS_PASS_OPUS)

    fail_pct = round(fail_l0 / fail_total * 100) if fail_total else 0
    pass_pct = round(pass_l0 / pass_total * 100) if pass_total else 0

    return {
        "layer_0_dominance": {
            "always_fail_layer_0_pct": fail_pct,
            "always_pass_layer_0_pct": pass_pct,
            "always_fail_detail": f"{fail_l0}/{fail_total} (GPT {fail_l0_gpt}/{fail_total_gpt}, Opus {fail_l0_opus}/{fail_total_opus})",
            "always_pass_detail": f"{pass_l0}/{pass_total}",
            "judge_never_invoked_for_extreme_tasks": fail_l0 == fail_total
            and pass_l0 == pass_total,
            "confidence_threshold": 0.8,
            "recommendation": "Lower LAYER_0_CONFIDENCE_THRESHOLD or force judge for Class A",
        }
    }


# ---------------------------------------------------------------------------
# Human-readable report
# ---------------------------------------------------------------------------
def print_report(audit: dict) -> None:
    """Print formatted summary to stdout."""
    W = 72
    print("=" * W)
    print("  RC1.0 GRADING AUDIT -- FALSE NEGATIVE & FALSE POSITIVE ANALYSIS")
    print("=" * W)
    print()

    # -- Systemic finding --
    sf = audit["systemic_findings"]["layer_0_dominance"]
    print("SYSTEMIC FINDING: Layer 0 (Pattern-Only) Grading Dominates")
    print("-" * 60)
    print(f"  Always-fail Layer 0:  {sf['always_fail_layer_0_pct']}%  ({sf['always_fail_detail']})")
    print(f"  Always-pass Layer 0:  {sf['always_pass_layer_0_pct']}%  ({sf['always_pass_detail']})")
    judge_status = "No" if sf["judge_never_invoked_for_extreme_tasks"] else "Yes (partial)"
    print(f"  Judge invoked for extreme tasks:  {judge_status}")
    print(f"  Confidence threshold:             {sf['confidence_threshold']}")
    print(f"  Recommendation: {sf['recommendation']}")
    print()

    # -- False negatives --
    fn = audit["false_negatives"]
    print(f"FALSE NEGATIVES ({len(fn)} always-fail tasks)")
    print("-" * 60)
    for classification in ["IMAGE_MISMATCH", "AMBIGUOUS", "GENUINE"]:
        tasks = [e for e in fn if e["classification"] == classification]
        if not tasks:
            continue
        print(f"\n  {classification} ({len(tasks)}):")
        for e in tasks:
            layer = e.get("detection_layer", "?")
            conf = e.get("pattern_confidence", 0)
            print(f"    {e['task_id']:10s}  {e['condition']:35s}  L{layer} conf={conf}")
            print(f"      Expected:  {e['expected_diagnosis'][:65]}")
            print(f"      Model dx:  {e['model_primary_diagnosis'][:65]}")
            print(f"      Evidence:  {e['evidence'][:65]}")
    print()

    # -- False positives --
    fp = audit["false_positives"]
    print(f"FALSE POSITIVES ({len(fp)} always-pass Opus tasks)")
    print("-" * 60)
    for classification in ["VALID", "RUBRIC_EASY", "PATTERN_LEAK"]:
        tasks = [e for e in fp if e["classification"] == classification]
        if not tasks:
            continue
        print(f"\n  {classification} ({len(tasks)}):")
        for e in tasks:
            layer = e.get("detection_layer", "?")
            conf = e.get("pattern_confidence", 0)
            reasoning = e.get("image_reasoning_count", 0)
            print(
                f"    {e['task_id']:10s}  {e['condition']:35s}  "
                f"L{layer} conf={conf}  reasoning={reasoning}/5"
            )
    print()

    # -- Cross-model --
    cm = audit["cross_model"]
    print(f"CROSS-MODEL DISAGREEMENT ({len(cm)} tasks)")
    print("-" * 60)
    for direction, label in [
        ("opus_only", "Opus-only (pass Opus, fail GPT)"),
        ("gpt_only", "GPT-only (pass GPT, fail Opus)"),
    ]:
        tasks = [e for e in cm if e["direction"] == direction]
        if not tasks:
            continue
        print(f"\n  {label}:")
        for e in tasks:
            print(f"    {e['task_id']:10s}  {e['condition']:35s}  gap={e['gap_type']}")
            print(
                f"      GPT: {e['gpt_pass_rate']}  mean={e['gpt_mean_score']:.3f}  "
                f"dx: {e['gpt_primary_diagnosis'][:50]}"
            )
            print(
                f"      Opus: {e['opus_pass_rate']}  mean={e['opus_mean_score']:.3f}  "
                f"dx: {e['opus_primary_diagnosis'][:50]}"
            )
    print()

    # -- Corrected pass rates --
    corr = audit["corrected_rates"]
    print("CORRECTED PASS RATES")
    print("-" * 60)
    for key, label in [
        ("original", "Original"),
        ("mismatch_excluded", "IMAGE_MISMATCH excluded"),
        ("mismatch_and_ambiguous_excluded", "IMAGE_MISMATCH + AMBIGUOUS excluded"),
    ]:
        r = corr[key]
        excluded = r.get("excluded_tasks", [])
        excl_str = f"  (excl: {', '.join(excluded)})" if excluded else ""
        print(f"\n  {label} ({r['n_tasks']} tasks):{excl_str}")
        print(f"    GPT-5.2:   {r['gpt_pass_rate']:5.1f}%  ({r['gpt_passes']}/{r['gpt_trials']})")
        print(
            f"    Opus 4.6:  {r['opus_pass_rate']:5.1f}%  ({r['opus_passes']}/{r['opus_trials']})"
        )
    print()

    # -- Summary --
    s = audit["summary"]
    print("SUMMARY")
    print("-" * 60)
    print(
        f"  False negatives:  {s['fn_image_mismatch']} IMAGE_MISMATCH, "
        f"{s['fn_ambiguous']} AMBIGUOUS, {s['fn_genuine']} GENUINE"
    )
    print(
        f"  False positives:  {s['fp_valid']} VALID, "
        f"{s['fp_rubric_easy']} RUBRIC_EASY, {s['fp_pattern_leak']} PATTERN_LEAK"
    )
    print(f"  Corrected GPT pass rate:   {s['estimated_corrected_pass_rate_gpt']}")
    print(f"  Corrected Opus pass rate:  {s['estimated_corrected_pass_rate_opus']}")
    print()

    # -- Recommended actions --
    print("RECOMMENDED ACTIONS")
    print("-" * 60)
    print("  1. FIX: Replace 6 IMAGE_MISMATCH images with correct pathology")
    print("  2. FIX: Lower LAYER_0_CONFIDENCE_THRESHOLD from 0.8 to 0.6")
    print("     (forces judge invocation for borderline pattern results)")
    print("  3. FIX: Force judge for all Class A failures regardless of confidence")
    print("  4. REVIEW: 5 AMBIGUOUS tasks -- clarify images or add to exclusion list")
    print("  5. REVIEW: 2 RUBRIC_EASY patterns (XRAY-007, XRAY-027) -- tighten to")
    print("     require primary diagnosis term, not just associated findings")
    print("  6. MEASURE: Re-run grading with judge forced to establish true rates")
    print()
    print("=" * W)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Verify input files exist
    missing = []
    for path, label in [
        (GPT_DIR / "grades.jsonl", "GPT grades"),
        (GPT_DIR / "transcripts.jsonl", "GPT transcripts"),
        (OPUS_DIR / "grades.jsonl", "Opus grades"),
        (OPUS_DIR / "transcripts.jsonl", "Opus transcripts"),
    ]:
        if not path.exists():
            missing.append(f"  {label}: {path}")
    if missing:
        print("ERROR: Missing input files:", file=sys.stderr)
        for m in missing:
            print(m, file=sys.stderr)
        sys.exit(1)

    print("Loading grade and transcript data...")
    gpt_grades = load_grades(GPT_DIR)
    opus_grades = load_grades(OPUS_DIR)
    gpt_transcripts = load_transcripts(GPT_DIR)
    opus_transcripts = load_transcripts(OPUS_DIR)

    print(
        f"  GPT:  {sum(len(v) for v in gpt_grades.values())} grades, "
        f"{sum(len(v) for v in gpt_transcripts.values())} transcripts"
    )
    print(
        f"  Opus: {sum(len(v) for v in opus_grades.values())} grades, "
        f"{sum(len(v) for v in opus_transcripts.values())} transcripts"
    )

    # Verify expected task lists match data
    computed_always_fail = sorted(
        t
        for t in set(gpt_grades) & set(opus_grades)
        if all(not g.get("passed") for g in gpt_grades[t])
        and all(not g.get("passed") for g in opus_grades[t])
    )
    computed_always_pass_opus = sorted(
        t for t in opus_grades if all(g.get("passed") for g in opus_grades[t])
    )
    if set(computed_always_fail) != set(ALWAYS_FAIL):
        extra = set(computed_always_fail) - set(ALWAYS_FAIL)
        missing_tasks = set(ALWAYS_FAIL) - set(computed_always_fail)
        print(f"  WARNING: Always-fail mismatch. Extra: {extra}, Missing: {missing_tasks}")
    if set(computed_always_pass_opus) != set(ALWAYS_PASS_OPUS):
        extra = set(computed_always_pass_opus) - set(ALWAYS_PASS_OPUS)
        missing_tasks = set(ALWAYS_PASS_OPUS) - set(computed_always_pass_opus)
        print(f"  WARNING: Always-pass mismatch. Extra: {extra}, Missing: {missing_tasks}")

    # Run analyses
    print("\nAnalyzing false negatives (14 always-fail tasks)...")
    fn = analyze_false_negatives(gpt_grades, opus_grades, gpt_transcripts, opus_transcripts)

    print("Analyzing false positives (13 always-pass Opus tasks)...")
    fp = analyze_false_positives(opus_grades, opus_transcripts)

    print("Analyzing cross-model disagreements (8 tasks)...")
    cm = analyze_cross_model(gpt_grades, opus_grades, gpt_transcripts, opus_transcripts)

    print("Computing corrected pass rates...")
    corrected = compute_corrected_rates(gpt_grades, opus_grades)

    print("Computing systemic findings...")
    systemic = compute_systemic_findings(gpt_grades, opus_grades)

    # Build summary
    fn_counts = defaultdict(int)
    for e in fn:
        fn_counts[e["classification"]] += 1
    fp_counts = defaultdict(int)
    for e in fp:
        fp_counts[e["classification"]] += 1

    audit = {
        "false_negatives": fn,
        "false_positives": fp,
        "cross_model": cm,
        "systemic_findings": systemic,
        "corrected_rates": corrected,
        "summary": {
            "fn_genuine": fn_counts.get("GENUINE", 0),
            "fn_rubric_strict": 0,
            "fn_image_mismatch": fn_counts.get("IMAGE_MISMATCH", 0),
            "fn_ambiguous": fn_counts.get("AMBIGUOUS", 0),
            "fp_valid": fp_counts.get("VALID", 0),
            "fp_rubric_easy": fp_counts.get("RUBRIC_EASY", 0),
            "fp_pattern_leak": fp_counts.get("PATTERN_LEAK", 0),
            "estimated_corrected_pass_rate_gpt": f"{corrected['mismatch_excluded']['gpt_pass_rate']}%",
            "estimated_corrected_pass_rate_opus": f"{corrected['mismatch_excluded']['opus_pass_rate']}%",
        },
    }

    # Write JSON output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(audit, f, indent=2)
    print(f"\nAudit JSON written to {OUTPUT_PATH}")

    # Print human-readable report
    print()
    print_report(audit)


if __name__ == "__main__":
    main()
