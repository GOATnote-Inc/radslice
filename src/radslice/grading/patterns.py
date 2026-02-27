"""Layer 0: Deterministic regex/contains pattern checks per modality."""

from __future__ import annotations

import re
from dataclasses import dataclass

from radslice.task import Task


@dataclass(frozen=True)
class PatternResult:
    """Result of running pattern checks on a response."""

    checks: dict[str, bool]  # name -> passed
    required_passed: int
    required_total: int
    optional_passed: int
    optional_total: int
    confidence: float  # 0.0-1.0, how decisive pattern checks are

    @property
    def all_required_pass(self) -> bool:
        return self.required_passed == self.required_total

    @property
    def pass_rate(self) -> float:
        total = self.required_total + self.optional_total
        if total == 0:
            return 1.0
        passed = self.required_passed + self.optional_passed
        return passed / total


def run_task_patterns(task: Task, response: str) -> PatternResult:
    """Run all pattern checks defined in a task YAML against the response."""
    checks = {}
    req_passed = 0
    req_total = 0
    opt_passed = 0
    opt_total = 0

    for pc in task.pattern_checks:
        passed = pc.check(response)
        checks[pc.name] = passed
        if pc.required:
            req_total += 1
            if passed:
                req_passed += 1
        else:
            opt_total += 1
            if passed:
                opt_passed += 1

    # Confidence is high when we have many pattern checks and they agree
    total = req_total + opt_total
    if total == 0:
        confidence = 0.0  # No patterns defined, must go to judge
    elif req_total > 0 and req_passed == 0:
        confidence = 0.9  # Strong signal: all required failed
    elif req_passed == req_total and req_total >= 2:
        confidence = 0.85  # Strong signal: all required passed
    else:
        confidence = 0.5 + (0.3 * (req_passed + opt_passed) / total)

    return PatternResult(
        checks=checks,
        required_passed=req_passed,
        required_total=req_total,
        optional_passed=opt_passed,
        optional_total=opt_total,
        confidence=confidence,
    )


# --- Modality-specific supplementary patterns ---

XRAY_PATTERNS: dict[str, re.Pattern] = {
    "consolidation": re.compile(r"\b(consolidat|opacit|infiltrat)", re.IGNORECASE),
    "effusion": re.compile(r"\b(effusion|fluid|meniscus)", re.IGNORECASE),
    "pneumothorax": re.compile(r"\b(pneumothorax|ptx)\b", re.IGNORECASE),
    "cardiomegaly": re.compile(r"\b(cardiomegal|enlarged.heart)", re.IGNORECASE),
    "fracture": re.compile(r"\b(fractur|break|discontinuity)", re.IGNORECASE),
    "nodule": re.compile(r"\b(nodule|mass|lesion)", re.IGNORECASE),
    "atelectasis": re.compile(r"\b(atelectas|collapse)", re.IGNORECASE),
    "normal": re.compile(r"\b(normal|unremarkable|no.acute)", re.IGNORECASE),
}

CT_PATTERNS: dict[str, re.Pattern] = {
    "hounsfield": re.compile(r"\b(hounsfield|HU|density)\b", re.IGNORECASE),
    "enhancement": re.compile(r"\b(enhanc|contrast.uptake)", re.IGNORECASE),
    "hemorrhage": re.compile(r"\b(hemorrhag|bleed|hyperdense)", re.IGNORECASE),
    "mass_effect": re.compile(r"\b(mass.effect|midline.shift|hernia)", re.IGNORECASE),
    "lymphadenopathy": re.compile(r"\b(lymphadenopath|enlarged.node)", re.IGNORECASE),
    "calcification": re.compile(r"\b(calcific|calcified)", re.IGNORECASE),
}

MRI_PATTERNS: dict[str, re.Pattern] = {
    "t1_signal": re.compile(r"\bT1[\s-]*(hyper|hypo|iso|bright|dark|signal)", re.IGNORECASE),
    "t2_signal": re.compile(r"\bT2[\s-]*(hyper|hypo|iso|bright|dark|signal)", re.IGNORECASE),
    "diffusion_restriction": re.compile(
        r"\b(diffusion.restrict|DWI|ADC.?(low|decreas))", re.IGNORECASE
    ),
    "enhancement": re.compile(r"\b(enhanc|gadolinium|contrast.uptake)", re.IGNORECASE),
    "edema": re.compile(r"\b(edema|oedema|FLAIR.hyperinten)", re.IGNORECASE),
}

US_PATTERNS: dict[str, re.Pattern] = {
    "echogenicity": re.compile(r"\b(hyper|hypo|iso|an)echoi?c\b", re.IGNORECASE),
    "doppler": re.compile(r"\b(doppler|flow|vascularity)", re.IGNORECASE),
    "shadowing": re.compile(r"\b(shadow|posterior.acoustic)", re.IGNORECASE),
    "collection": re.compile(r"\b(collection|fluid|cyst)", re.IGNORECASE),
    "calculus": re.compile(r"\b(calcul|stone|lithiasis)", re.IGNORECASE),
}

MODALITY_PATTERNS = {
    "xray": XRAY_PATTERNS,
    "ct": CT_PATTERNS,
    "mri": MRI_PATTERNS,
    "ultrasound": US_PATTERNS,
}


def run_modality_patterns(modality: str, response: str) -> dict[str, bool]:
    """Run supplementary modality-specific patterns against a response."""
    patterns = MODALITY_PATTERNS.get(modality, {})
    return {name: bool(pat.search(response)) for name, pat in patterns.items()}


def check_laterality(response: str, expected: str) -> bool:
    """Check if the response mentions the correct laterality."""
    if not expected:
        return True
    return expected.lower() in response.lower()


def check_negatives(response: str, negatives: list[str]) -> list[str]:
    """Check for false-positive mentions. Returns list of overcalled negatives."""
    overcalled = []
    for neg in negatives:
        if neg.lower() in response.lower():
            overcalled.append(neg)
    return overcalled
