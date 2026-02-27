"""Fetch corpus images from sources with checksum verification."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def load_manifest(path: str | Path = "corpus/manifest.yaml") -> dict:
    """Load the corpus manifest."""
    with open(path) as f:
        return yaml.safe_load(f)


def verify_checksum(file_path: Path, expected_sha256: str) -> bool:
    """Verify SHA-256 checksum of a downloaded file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest() == expected_sha256


def download_corpus(
    manifest_path: str = "corpus/manifest.yaml",
    output_dir: str = "corpus/images",
    dry_run: bool = False,
) -> dict:
    """Download all corpus images. Returns {downloaded, skipped, failed}."""
    manifest = load_manifest(manifest_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    stats = {"downloaded": 0, "skipped": 0, "failed": 0}

    logger.info("Corpus download requires dataset-specific downloaders.")
    logger.info("Sources: %s", list(manifest.get("sources", {}).keys()))
    logger.info(
        "Target: %d images across %s",
        manifest.get("target_counts", {}).get("total", 200),
        list(manifest.get("target_counts", {}).keys()),
    )

    if dry_run:
        logger.info("Dry run — no images downloaded.")
        return stats

    # TODO: Implement per-source downloaders
    # - OmniMedVQA: HuggingFace datasets API
    # - MediConfusion: GitHub release download
    # - Eurorad: Web scraping with rate limiting
    # - RadImageNet: Direct download
    # - VinDr-CXR: PhysioNet credentialed download

    logger.warning("Image download not yet implemented. Place images manually in %s", out)
    return stats


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    stats = download_corpus(dry_run=dry)
    print(f"Download stats: {stats}")
