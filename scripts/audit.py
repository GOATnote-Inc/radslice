"""Provenance audit trail for sourced images.

Append-only JSONL log at corpus/audit/provenance.jsonl.
Each record tracks the full lifecycle of an image: sourcing, download, validation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("audit")

DEFAULT_PROVENANCE_PATH = "corpus/audit/provenance.jsonl"


def append_provenance(record: dict, path: str = DEFAULT_PROVENANCE_PATH) -> None:
    """Append a provenance record to the audit log."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    record.setdefault("downloaded_at", datetime.now(timezone.utc).isoformat())
    record.setdefault("validation", None)

    with open(p, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")

    logger.debug("Appended provenance record for %s", record.get("image_ref", "?"))


def update_provenance_validation(
    image_ref: str,
    validation: dict,
    path: str = DEFAULT_PROVENANCE_PATH,
) -> bool:
    """Update the validation field for an existing provenance record.

    Returns True if the record was found and updated, False otherwise.
    """
    p = Path(path)
    if not p.exists():
        logger.warning("Provenance file not found: %s", path)
        return False

    lines = p.read_text().strip().split("\n")
    updated = False
    new_lines = []

    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue

        if rec.get("image_ref") == image_ref:
            rec["validation"] = validation
            rec["validated_at"] = datetime.now(timezone.utc).isoformat()
            updated = True

        new_lines.append(json.dumps(rec, default=str))

    if updated:
        p.write_text("\n".join(new_lines) + "\n")
        logger.debug("Updated provenance validation for %s", image_ref)

    return updated


def build_provenance_record(
    image_ref: str,
    source: str,
    pmcid: str,
    figure_id: str,
    cdn_url: str | None,
    license_info: str,
    article_title: str,
    article_doi: str,
    figure_caption: str,
    caption_score: float,
    sha256: str,
    file_size_bytes: int,
    image_format: str,
    image_dimensions: tuple[int, int] | None,
    condition_id: str,
    task_ids: list[str] | None = None,
) -> dict:
    """Build a complete provenance record."""
    return {
        "image_ref": image_ref,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "pmcid": pmcid,
        "figure_id": figure_id,
        "cdn_url": cdn_url,
        "license": license_info,
        "license_verified_from": "Europe PMC API",
        "article_title": article_title,
        "article_doi": article_doi,
        "figure_caption": figure_caption[:500],
        "caption_score": caption_score,
        "sha256": sha256,
        "file_size_bytes": file_size_bytes,
        "image_format": image_format,
        "image_dimensions": list(image_dimensions) if image_dimensions else None,
        "condition_id": condition_id,
        "task_ids": task_ids or [],
        "validation": None,
    }
