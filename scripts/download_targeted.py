#!/usr/bin/env python3
"""Download specific PMC figures for Phase 2 sourcing.

Targeted downloads from verified case reports — replaces automated pipeline
which had ~84% false positive rate (diagrams/flowcharts instead of imaging).
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import append_provenance, build_provenance_record

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("download_targeted")

CORPUS_DIR = Path("corpus/images")
NCBI_RATE_LIMIT = 0.5

# Verified CC-BY case reports with real clinical images
# Format: (task_id, condition_id, modality, pmcid, fig_id_hint, notes)
TARGETS = [
    # === MRI (6 replacements — all CC-BY 4.0) ===
    (
        "MRI-005",
        "acute-ischemic-stroke",
        "mri",
        "PMC4548688",
        "fig-01",
        "Young stroke patient DWI+FLAIR — CC-BY 4.0",
    ),
    (
        "MRI-023",
        "eclampsia",
        "mri",
        "PMC5445265",
        "Fig1",
        "PRES+HELLP with FLAIR showing posterior white matter edema — CC-BY 4.0",
    ),
    (
        "MRI-040",
        "carbon-monoxide-poisoning",
        "mri",
        "PMC10772852",
        "fig1",
        "Filipino household CO case — 6-panel DWI/ADC/T1/T2/FLAIR/GRE — CC-BY 4.0",
    ),
    (
        "MRI-011",
        "spinal-cord-compression",
        "mri",
        "PMC7930977",
        "Fig2",
        "Plasmacytoma compressing spinal cord — sagittal T2 — CC-BY 4.0",
    ),
    (
        "MRI-003",
        "pericarditis-myocarditis",
        "mri",
        "PMC9539345",
        "fig-01",
        "Vaccine-related myocarditis — cardiac MRI with LGE — CC-BY 4.0",
    ),
    (
        "MRI-014",
        "fat-embolism-syndrome",
        "mri",
        "PMC6450253",
        "Fig2",
        "Cerebral fat embolism — DWI starfield pattern — CC-BY 4.0",
    ),
    # === Ultrasound (15 — all CC-BY 4.0 unless noted) ===
    (
        "US-006",
        "cardiac-tamponade",
        "ultrasound",
        "PMC5965178",
        "img-0002",
        "Sub-acute tamponade POCUS — parasternal long axis — CC-BY 4.0",
    ),
    (
        "US-010",
        "ruptured-aaa",
        "ultrasound",
        "PMC6876902",
        "Fig1",
        "POCUS AAA — transverse+longitudinal 8x9cm — CC-BY",
    ),
    (
        "US-024",
        "spontaneous-pneumothorax",
        "ultrasound",
        "PMC6360002",
        "Fig2",
        "Pneumothorax barcode sign M-mode + lung point — CC-BY",
    ),
    (
        "US-026",
        "acute-cholecystitis",
        "ultrasound",
        "PMC3236129",
        "Fig1",
        "Bedside US acalculous cholecystitis — wall thickening >1cm — CC-BY 4.0",
    ),
    (
        "US-066",
        "intussusception",
        "ultrasound",
        "PMC10854881",
        "Fig1",
        "Colocolic intussusception target sign — CC-BY 4.0",
    ),
    (
        "US-073",
        "acute-appendicitis",
        "ultrasound",
        "PMC7676787",
        "img-0001",
        "POCUS appendicitis — enlarged >1cm non-compressible — CC-BY 4.0",
    ),
    (
        "US-046",
        "urolithiasis",
        "ultrasound",
        "PMC9523545",
        "Fig1",
        "Hydronephrosis + perinephric fluid — CC-BY-NC-ND 4.0",
    ),
    (
        "US-036",
        "ovarian-torsion",
        "ultrasound",
        "PMC9806735",
        "Fig1",
        "Doppler ovarian torsion — restricted flow — CC-BY",
    ),
    (
        "US-042",
        "testicular-torsion",
        "ultrasound",
        "PMC7872624",
        "img-0002",
        "Monorchid testicular torsion — spectral Doppler — CC-BY 4.0",
    ),
    (
        "US-053",
        "deep-vein-thrombosis",
        "ultrasound",
        "PMC9142702",
        "Fig2",
        "Two-point compression US — non-compressible popliteal vein — CC-BY-NC-ND",
    ),
    (
        "US-050",
        "retinal-detachment",
        "ultrasound",
        "PMC6084687",
        "Fig1",
        "Bedside ocular US — hyperechoic undulating membrane — CC-BY",
    ),
    (
        "US-082",
        "necrotizing-fasciitis",
        "ultrasound",
        "PMC10332782",
        "Fig1",
        "POCUS NF — subcutaneous air + dirty shadowing — CC-BY 4.0",
    ),
    (
        "US-069",
        "pyloric-stenosis",
        "ultrasound",
        "PMC5965224",
        "img-0001",
        "POCUS pyloric stenosis — elongated channel >17mm — CC-BY 4.0",
    ),
    (
        "US-019",
        "hemorrhagic-shock",
        "ultrasound",
        "PMC7676810",
        "img-0001",
        "FAST — free fluid Morison's pouch — CC-BY 4.0",
    ),
    (
        "US-034",
        "ectopic-pregnancy",
        "ultrasound",
        "PMC9408466",
        "Fig1",
        "Transvaginal US — advanced tubal ectopic — CC-BY 4.0",
    ),
]


# rc1.1 IMAGE_MISMATCH remediation: 5 re-sourced images (CT-097 deferred)
# All CC-BY 4.0 or CC-BY. Manually curated from Europe PMC search.
# Format: (task_id, condition_id, modality, pmcid, fig_hint, cdn_url, notes)
TARGETS_RC11 = [
    (
        "CT-027",
        "foreign-body-aspiration",
        "ct",
        "PMC12444646",
        "Fig2",
        "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/a12f/12444646/293fc0921e59/RCR2-13-e70346-g002.jpg",
        "Chest CT endobronchial mukago in R bronchus intermedius — CC-BY 4.0",
    ),
    (
        "CT-048",
        "open-fracture",
        "ct",
        "PMC12686621",
        "Fig1",
        "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/e26d/12686621/e262b547c787/gr1.jpg",
        "Gustilo IIIB open tibial fracture: clinical + XR + 3D CTA — CC-BY 4.0",
    ),
    (
        "MRI-007",
        "cauda-equina-syndrome",
        "mri",
        "PMC12854390",
        "Fig1",
        "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/bb7f/12854390/fce4b37897da/cureus-0017-00000100428-i01.jpg",
        "Sagittal T2 massive L5-S1 disc extrusion compressing cauda equina — CC-BY 4.0",
    ),
    (
        "MRI-031",
        "hsv-encephalitis",
        "mri",
        "PMC12126961",
        "Fig1",
        "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/6c41/12126961/8b814060601b/cureus-0017-00000083346-i01.jpg",
        "Axial FLAIR bilateral temporal lobe hyperintensity HSV-1 — CC-BY 4.0",
    ),
    (
        "MRI-035",
        "spinal-epidural-abscess",
        "mri",
        "PMC8723735",
        "Fig1",
        "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/c9e9/8723735/3ea73a476846/cureus-0013-00000020100-i01.jpg",
        "Cervical T1/T2/post-gad: rim-enhancing epidural abscess + cord compression — CC-BY 4.0",
    ),
]


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_page(url: str) -> str | None:
    """Fetch a web page and return its HTML."""
    try:
        req = Request(url, headers={"User-Agent": "RadSlice/1.0 (image-sourcing)"})
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def find_figure_urls(pmcid: str, fig_hint: str) -> list[str]:
    """Find all figure image URLs from a PMC article page."""
    article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
    html = fetch_page(article_url)
    if not html:
        return []

    # Find all CDN blob URLs
    cdn_urls = re.findall(r'src="(https://cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^"]+)"', html)

    # Also find figure-specific URLs
    fig_urls = re.findall(
        r'src="(https://[^"]*(?:'
        + re.escape(pmcid.lower().replace("pmc", ""))
        + r'|pmc)[^"]*\.(?:jpg|png|gif|jpeg)[^"]*)"',
        html,
        re.IGNORECASE,
    )

    all_urls = list(dict.fromkeys(cdn_urls + fig_urls))  # dedup, preserve order

    if not all_urls:
        # Try figure-specific page
        fig_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/figure/{fig_hint}/"
        html2 = fetch_page(fig_url)
        if html2:
            cdn_urls2 = re.findall(
                r'src="(https://cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^"]+)"', html2
            )
            all_urls.extend(cdn_urls2)

    return all_urls


def download_image(url: str, dest: Path) -> bool:
    """Download an image, return True on success."""
    try:
        req = Request(url, headers={"User-Agent": "RadSlice/1.0 (image-sourcing)"})
        with urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 2000:
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
    """Create openem/ → multicare/ symlink."""
    multicare_path = CORPUS_DIR / modality / "multicare" / source_filename
    openem_path = CORPUS_DIR / modality / "openem" / f"{condition_id}.png"

    if not multicare_path.exists():
        logger.error("Source not found: %s", multicare_path)
        return False

    openem_path.parent.mkdir(parents=True, exist_ok=True)
    if openem_path.exists() or openem_path.is_symlink():
        openem_path.unlink()

    openem_path.symlink_to(multicare_path.resolve())
    logger.info("Symlink: %s → %s", openem_path, multicare_path)
    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Download targeted PMC figures")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--modality", choices=["mri", "ultrasound", "ct"])
    parser.add_argument("--task", help="Download only this task_id")
    parser.add_argument(
        "--rc11",
        action="store_true",
        help="Use rc1.1 IMAGE_MISMATCH remediation target list (5 tasks)",
    )
    args = parser.parse_args()

    if args.rc11:
        targets_raw = TARGETS_RC11
    else:
        targets_raw = TARGETS

    if args.modality:
        targets_raw = [t for t in targets_raw if t[2] == args.modality]
    if args.task:
        targets_raw = [t for t in targets_raw if t[0] == args.task]

    results = {"sourced": [], "failed": [], "skipped": []}

    for entry in targets_raw:
        if args.rc11:
            task_id, condition_id, modality, pmcid, fig_hint, cdn_url, notes = entry
        else:
            task_id, condition_id, modality, pmcid, fig_hint, notes = entry
            cdn_url = None

        logger.info("=" * 60)
        logger.info("%s: %s (%s) — %s", task_id, condition_id, modality, pmcid)

        pmcid_lower = pmcid.lower()
        ext = "jpg"
        filename = f"{condition_id}-{pmcid_lower}-{fig_hint}.{ext}"
        dest = CORPUS_DIR / modality / "multicare" / filename

        # Check if already downloaded
        if dest.exists():
            logger.info("Already downloaded: %s", dest)
            create_symlink(condition_id, modality, filename)
            if args.rc11:
                sha = compute_sha256(dest)
                logger.info("SHA-256: %s", sha)
            results["skipped"].append(task_id)
            continue

        if args.dry_run:
            logger.info("[DRY RUN] Would download from %s", pmcid)
            continue

        # rc11 mode: use pre-verified CDN URL directly
        if args.rc11 and cdn_url:
            success = download_image(cdn_url, dest)
            if success:
                sha = compute_sha256(dest)
                logger.info("SHA-256: %s", sha)
                create_symlink(condition_id, modality, filename)
                # Record provenance
                image_ref = f"{modality}/multicare/{filename}"
                record = build_provenance_record(
                    image_ref=image_ref,
                    source="multicare",
                    pmcid=pmcid,
                    figure_id=fig_hint,
                    cdn_url=cdn_url,
                    license_info="CC-BY 4.0",
                    article_title=notes,
                    article_doi="",
                    figure_caption=notes,
                    caption_score=1.0,
                    sha256=sha,
                    file_size_bytes=dest.stat().st_size,
                    image_format=ext,
                    image_dimensions=None,
                    condition_id=condition_id,
                    task_ids=[task_id],
                )
                append_provenance(record)
                results["sourced"].append(task_id)
            else:
                results["failed"].append(task_id)
            time.sleep(1.0)
            continue

        # Original mode: discover figure URLs from article page
        urls = find_figure_urls(pmcid, fig_hint)
        if not urls:
            logger.warning("No figure URLs found for %s", pmcid)
            results["failed"].append(task_id)
            time.sleep(NCBI_RATE_LIMIT)
            continue

        logger.info("Found %d candidate URLs for %s", len(urls), pmcid)
        for i, u in enumerate(urls[:5]):
            logger.info("  [%d] %s", i, u[:120])

        # Try each URL until one works
        success = False
        for url in urls:
            if dest.exists():
                logger.info("Already downloaded: %s", dest)
                success = True
                break

            if download_image(url, dest):
                success = True
                break

            time.sleep(NCBI_RATE_LIMIT)

        if success:
            create_symlink(condition_id, modality, filename)
            results["sourced"].append(task_id)
        else:
            results["failed"].append(task_id)

        time.sleep(1.0)  # Rate limit

    # Summary
    print(f"\n{'=' * 60}")
    print("Targeted Download Summary")
    print(f"  Sourced: {len(results['sourced'])}")
    print(f"  Skipped: {len(results['skipped'])}")
    print(f"  Failed:  {len(results['failed'])}")

    if results["failed"]:
        print(f"\nFailed: {', '.join(results['failed'])}")


if __name__ == "__main__":
    main()
