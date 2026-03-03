#!/usr/bin/env python3
"""Phase 2 sourcing: ultrasound and MRI images from PubMed Central / MultiCaRe.

Extends the Phase 1 X-ray/CT corpus with 15 US + 10 MRI pathology-validated images.
Uses the same discover_multicare.py pipeline (Europe PMC search + CDN resolution).

Usage:
    python scripts/source_phase2.py [--dry-run] [--top 5]
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
from discover_multicare import discover_candidates

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("source_phase2")

CORPUS_DIR = Path("corpus/images")

# Phase 2 sourcing targets — selected for HIGH sourcing probability,
# distinctive imaging findings, and diverse anatomy coverage.
TARGETS = [
    # ── Ultrasound (15 tasks) ──
    # Cardiac
    {
        "task_id": "US-006",
        "condition": "cardiac tamponade",
        "modality": "ultrasound",
        "search_terms": "cardiac tamponade pericardial effusion echocardiography",
    },
    {
        "task_id": "US-010",
        "condition": "ruptured aaa",
        "modality": "ultrasound",
        "search_terms": "abdominal aortic aneurysm ultrasound POCUS",
    },
    # Lung
    {
        "task_id": "US-024",
        "condition": "spontaneous pneumothorax",
        "modality": "ultrasound",
        "search_terms": "pneumothorax lung ultrasound absent lung sliding",
    },
    # Abdomen
    {
        "task_id": "US-026",
        "condition": "acute cholecystitis",
        "modality": "ultrasound",
        "search_terms": "acute cholecystitis gallbladder ultrasound",
    },
    {
        "task_id": "US-066",
        "condition": "intussusception",
        "modality": "ultrasound",
        "search_terms": "intussusception target sign ultrasound",
    },
    {
        "task_id": "US-073",
        "condition": "acute appendicitis",
        "modality": "ultrasound",
        "search_terms": "acute appendicitis ultrasound graded compression",
    },
    {
        "task_id": "US-046",
        "condition": "urolithiasis",
        "modality": "ultrasound",
        "search_terms": "urolithiasis hydronephrosis renal ultrasound",
    },
    # Pelvis/OB-GYN
    {
        "task_id": "US-034",
        "condition": "ectopic pregnancy",
        "modality": "ultrasound",
        "search_terms": "ectopic pregnancy transvaginal ultrasound",
    },
    {
        "task_id": "US-036",
        "condition": "ovarian torsion",
        "modality": "ultrasound",
        "search_terms": "ovarian torsion pelvic ultrasound Doppler",
    },
    {
        "task_id": "US-042",
        "condition": "testicular torsion",
        "modality": "ultrasound",
        "search_terms": "testicular torsion scrotal ultrasound Doppler",
    },
    # Vascular
    {
        "task_id": "US-053",
        "condition": "deep vein thrombosis",
        "modality": "ultrasound",
        "search_terms": "deep vein thrombosis DVT compression ultrasound",
    },
    # MSK/Soft tissue
    {
        "task_id": "US-050",
        "condition": "retinal detachment",
        "modality": "ultrasound",
        "search_terms": "retinal detachment ocular ultrasound",
    },
    {
        "task_id": "US-082",
        "condition": "necrotizing fasciitis",
        "modality": "ultrasound",
        "search_terms": "necrotizing fasciitis soft tissue ultrasound",
    },
    # Pediatric
    {
        "task_id": "US-069",
        "condition": "pyloric stenosis",
        "modality": "ultrasound",
        "search_terms": "pyloric stenosis abdominal ultrasound hypertrophic",
    },
    # Trauma
    {
        "task_id": "US-019",
        "condition": "hemorrhagic shock",
        "modality": "ultrasound",
        "search_terms": "FAST examination hemoperitoneum free fluid ultrasound trauma",
    },
    # ── MRI (10 tasks) ──
    # Neuro
    {
        "task_id": "MRI-005",
        "condition": "acute ischemic stroke",
        "modality": "mri",
        "search_terms": "acute ischemic stroke DWI MRI diffusion weighted",
    },
    {
        "task_id": "MRI-010",
        "condition": "hemorrhagic stroke",
        "modality": "mri",
        "search_terms": "intracerebral hemorrhage brain MRI",
    },
    {
        "task_id": "MRI-023",
        "condition": "eclampsia",
        "modality": "mri",
        "search_terms": "PRES posterior reversible encephalopathy syndrome MRI",
    },
    {
        "task_id": "MRI-031",
        "condition": "hsv encephalitis",
        "modality": "mri",
        "search_terms": "herpes simplex encephalitis HSV MRI temporal lobe",
    },
    {
        "task_id": "MRI-040",
        "condition": "carbon monoxide poisoning",
        "modality": "mri",
        "search_terms": "carbon monoxide poisoning globus pallidus MRI",
    },
    # Spine
    {
        "task_id": "MRI-007",
        "condition": "cauda equina syndrome",
        "modality": "mri",
        "search_terms": "cauda equina syndrome lumbar MRI disc herniation",
    },
    {
        "task_id": "MRI-011",
        "condition": "spinal cord compression",
        "modality": "mri",
        "search_terms": "spinal cord compression myelopathy MRI",
    },
    {
        "task_id": "MRI-035",
        "condition": "spinal epidural abscess",
        "modality": "mri",
        "search_terms": "spinal epidural abscess MRI",
    },
    # Cardiac
    {
        "task_id": "MRI-003",
        "condition": "pericarditis myocarditis",
        "modality": "mri",
        "search_terms": "myocarditis cardiac MRI late gadolinium enhancement",
    },
    # Head special
    {
        "task_id": "MRI-014",
        "condition": "fat embolism syndrome",
        "modality": "mri",
        "search_terms": "fat embolism syndrome starfield pattern DWI MRI",
    },
]


def download_image(url: str, dest: Path) -> bool:
    """Download an image from a URL, return True on success."""
    try:
        req = Request(url, headers={"User-Agent": "RadSlice/1.0 (image-sourcing)"})
        with urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 1000:
            logger.warning("Suspiciously small file (%d bytes): %s", len(data), url)
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info("Downloaded %d bytes → %s", len(data), dest)
        return True
    except Exception as e:
        logger.warning("Download failed: %s — %s", url, e)
        return False


def create_symlink(condition_id: str, modality: str, source_filename: str) -> bool:
    """Create openem/ → multicare/ symlink for a condition."""
    multicare_path = CORPUS_DIR / modality / "multicare" / source_filename
    openem_path = CORPUS_DIR / modality / "openem" / f"{condition_id}.png"

    if not multicare_path.exists():
        logger.error("Source file not found: %s", multicare_path)
        return False

    openem_path.parent.mkdir(parents=True, exist_ok=True)
    if openem_path.exists() or openem_path.is_symlink():
        openem_path.unlink()

    openem_path.symlink_to(multicare_path.resolve())
    logger.info("Symlink: %s → %s", openem_path, multicare_path)
    return True


def source_target(target: dict, top: int = 5, dry_run: bool = False) -> dict | None:
    """Source an image for a single target. Returns result dict or None."""
    task_id = target["task_id"]
    condition = target["condition"]
    modality = target["modality"]
    search_terms = target.get("search_terms", condition)

    logger.info("=" * 60)
    logger.info("Sourcing %s: %s (%s)", task_id, condition, modality)

    # Get condition_id from task YAML
    mod_dir = modality if modality != "ultrasound" else "ultrasound"
    task_path = Path(f"configs/tasks/{mod_dir}/{task_id}.yaml")
    if not task_path.exists():
        logger.error("Task YAML not found: %s", task_path)
        return None

    with open(task_path) as f:
        task = yaml.safe_load(f)
    condition_id = task["condition_id"]

    # Check if image already exists
    openem_path = CORPUS_DIR / modality / "openem" / f"{condition_id}.png"
    if openem_path.exists() and not openem_path.is_symlink():
        logger.info("Image already exists (non-symlink): %s — skipping", openem_path)
        return {"task_id": task_id, "status": "exists", "condition_id": condition_id}

    # Discover candidates
    candidates = discover_candidates(search_terms, modality, top=top)
    if not candidates:
        # Retry with just condition name
        logger.info("No candidates with search_terms, retrying with condition name...")
        candidates = discover_candidates(condition, modality, top=top)
    if not candidates:
        logger.warning("No candidates found for %s", task_id)
        return {"task_id": task_id, "status": "no_candidates", "condition_id": condition_id}

    logger.info("Found %d candidates for %s", len(candidates), task_id)
    for i, c in enumerate(candidates):
        logger.info(
            "  [%d] score=%.2f pmcid=%s caption=%s",
            i,
            c.get("caption_score", 0),
            c["pmcid"],
            c["caption"][:80],
        )

    if dry_run:
        return {
            "task_id": task_id,
            "status": "dry_run",
            "condition_id": condition_id,
            "n_candidates": len(candidates),
            "top_candidate": candidates[0]["pmcid"] if candidates else None,
        }

    # Try downloading candidates in order
    for c in candidates:
        url = c.get("cdn_url") or c.get("url")
        if not url:
            continue

        pmcid = c["pmcid"].lower()
        fig_id = c.get("source_id", "").split("_")[-1] or "fig1"
        filename = f"{condition_id}-{pmcid}-{fig_id}.png"
        dest = CORPUS_DIR / modality / "multicare" / filename

        if dest.exists():
            logger.info("Already downloaded: %s", dest)
        else:
            success = download_image(url, dest)
            if not success:
                time.sleep(0.5)
                continue

        # Create symlink
        create_symlink(condition_id, modality, filename)

        return {
            "task_id": task_id,
            "status": "sourced",
            "condition_id": condition_id,
            "pmcid": c["pmcid"],
            "fig_id": fig_id,
            "filename": filename,
            "caption": c["caption"][:200],
            "caption_score": c.get("caption_score", 0),
        }

    logger.warning("All download attempts failed for %s", task_id)
    return {"task_id": task_id, "status": "download_failed", "condition_id": condition_id}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 2 sourcing: US + MRI")
    parser.add_argument("--dry-run", action="store_true", help="Search only, don't download")
    parser.add_argument("--top", type=int, default=5, help="Max candidates per condition")
    parser.add_argument(
        "--modality", choices=["ultrasound", "mri"], help="Source only one modality"
    )
    args = parser.parse_args()

    targets = TARGETS
    if args.modality:
        targets = [t for t in TARGETS if t["modality"] == args.modality]

    results = []
    for target in targets:
        result = source_target(target, top=args.top, dry_run=args.dry_run)
        if result:
            results.append(result)
        time.sleep(1.0)  # Rate limiting between conditions

    # Summary
    sourced = [r for r in results if r["status"] == "sourced"]
    failed = [r for r in results if r["status"] in ("no_candidates", "download_failed")]
    existing = [r for r in results if r["status"] == "exists"]

    print("\n" + "=" * 60)
    print("Phase 2 Sourcing Summary")
    print(f"  Sourced: {len(sourced)}")
    print(f"  Already existed: {len(existing)}")
    print(f"  Failed: {len(failed)}")
    print(f"  Total: {len(results)}")

    if sourced:
        print("\nSourced:")
        for r in sourced:
            print(f"  {r['task_id']}: {r['condition_id']} ← {r['pmcid']} ({r['filename']})")

    if failed:
        print("\nFailed (need manual sourcing):")
        for r in failed:
            print(f"  {r['task_id']}: {r['condition_id']} — {r['status']}")


if __name__ == "__main__":
    main()
