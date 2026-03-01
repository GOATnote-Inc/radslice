"""Fetch corpus images from sources with checksum verification.

Supports per-source downloaders for OmniMedVQA, MediConfusion, VinDr-CXR,
Eurorad, and RadImageNet. For the smoke test, OmniMedVQA covers all 4 modalities.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import urllib.request
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_manifest(path: str | Path = "corpus/manifest.yaml") -> dict:
    """Load the corpus manifest."""
    with open(path) as f:
        return yaml.safe_load(f)


def load_image_sources(path: str | Path = "corpus/image_sources.yaml") -> dict:
    """Load per-image source mappings."""
    with open(path) as f:
        return yaml.safe_load(f)


def verify_checksum(file_path: Path, expected_sha256: str) -> bool:
    """Verify SHA-256 checksum of a downloaded file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest() == expected_sha256


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


# --- Per-source downloaders ---


def _download_url(url: str, dest: Path, timeout: int = 60) -> bool:
    """Download a single URL to dest. Returns True on success."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "RadSlice/0.1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return True
    except Exception as e:
        logger.error("Failed to download %s: %s", url, e)
        return False


def _download_omnimedvqa(
    images: dict[str, dict], output_dir: Path, dry_run: bool = False
) -> dict[str, int]:
    """Download images sourced from OmniMedVQA (HuggingFace open access)."""
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    entries = {k: v for k, v in images.items() if v.get("source") == "omnimedvqa-open"}

    if not entries:
        return stats

    logger.info("OmniMedVQA: %d images to fetch", len(entries))

    for image_ref, info in entries.items():
        dest = output_dir / image_ref
        if dest.exists():
            # Verify checksum if available
            expected = info.get("sha256")
            if expected and verify_checksum(dest, expected):
                stats["skipped"] += 1
                continue
            elif expected:
                logger.warning("Checksum mismatch for %s, re-downloading", image_ref)

        if dry_run:
            logger.info("  [dry-run] Would download: %s", image_ref)
            stats["skipped"] += 1
            continue

        url = info.get("url")
        if not url:
            logger.warning("No URL for %s, skipping", image_ref)
            stats["failed"] += 1
            continue

        if _download_url(url, dest):
            # Verify checksum after download
            expected = info.get("sha256")
            if expected and not verify_checksum(dest, expected):
                logger.error("Checksum mismatch after download: %s", image_ref)
                dest.unlink(missing_ok=True)
                stats["failed"] += 1
            else:
                stats["downloaded"] += 1
        else:
            stats["failed"] += 1

    return stats


def _download_mediconfusion(
    images: dict[str, dict], output_dir: Path, dry_run: bool = False
) -> dict[str, int]:
    """Download images sourced from MediConfusion (GitHub releases)."""
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    entries = {k: v for k, v in images.items() if v.get("source") == "mediconfusion"}

    for image_ref, info in entries.items():
        dest = output_dir / image_ref
        if dest.exists():
            stats["skipped"] += 1
            continue
        if dry_run:
            stats["skipped"] += 1
            continue
        url = info.get("url")
        if url and _download_url(url, dest):
            stats["downloaded"] += 1
        else:
            stats["failed"] += 1

    return stats


def _download_vindr(
    images: dict[str, dict], output_dir: Path, dry_run: bool = False
) -> dict[str, int]:
    """Download images from VinDr-CXR (requires PhysioNet credentials)."""
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    entries = {k: v for k, v in images.items() if v.get("source") == "vindr-cxr"}

    if entries:
        logger.warning(
            "VinDr-CXR requires PhysioNet credentials. "
            "%d images need manual download from https://physionet.org/content/vindr-cxr/",
            len(entries),
        )
    for image_ref in entries:
        dest = output_dir / image_ref
        if dest.exists():
            stats["skipped"] += 1
        else:
            stats["failed"] += 1

    return stats


def _download_eurorad(
    images: dict[str, dict], output_dir: Path, dry_run: bool = False
) -> dict[str, int]:
    """Download images from Eurorad case reports."""
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    entries = {k: v for k, v in images.items() if v.get("source") == "eurorad"}

    for image_ref, info in entries.items():
        dest = output_dir / image_ref
        if dest.exists():
            stats["skipped"] += 1
            continue
        if dry_run:
            stats["skipped"] += 1
            continue
        url = info.get("url")
        if url and _download_url(url, dest):
            stats["downloaded"] += 1
        else:
            stats["failed"] += 1

    return stats


def _download_radimagenet(
    images: dict[str, dict], output_dir: Path, dry_run: bool = False
) -> dict[str, int]:
    """Download images from RadImageNet."""
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    entries = {k: v for k, v in images.items() if v.get("source") == "radimagenet"}

    for image_ref, info in entries.items():
        dest = output_dir / image_ref
        if dest.exists():
            stats["skipped"] += 1
            continue
        if dry_run:
            stats["skipped"] += 1
            continue
        url = info.get("url")
        if url and _download_url(url, dest):
            stats["downloaded"] += 1
        else:
            stats["failed"] += 1

    return stats


def _download_multicare(
    images: dict[str, dict], output_dir: Path, dry_run: bool = False
) -> dict[str, int]:
    """Download images from MultiCaRe (PubMed Central open-access clinical case images).

    MultiCaRe provides curated clinical case images from open-access PubMed Central
    articles. Images are fetched directly via PMC figure URLs.
    """
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    entries = {k: v for k, v in images.items() if v.get("source") == "multicare"}

    if not entries:
        return stats

    logger.info("MultiCaRe: %d images to fetch", len(entries))

    for image_ref, info in entries.items():
        dest = output_dir / image_ref
        if dest.exists():
            expected = info.get("sha256")
            if expected and verify_checksum(dest, expected):
                stats["skipped"] += 1
                continue
            elif expected:
                logger.warning("Checksum mismatch for %s, re-downloading", image_ref)
            else:
                # No checksum to verify — trust existing file
                stats["skipped"] += 1
                continue

        if dry_run:
            logger.info("  [dry-run] Would download: %s", image_ref)
            stats["skipped"] += 1
            continue

        url = info.get("url")
        if not url:
            logger.warning("No URL for %s, skipping", image_ref)
            stats["failed"] += 1
            continue

        if _download_url(url, dest):
            expected = info.get("sha256")
            if expected and not verify_checksum(dest, expected):
                logger.error("Checksum mismatch after download: %s", image_ref)
                dest.unlink(missing_ok=True)
                stats["failed"] += 1
            else:
                stats["downloaded"] += 1
        else:
            stats["failed"] += 1

    return stats


def _download_idc(
    images: dict[str, dict], output_dir: Path, dry_run: bool = False
) -> dict[str, int]:
    """Download DICOM images from NCI Imaging Data Commons (IDC).

    Uses idc-index package if available for efficient bucket access,
    otherwise falls back to direct URLs.
    """
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    entries = {k: v for k, v in images.items() if v.get("source") == "idc"}

    if not entries:
        return stats

    logger.info("IDC: %d images to fetch", len(entries))

    # Try idc-index for batch download
    idc_client = None
    try:
        from idc_index import IDCClient  # type: ignore[import-untyped]
        idc_client = IDCClient()
        logger.info("Using idc-index for IDC downloads")
    except ImportError:
        logger.info("idc-index not installed, using direct URLs for IDC downloads")

    for image_ref, info in entries.items():
        dest = output_dir / image_ref
        if dest.exists():
            expected = info.get("sha256")
            if expected and verify_checksum(dest, expected):
                stats["skipped"] += 1
                continue
            elif expected:
                logger.warning("Checksum mismatch for %s, re-downloading", image_ref)
            else:
                # No checksum to verify — trust existing file
                stats["skipped"] += 1
                continue

        if dry_run:
            logger.info("  [dry-run] Would download: %s", image_ref)
            stats["skipped"] += 1
            continue

        downloaded = False

        # Try idc-index first if available and series_uid is provided
        if idc_client and info.get("series_uid"):
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                idc_client.download_from_selection(
                    seriesInstanceUID=info["series_uid"],
                    downloadDir=str(dest.parent),
                )
                # idc-index downloads to a nested dir structure, find the file
                downloaded = dest.exists()
            except Exception as e:
                logger.warning("idc-index download failed for %s: %s", image_ref, e)

        # Fallback to direct URL
        if not downloaded:
            url = info.get("url")
            if url and _download_url(url, dest):
                downloaded = True

        if downloaded:
            expected = info.get("sha256")
            if expected and not verify_checksum(dest, expected):
                logger.error("Checksum mismatch after download: %s", image_ref)
                dest.unlink(missing_ok=True)
                stats["failed"] += 1
            else:
                stats["downloaded"] += 1
        else:
            stats["failed"] += 1

    return stats


# --- Main entry point ---

_DOWNLOADERS: dict[str, Any] = {
    "omnimedvqa-open": _download_omnimedvqa,
    "mediconfusion": _download_mediconfusion,
    "vindr-cxr": _download_vindr,
    "eurorad": _download_eurorad,
    "radimagenet": _download_radimagenet,
    "multicare": _download_multicare,
    "idc": _download_idc,
}


def download_corpus(
    manifest_path: str = "corpus/manifest.yaml",
    output_dir: str = "corpus/images",
    sources: list[str] | None = None,
    dry_run: bool = False,
    image_sources_path: str = "corpus/image_sources.yaml",
) -> dict[str, int]:
    """Download corpus images. sources=None downloads all.

    Returns aggregate {downloaded, skipped, failed} counts.
    """
    manifest = load_manifest(manifest_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load per-image source mappings
    sources_path = Path(image_sources_path)
    if not sources_path.exists():
        logger.warning("No image_sources.yaml found at %s", sources_path)
        logger.info("Sources: %s", list(manifest.get("sources", {}).keys()))
        logger.info(
            "Target: %d images across %s",
            manifest.get("target_counts", {}).get("total", 200),
            list(manifest.get("target_counts", {}).keys()),
        )
        return {"downloaded": 0, "skipped": 0, "failed": 0}

    image_sources = load_image_sources(sources_path)
    images = image_sources.get("images", {})

    # Filter to requested sources
    active_sources = sources or list(_DOWNLOADERS.keys())

    total = {"downloaded": 0, "skipped": 0, "failed": 0}

    for source_name in active_sources:
        downloader = _DOWNLOADERS.get(source_name)
        if not downloader:
            logger.warning("Unknown source: %s", source_name)
            continue

        logger.info("Processing source: %s", source_name)
        stats = downloader(images, out, dry_run=dry_run)
        for k in total:
            total[k] += stats.get(k, 0)

    logger.info(
        "Download complete: %d downloaded, %d skipped, %d failed",
        total["downloaded"],
        total["skipped"],
        total["failed"],
    )
    return total


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    source_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--source="):
            source_filter = [arg.split("=", 1)[1]]
    stats = download_corpus(dry_run=dry, sources=source_filter)
    print(f"Download stats: {stats}")
