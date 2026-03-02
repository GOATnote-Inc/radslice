#!/usr/bin/env python3
"""Phase 1 image sourcing orchestrator: discover → download → validate.

Automates the full loop of finding, downloading, and validating condition-matched
clinical images from PubMed Central (MultiCaRe source).

Usage:
    # Dry run — discover and score only, no downloads
    python scripts/source_phase1.py --modality xray --dry-run

    # Source 5 X-ray images with validation
    python scripts/source_phase1.py --modality xray --limit 5 --model gpt-5.2

    # Full run targeting 100 images (40 xray + 60 ct)
    python scripts/source_phase1.py --modality all --limit 100 --model gpt-5.2 --resume

    # Download only, skip LLM validation
    python scripts/source_phase1.py --modality ct --limit 10 --skip-validation
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Sibling script imports
sys.path.insert(0, str(Path(__file__).parent))
from audit import append_provenance, build_provenance_record, update_provenance_validation
from discover_multicare import (
    RATE_LIMIT_DELAY,
    discover_candidates,
    format_yaml_entry,
)

logger = logging.getLogger("source_phase1")

# Default split when --modality all
MODALITY_TARGETS = {"xray": 40, "ct": 60}

# Tier 1: conditions where X-ray is the primary or confirmatory diagnostic modality.
# These have key_findings that describe radiographically visible pathology.
# Tier 2 conditions (ECG/CT/echo/labs primary) are skipped for X-ray sourcing.
XRAY_TIER1_CONDITIONS = {
    "active-shooter-response",
    "acute-appendicitis",
    "acute-asthma-exacerbation",
    "acute-cholecystitis",
    "acute-heart-failure",
    "acute-low-back-pain-red-flags",
    "air-embolism",
    "aortic-dissection",
    "aortic-transection",
    "blast-injury",
    "bowel-obstruction",
    "bronchiolitis",
    "cardiac-tamponade",
    "caustic-ingestion",
    "compartment-syndrome",
    "copd-exacerbation",
    "croup",
    "crush-syndrome-mci",
    "dengue-hemorrhagic-fever",
    "epiglottitis",
    "esophageal-foreign-body-impaction",
    "esophageal-perforation",
    "fat-embolism-syndrome",
    "foreign-body-aspiration",
    "fourniers-gangrene",
    "globe-rupture",
    "hemorrhagic-shock",
    "high-altitude-illness",
    "hip-fracture",
    "intussusception",
    "knee-osteoarthritis",
    "major-joint-dislocation",
    "massive-hemoptysis",
    "mesenteric-ischemia",
    "necrotizing-enterocolitis",
    "necrotizing-fasciitis",
    "neonatal-emergencies",
    "neutropenic-fever",
    "non-accidental-trauma",
    "open-fracture",
    "pelvic-fracture",
    "penetrating-chest-trauma",
    "pneumonia",
    "retropharyngeal-abscess",
    "sepsis",
    "sickle-cell-crisis",
    "spinal-cord-compression",
    "spinal-cord-injury",
    "spontaneous-pneumothorax",
    "submersion-injury",
    "tension-pneumothorax",
    "tracheal-disruption",
    "urolithiasis",
}  # 53 of 72 X-ray conditions


def load_image_sources(path: str = "corpus/image_sources.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        return {"schema_version": "2.0", "metadata": {}, "images": {}}
    with open(p) as f:
        return yaml.safe_load(f) or {"schema_version": "2.0", "metadata": {}, "images": {}}


def save_image_sources(data: dict, path: str = "corpus/image_sources.yaml") -> None:
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)


def load_tasks_for_modality(
    modality: str, tasks_dir: str = "configs/tasks"
) -> list[dict]:
    """Load all task YAMLs for a given modality."""
    tasks_path = Path(tasks_dir) / modality
    tasks = []
    if not tasks_path.exists():
        return tasks

    for yaml_path in sorted(tasks_path.rglob("*.yaml")):
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        if raw and "id" in raw and "condition_id" in raw:
            tasks.append(raw)

    return tasks


def get_sourced_condition_ids(sources: dict) -> set[str]:
    """Get condition_ids that already have validated images."""
    sourced = set()
    for _ref, info in sources.get("images", {}).items():
        status = info.get("validation_status", "unsourced")
        if status in ("validated", "downloaded", "sourced"):
            cid = info.get("condition_id", "")
            if cid:
                sourced.add(cid)
    return sourced


def get_validated_condition_ids(sources: dict) -> set[str]:
    """Get condition_ids with pathology_confirmed=true."""
    validated = set()
    for _ref, info in sources.get("images", {}).items():
        if info.get("pathology_confirmed"):
            cid = info.get("condition_id", "")
            if cid:
                validated.add(cid)
    return validated


def compute_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def get_image_dimensions(file_path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size
    except Exception:
        return None


def download_image(url: str, dest: Path, timeout: int = 60) -> bool:
    """Download image from URL. Returns True on success."""
    import shutil
    import urllib.request

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "RadSlice/1.0 (image-sourcing)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            # Reject HTML responses (Europe PMC stub pages)
            if "text/html" in content_type:
                logger.warning("Got HTML instead of image from %s", url)
                return False
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
        # Verify we got something reasonable
        if dest.stat().st_size < 1024:
            logger.warning("Downloaded file too small (%d bytes): %s", dest.stat().st_size, url)
            dest.unlink(missing_ok=True)
            return False
        return True
    except Exception as e:
        logger.error("Download failed %s: %s", url, e)
        return False


async def run_validation(
    task_id: str,
    tasks_dir: str,
    images_dir: str,
    model: str,
) -> dict:
    """Run pathology validation for a single task."""
    from validate_pathology import validate_single

    return await validate_single(
        task_id=task_id,
        tasks_dir=tasks_dir,
        images_dir=images_dir,
        model=model,
        dry_run=False,
    )


def source_modality(
    modality: str,
    limit: int,
    model: str,
    dry_run: bool,
    skip_validation: bool,
    resume: bool,
    tasks_dir: str = "configs/tasks",
    images_dir: str = "corpus/images",
    sources_path: str = "corpus/image_sources.yaml",
) -> dict:
    """Source images for a single modality.

    Returns summary dict with counts and details.
    """
    sources = load_image_sources(sources_path)
    tasks = load_tasks_for_modality(modality, tasks_dir)

    if not tasks:
        logger.warning("No tasks found for modality: %s", modality)
        return {"modality": modality, "sourced": 0, "failed": 0, "skipped": 0, "details": []}

    # Deduplicate by condition_id, keeping first task per condition
    seen: dict[str, dict] = {}
    for t in tasks:
        cid = t["condition_id"]
        if cid not in seen:
            seen[cid] = t

    # Determine which conditions to skip
    skip_cids: set[str] = set()
    if resume:
        skip_cids = get_validated_condition_ids(sources)
    else:
        skip_cids = get_sourced_condition_ids(sources)

    # For X-ray, only source Tier 1 conditions (X-ray is diagnostic)
    tier_filter = None
    if modality == "xray":
        tier_filter = XRAY_TIER1_CONDITIONS
        tier2_count = sum(
            1 for cid in seen if cid not in tier_filter and cid not in skip_cids
        )
        if tier2_count:
            logger.info(
                "Skipping %d Tier 2 conditions (X-ray not primary modality)",
                tier2_count,
            )

    unsourced = [
        (cid, t)
        for cid, t in seen.items()
        if cid not in skip_cids and (tier_filter is None or cid in tier_filter)
    ]

    logger.info(
        "%s: %d tasks, %d unique conditions, %d already sourced, "
        "%d to source (limit %d)",
        modality,
        len(tasks),
        len(seen),
        len(skip_cids),
        len(unsourced),
        limit,
    )

    if dry_run:
        return _dry_run(modality, unsourced, limit)

    sourced = 0
    failed = 0
    skipped = 0
    details: list[dict] = []

    for cid, task in unsourced:
        if sourced >= limit:
            break

        search_term = cid.replace("-", " ")
        task_id = task["id"]
        image_ref = task.get("image_ref", "")

        logger.info("[%d/%d] Discovering images for: %s", sourced + 1, limit, cid)

        try:
            candidates = discover_candidates(search_term, modality, top=5)
        except Exception as e:
            logger.error("Discovery failed for %s: %s", cid, e)
            failed += 1
            details.append({"condition_id": cid, "status": "discovery_failed", "error": str(e)})
            time.sleep(RATE_LIMIT_DELAY)
            continue

        if not candidates:
            logger.warning("No candidates found for %s", cid)
            failed += 1
            details.append({"condition_id": cid, "status": "no_candidates"})
            continue

        # Try each candidate in order of caption_score
        image_sourced = False
        for i, candidate in enumerate(candidates):
            url = candidate.get("cdn_url") or candidate.get("url", "")
            if not url:
                continue

            # Build destination path
            entry = format_yaml_entry(candidate, cid, modality)
            ref = entry["image_ref"]
            dest = Path(images_dir) / ref

            logger.info(
                "  Trying candidate %d/%d (score=%.2f): %s",
                i + 1,
                len(candidates),
                candidate.get("caption_score", 0),
                url[:80],
            )

            # Download
            if not download_image(url, dest):
                logger.warning("  Download failed, trying next candidate")
                time.sleep(RATE_LIMIT_DELAY)
                continue

            # Compute file metadata
            sha = compute_sha256(dest)
            file_size = dest.stat().st_size
            dims = get_image_dimensions(dest)
            fmt = dest.suffix.lstrip(".")

            # Write provenance record
            prov = build_provenance_record(
                image_ref=ref,
                source="multicare",
                pmcid=candidate["pmcid"],
                figure_id=candidate.get("source_id", "").split("_")[-1],
                cdn_url=candidate.get("cdn_url"),
                license_info=candidate.get("license", "CC-BY-4.0"),
                article_title=candidate.get("title", ""),
                article_doi="",
                figure_caption=candidate.get("caption", ""),
                caption_score=candidate.get("caption_score", 0.5),
                sha256=sha,
                file_size_bytes=file_size,
                image_format=fmt,
                image_dimensions=dims,
                condition_id=cid,
                task_ids=[task_id],
            )
            append_provenance(prov)

            # Create symlink so validate_single can find the image
            # at the task's image_ref path
            symlink_created = False
            symlink_path = None
            if image_ref and image_ref != ref:
                symlink_path = Path(images_dir) / image_ref
                symlink_path.parent.mkdir(parents=True, exist_ok=True)
                # Remove stale symlink (broken or pointing to wrong image)
                if symlink_path.is_symlink() or symlink_path.exists():
                    symlink_path.unlink()
                try:
                    symlink_path.symlink_to(dest.resolve())
                    symlink_created = True
                except OSError as e:
                    logger.warning("  Symlink failed: %s", e)

            # Validation
            if skip_validation:
                validation_result = "skipped"
                passed = True
            else:
                logger.info("  Validating pathology with %s...", model)
                try:
                    result = asyncio.run(
                        run_validation(task_id, tasks_dir, images_dir, model)
                    )
                    validation_result = result.get("overall", "FAIL")
                    passed = validation_result == "PASS"

                    # Update provenance with validation
                    update_provenance_validation(ref, {
                        "model": model,
                        "overall": validation_result,
                        "confidence": result.get("confidence", 0.0),
                        "notes": result.get("notes", ""),
                    })
                except Exception as e:
                    logger.error("  Validation error: %s", e)
                    validation_result = "error"
                    passed = False

            if passed:
                # Update image_sources.yaml
                sources = load_image_sources(sources_path)  # Re-read for safety
                images = sources.setdefault("images", {})
                entry_data = entry["entry"]
                entry_data["sha256"] = sha
                vstatus = "validated" if not skip_validation else "downloaded"
                entry_data["validation_status"] = vstatus
                entry_data["pathology_confirmed"] = not skip_validation
                images[ref] = entry_data
                save_image_sources(sources, sources_path)
                sourced += 1
                image_sourced = True

                details.append({
                    "condition_id": cid,
                    "status": "sourced",
                    "image_ref": ref,
                    "caption_score": candidate.get("caption_score", 0),
                    "validation": validation_result,
                    "sha256": sha,
                })

                logger.info(
                    "  PASS — Sourced %d/%d %s (%.1f%%)",
                    sourced,
                    limit,
                    modality,
                    sourced / limit * 100,
                )
                break
            else:
                logger.info(
                    "  FAIL — validation=%s, trying next candidate",
                    validation_result,
                )
                # Clean up failed download and symlink
                dest.unlink(missing_ok=True)
                if symlink_created and symlink_path:
                    symlink_path.unlink(missing_ok=True)
                time.sleep(RATE_LIMIT_DELAY)

        if not image_sourced:
            failed += 1
            details.append({"condition_id": cid, "status": "all_candidates_failed"})
            logger.warning("  All candidates failed for %s", cid)

    return {
        "modality": modality,
        "sourced": sourced,
        "failed": failed,
        "skipped": skipped,
        "total_conditions": len(seen),
        "details": details,
    }


def _dry_run(
    modality: str, unsourced: list[tuple[str, dict]], limit: int
) -> dict:
    """Dry run: discover and score candidates without downloading."""
    details: list[dict] = []
    for i, (cid, task) in enumerate(unsourced[:limit]):
        search_term = cid.replace("-", " ")
        logger.info("[%d/%d] Discovering for: %s", i + 1, min(limit, len(unsourced)), cid)

        try:
            candidates = discover_candidates(search_term, modality, top=3)
        except Exception as e:
            logger.error("Discovery failed for %s: %s", cid, e)
            details.append({"condition_id": cid, "status": "discovery_failed"})
            continue

        if candidates:
            best = candidates[0]
            details.append({
                "condition_id": cid,
                "status": "dry_run",
                "n_candidates": len(candidates),
                "best_score": best.get("caption_score", 0),
                "best_caption": best.get("caption", "")[:100],
                "best_url": (best.get("cdn_url") or best.get("url", ""))[:80],
            })
        else:
            details.append({"condition_id": cid, "status": "no_candidates"})

        time.sleep(RATE_LIMIT_DELAY)

    return {
        "modality": modality,
        "sourced": 0,
        "failed": 0,
        "skipped": 0,
        "dry_run": True,
        "details": details,
    }


def write_summary(results: list[dict], output_dir: str = "results") -> str:
    """Write summary JSON to results directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out / f"sourcing-phase1-{ts}.json"

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "total_sourced": sum(r.get("sourced", 0) for r in results),
        "total_failed": sum(r.get("failed", 0) for r in results),
    }

    with open(path, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("Summary written to %s", path)
    return str(path)


def update_metadata(sources_path: str = "corpus/image_sources.yaml") -> None:
    """Update image_sources.yaml metadata block."""
    sources = load_image_sources(sources_path)
    images = sources.get("images", {})

    total_sourced = sum(
        1
        for info in images.values()
        if info.get("validation_status") in ("sourced", "downloaded", "validated")
    )
    total_validated = sum(
        1 for info in images.values() if info.get("pathology_confirmed")
    )

    meta = sources.setdefault("metadata", {})
    meta["total_sourced"] = total_sourced
    meta["total_validated"] = total_validated
    meta["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    save_image_sources(sources, sources_path)
    logger.info("Updated metadata: sourced=%d, validated=%d", total_sourced, total_validated)


def main():
    parser = argparse.ArgumentParser(
        description="Phase 1 image sourcing: discover → download → validate"
    )
    parser.add_argument(
        "--modality",
        choices=["xray", "ct", "all"],
        required=True,
        help="Target modality (or 'all' for both xray+ct)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max total images to source (default: 100)",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.2",
        help="Vision LLM for validation (default: gpt-5.2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and score only — no downloads or API calls",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Download only, skip LLM validation",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip conditions already validated in image_sources.yaml",
    )
    parser.add_argument("--tasks-dir", default="configs/tasks")
    parser.add_argument("--images-dir", default="corpus/images")
    parser.add_argument("--sources", default="corpus/image_sources.yaml")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    if args.modality == "all":
        modalities = list(MODALITY_TARGETS.keys())
        # Split limit proportionally
        total = sum(MODALITY_TARGETS.values())
        limits = {
            mod: max(1, int(args.limit * MODALITY_TARGETS[mod] / total))
            for mod in modalities
        }
    else:
        modalities = [args.modality]
        limits = {args.modality: args.limit}

    results = []
    for mod in modalities:
        mod_limit = limits[mod]
        logger.info("=== Sourcing %s (limit=%d) ===", mod, mod_limit)

        result = source_modality(
            modality=mod,
            limit=mod_limit,
            model=args.model,
            dry_run=args.dry_run,
            skip_validation=args.skip_validation,
            resume=args.resume,
            tasks_dir=args.tasks_dir,
            images_dir=args.images_dir,
            sources_path=args.sources,
        )
        results.append(result)

    # Print summary
    print("\n" + "=" * 60)
    print("Phase 1 Sourcing Summary")
    print("=" * 60)
    for r in results:
        mod = r["modality"]
        s = r.get("sourced", 0)
        f = r.get("failed", 0)
        total = s + f
        pct = s / total * 100 if total else 0
        dry = " [DRY RUN]" if r.get("dry_run") else ""
        print(f"  {mod:12s}  sourced: {s:3d}  failed: {f:3d}  ({pct:.1f}%){dry}")

    total_sourced = sum(r.get("sourced", 0) for r in results)
    total_failed = sum(r.get("failed", 0) for r in results)
    print(f"\n  Total:        sourced: {total_sourced:3d}  failed: {total_failed:3d}")

    # Write summary JSON
    if not args.dry_run:
        summary_path = write_summary(results)
        print(f"\n  Summary: {summary_path}")

        # Update metadata
        update_metadata(args.sources)

    # Print dry-run details
    if args.dry_run:
        print("\nDry Run Details:")
        for r in results:
            for d in r.get("details", []):
                cid = d["condition_id"]
                status = d["status"]
                if status == "dry_run":
                    score = d.get("best_score", 0)
                    n = d.get("n_candidates", 0)
                    cap = d.get("best_caption", "")[:60]
                    print(f"  {cid:40s}  candidates={n}  best_score={score:.2f}  {cap}")
                else:
                    print(f"  {cid:40s}  {status}")


if __name__ == "__main__":
    main()
