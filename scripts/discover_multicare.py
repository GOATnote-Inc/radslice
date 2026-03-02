#!/usr/bin/env python3
"""Discover condition-matched case images from PubMed Central via Europe PMC API.

Queries open-access case reports with clinical images matching RadSlice conditions.
Outputs candidates in image_sources.yaml format.

Usage:
    # Single condition
    python scripts/discover_multicare.py --condition pneumonia --modality xray --top 5

    # Batch mode: all conditions in a task directory
    python scripts/discover_multicare.py --batch configs/tasks/xray/ --top 3

    # Append results to image_sources.yaml
    python scripts/discover_multicare.py --condition pneumonia --modality xray --append
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import yaml

logger = logging.getLogger("discover_multicare")

# Europe PMC REST API — no auth required
EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPEPMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{id}/fullTextXML"

# Rate limits
RATE_LIMIT_DELAY = 0.12  # seconds between Europe PMC requests
NCBI_RATE_LIMIT = 0.5  # seconds between NCBI fetches (stricter)

MODALITY_KEYWORDS = {
    "xray": ["radiograph", "chest x-ray", "x-ray", "plain film", "CXR"],
    "ct": ["computed tomography", "CT scan", "CT image", "CTPA", "CTA"],
    "mri": ["magnetic resonance", "MRI", "MR image"],
    "ultrasound": ["ultrasound", "sonography", "echocardiogram", "FAST exam"],
}

# Caption scoring terms
_REJECT_TERMS = [
    "flowchart", "flow chart", "diagram", "schematic",
    "bar chart", "pie chart", "bar graph", "line graph",
    "timeline", "prisma", "forest plot",
    "kaplan-meier", "algorithm", "decision tree",
]
_LOW_TERMS = [
    "histology", "pathology specimen", "gross specimen", "clinical photograph",
    "ecg", "electrocardiogram", "laboratory", "fundus photo", "slit-lamp",
    "dermatoscopy",
]
_COMPOSITE_TERMS = ["panels a", "serial", "composite", "comparison"]
_COMPOSITE_RE = re.compile(r"\([a-f]\)|[a-f]-[a-f]")
_IMAGING_TERMS = [
    "radiograph", "chest x-ray", "x-ray", "cxr", "ct scan",
    "computed tomography", "ctpa", "cta", "mri", "ultrasound",
    "sonography", "echocardiogram",
]


def resolve_cdn_url(pmcid: str, fig_id: str, href: str) -> str | None:
    """Resolve a PMC figure to its NCBI CDN URL.

    Europe PMC figure URLs return HTML stubs. NCBI CDN URLs serve actual image
    bytes. Tries the figure page first, then falls back to the article page.
    """
    # Try figure page first
    fig_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/figure/{fig_id}/"
    cdn_url = _fetch_cdn_from_page(fig_url, href)
    if cdn_url:
        return cdn_url

    time.sleep(NCBI_RATE_LIMIT)

    # Fallback: search article page for the href filename
    article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
    cdn_url = _fetch_cdn_from_page(article_url, href)
    return cdn_url


def _fetch_cdn_from_page(page_url: str, href: str) -> str | None:
    """Fetch a PMC page and extract the CDN URL for the given figure href."""
    try:
        req = Request(page_url, headers={"User-Agent": "RadSlice/1.0 (image-sourcing)"})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", page_url, e)
        return None

    # Look for CDN blob URL
    match = re.search(r'src="(https://cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^"]+)"', html)
    if match:
        return match.group(1)

    # Fallback: look for the href filename in any img src
    if href:
        filename = href.rsplit("/", 1)[-1]
        pattern = rf'src="(https://[^"]*{re.escape(filename)}[^"]*)"'
        match = re.search(pattern, html)
        if match:
            return match.group(1)

    return None


def score_caption(caption: str, condition_name: str, modality: str) -> float:
    """Score a figure caption for relevance to the target condition and modality.

    Returns 0.0–1.0. Higher is better. 0.0 means definite reject.
    """
    cap = caption.lower()

    # Reject non-imaging content
    for term in _REJECT_TERMS:
        if term in cap:
            return 0.0

    score = 0.5

    # Low-value content penalty
    for term in _LOW_TERMS:
        if term in cap:
            score = min(score, 0.2)
            break

    # Composite image penalty
    is_composite = any(term in cap for term in _COMPOSITE_TERMS) or bool(
        _COMPOSITE_RE.search(cap)
    )
    if is_composite:
        score -= 0.2

    # Imaging modality boost
    if any(term in cap for term in _IMAGING_TERMS):
        score += 0.4

    # Condition name match boost
    condition_words = re.split(r"[-\s]+", condition_name.lower())
    matching = sum(1 for w in condition_words if len(w) > 2 and w in cap)
    if matching > 0:
        score += 0.3

    return max(0.0, min(1.0, score))


def search_europepmc(
    condition: str,
    modality: str | None = None,
    max_results: int = 25,
) -> list[dict]:
    """Search Europe PMC for open-access case reports with images."""
    modality_clause = ""
    if modality and modality in MODALITY_KEYWORDS:
        kw_or = " OR ".join(f'"{k}"' for k in MODALITY_KEYWORDS[modality])
        modality_clause = f" AND ({kw_or})"

    query = f'"{condition}" AND "case report"{modality_clause} AND OPEN_ACCESS:y'

    params = {
        "query": query,
        "format": "json",
        "pageSize": str(min(max_results, 25)),
        "resultType": "core",
        "sort": "CITED desc",
    }

    url = EUROPEPMC_SEARCH + "?" + "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())

    logger.info("Searching Europe PMC: %s", query)
    logger.debug("URL: %s", url)

    req = Request(url, headers={"User-Agent": "RadSlice/1.0 (image-sourcing)"})
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    results = data.get("resultList", {}).get("result", [])
    logger.info("Found %d results", len(results))
    return results


def fetch_fulltext_xml(pmcid: str) -> ET.Element | None:
    """Fetch full-text XML for a PMC article."""
    url = EUROPEPMC_FULLTEXT.format(id=pmcid)
    logger.debug("Fetching full text: %s", url)

    try:
        req = Request(url, headers={"User-Agent": "RadSlice/1.0 (image-sourcing)"})
        with urlopen(req, timeout=30) as resp:
            xml_text = resp.read()
        return ET.fromstring(xml_text)
    except Exception as e:
        logger.warning("Failed to fetch full text for %s: %s", pmcid, e)
        return None


def extract_figures(root: ET.Element, pmcid: str) -> list[dict]:
    """Extract figure metadata from PMC full-text XML."""
    figures = []

    for fig in root.iter("fig"):
        fig_id = fig.get("id", "")
        label_elem = fig.find("label")
        caption_elem = fig.find("caption")

        label = label_elem.text if label_elem is not None and label_elem.text else ""
        caption = ""
        if caption_elem is not None:
            # Get all text content from caption, including nested elements
            caption = "".join(caption_elem.itertext()).strip()

        # Look for graphic element with xlink:href
        graphic = fig.find(".//{http://www.w3.org/1999/xlink}href/..")
        if graphic is None:
            graphic = fig.find(".//graphic")

        href = ""
        if graphic is not None:
            href = graphic.get("{http://www.w3.org/1999/xlink}href", "")

        # Build PMC figure URL (Europe PMC as fallback)
        url = ""
        cdn_url = None
        if href:
            url = f"https://europepmc.org/articles/{pmcid}/bin/{href}.jpg"
            # Try to resolve actual CDN URL from NCBI
            cdn_url = resolve_cdn_url(pmcid, fig_id, href)
            time.sleep(NCBI_RATE_LIMIT)
            if cdn_url:
                logger.debug("Resolved CDN URL for %s/%s: %s", pmcid, fig_id, cdn_url)

        figures.append(
            {
                "fig_id": fig_id,
                "label": label,
                "caption": caption[:500],  # Truncate long captions
                "url": url,
                "cdn_url": cdn_url,
                "href": href,
            }
        )

    return figures


def filter_figures_by_modality(
    figures: list[dict], modality: str, condition: str = ""
) -> list[dict]:
    """Filter and score figures by caption relevance.

    Uses score_caption() to assign a relevance score to each figure.
    Figures with score > 0.0 are included, sorted by score descending.
    Falls back to all figures if none score above 0.0.
    """
    for fig in figures:
        fig["caption_score"] = score_caption(fig["caption"], condition, modality)

    scored = [f for f in figures if f["caption_score"] > 0.0]
    if not scored:
        # Fall back to all figures with a default score
        for fig in figures:
            fig.setdefault("caption_score", 0.1)
        return figures

    scored.sort(key=lambda f: f["caption_score"], reverse=True)
    return scored


def discover_candidates(
    condition: str,
    modality: str | None = None,
    top: int = 5,
) -> list[dict]:
    """Discover candidate images for a condition.

    Returns list of candidate dicts ready for image_sources.yaml.
    """
    results = search_europepmc(condition, modality)
    time.sleep(RATE_LIMIT_DELAY)

    candidates = []

    for article in results[:10]:  # Check top 10 articles
        pmcid = article.get("pmcid", "")
        if not pmcid:
            continue

        title = article.get("title", "")
        license_info = article.get("license", "")

        # Only CC-BY variants
        is_cc_by = "cc-by" in license_info.lower() or "cc by" in license_info.lower()
        if not is_cc_by and license_info:
            logger.debug("Skipping %s — license: %s", pmcid, license_info)
            continue

        root = fetch_fulltext_xml(pmcid)
        time.sleep(RATE_LIMIT_DELAY)

        if root is None:
            continue

        figures = extract_figures(root, pmcid)
        if modality:
            figures = filter_figures_by_modality(figures, modality, condition)

        for fig in figures:
            if not fig["url"] and not fig.get("cdn_url"):
                continue

            candidates.append(
                {
                    "pmcid": pmcid,
                    "source_id": f"{pmcid}_{fig['fig_id']}",
                    "title": title,
                    "caption": fig["caption"],
                    "url": fig["url"],
                    "cdn_url": fig.get("cdn_url"),
                    "caption_score": fig.get("caption_score", 0.5),
                    "license": license_info or "CC-BY (open access)",
                    "fig_label": fig["label"],
                    "condition": condition,
                    "modality": modality or "unknown",
                }
            )

        if len(candidates) >= top:
            break

    # Sort by caption_score descending before truncating
    candidates.sort(key=lambda c: c.get("caption_score", 0), reverse=True)
    return candidates[:top]


def format_yaml_entry(candidate: dict, condition_id: str, modality: str) -> dict:
    """Format a candidate as an image_sources.yaml entry."""
    safe_pmcid = candidate["pmcid"].lower()
    fig_id = candidate.get("source_id", "").split("_")[-1] or "fig1"
    image_ref = f"{modality}/multicare/{condition_id}-{safe_pmcid}-{fig_id}.png"

    # Prefer CDN URL over Europe PMC URL
    url = candidate.get("cdn_url") or candidate["url"]

    return {
        "image_ref": image_ref,
        "entry": {
            "source": "multicare",
            "source_id": candidate["source_id"],
            "original_format": "png",
            "license": candidate["license"],
            "url": url,
            "condition_id": condition_id,
            "task_ids": [],
            "validation_status": "sourced",
            "pathology_confirmed": False,
            "caption_score": candidate.get("caption_score", 0.5),
            "notes": candidate["caption"][:200],
        },
    }


def batch_discover(
    tasks_dir: str, modality: str | None = None, top: int = 3
) -> list[dict]:
    """Batch discovery for all conditions in a tasks directory."""
    tasks_path = Path(tasks_dir)
    seen_conditions: set[str] = set()
    all_candidates: list[dict] = []

    for yaml_path in sorted(tasks_path.rglob("*.yaml")):
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        if not raw or "condition_id" not in raw:
            continue

        cond_id = raw["condition_id"]
        task_mod = raw.get("modality", modality or "unknown")
        if cond_id in seen_conditions:
            continue
        seen_conditions.add(cond_id)

        # Use condition_id as search term (replace hyphens with spaces)
        search_term = cond_id.replace("-", " ")
        logger.info("Discovering images for: %s (%s)", cond_id, task_mod)

        try:
            candidates = discover_candidates(search_term, task_mod, top=top)
            for c in candidates:
                entry = format_yaml_entry(c, cond_id, task_mod)
                entry["task_id"] = raw.get("id", "")
                all_candidates.append(entry)
        except Exception as e:
            logger.error("Failed to discover for %s: %s", cond_id, e)

        time.sleep(RATE_LIMIT_DELAY)

    return all_candidates


def append_to_sources(candidates: list[dict], sources_path: str = "corpus/image_sources.yaml"):
    """Append candidate entries to image_sources.yaml."""
    path = Path(sources_path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {"schema_version": "2.0", "metadata": {}, "images": {}}

    images = data.setdefault("images", {})
    added = 0
    for c in candidates:
        ref = c["image_ref"]
        if ref not in images:
            entry = c["entry"]
            # Add task_id if available
            if c.get("task_id"):
                entry["task_ids"] = [c["task_id"]]
            images[ref] = entry
            added += 1

    # Update metadata
    data.setdefault("metadata", {})["last_updated"] = "2026-03-02"

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)

    logger.info("Added %d new entries to %s", added, sources_path)
    return added


def main():
    parser = argparse.ArgumentParser(
        description="Discover condition-matched case images from PubMed Central"
    )
    parser.add_argument("--condition", help="Condition ID or name (e.g., pneumonia)")
    parser.add_argument(
        "--modality",
        choices=["xray", "ct", "mri", "ultrasound"],
        help="Target modality",
    )
    parser.add_argument("--top", type=int, default=5, help="Max candidates per condition")
    parser.add_argument("--batch", help="Batch mode: path to task YAML directory")
    parser.add_argument(
        "--append", action="store_true", help="Append results to image_sources.yaml"
    )
    parser.add_argument(
        "--sources", default="corpus/image_sources.yaml", help="Image sources YAML path"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    if not args.condition and not args.batch:
        parser.error("Provide --condition or --batch")

    if args.batch:
        candidates = batch_discover(args.batch, args.modality, args.top)
    else:
        raw_candidates = discover_candidates(args.condition, args.modality, args.top)
        candidates = [
            format_yaml_entry(c, args.condition.replace(" ", "-"), args.modality or "unknown")
            for c in raw_candidates
        ]

    # Output
    if not candidates:
        print("No candidates found.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFound {len(candidates)} candidate(s):\n")
    for c in candidates:
        print(f"  {c['image_ref']}")
        entry = c["entry"]
        print(f"    source_id: {entry['source_id']}")
        print(f"    url: {entry.get('url', 'N/A')}")
        print(f"    caption_score: {entry.get('caption_score', 'N/A')}")
        print(f"    notes: {entry.get('notes', '')[:100]}")
        print()

    if args.append:
        added = append_to_sources(candidates, args.sources)
        print(f"Added {added} entries to {args.sources}")


if __name__ == "__main__":
    main()
