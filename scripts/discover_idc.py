#!/usr/bin/env python3
"""Discover condition-matched DICOM images from NCI Imaging Data Commons (IDC).

Queries the local idc-index SQLite database for series matching modality,
anatomy, and collection criteria. Outputs candidates for image_sources.yaml.

Usage:
    # Find head CT series from CQ500
    python scripts/discover_idc.py --modality CT --anatomy HEAD --collection CQ500 --top 5

    # Find chest CT PE studies
    python scripts/discover_idc.py --modality CT --anatomy CHEST --description "pulmonary embolism"

    # List available collections
    python scripts/discover_idc.py --list-collections --modality CT

Requires: pip install idc-index
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

logger = logging.getLogger("discover_idc")

# Collections with known acute pathology useful for RadSlice
CURATED_COLLECTIONS = {
    # --- CT collections ---
    "CQ500": {
        "description": "Head CT — hemorrhage, fractures, mass effect",
        "modality": "CT",
        "anatomy": "HEAD",
        "conditions": [
            "hemorrhagic-stroke",
            "epidural-hematoma",
            "subdural-hematoma",
            "subarachnoid-hemorrhage",
            "traumatic-brain-injury",
        ],
    },
    "LIDC-IDRI": {
        "description": "Chest CT — lung nodules, lung cancer screening",
        "modality": "CT",
        "anatomy": "CHEST",
        "conditions": ["pulmonary-nodule", "lung-cancer"],
    },
    "RSNA-PE": {
        "description": "CTPA — pulmonary embolism detection",
        "modality": "CT",
        "anatomy": "CHEST",
        "conditions": ["pulmonary-embolism"],
    },
    "NLST": {
        "description": "National Lung Screening Trial — CXR and CT (longitudinal)",
        "modality": "CT",
        "anatomy": "CHEST",
        "conditions": ["pneumonia", "pulmonary-nodule"],
        "v2_levels": [1, 2, 4],  # L4: longitudinal comparison
    },
    "MIDRC-RICORD": {
        "description": "COVID-19 CXR and CT",
        "modality": "CT",
        "anatomy": "CHEST",
        "conditions": ["pneumonia", "ards"],
    },
    "CT-ORG": {
        "description": "CT organ segmentation — multi-organ",
        "modality": "CT",
        "anatomy": "ABDOMEN",
        "conditions": ["mesenteric-ischemia", "bowel-obstruction"],
        "v2_levels": [1, 2],
    },
    "CPTAC": {
        "description": "Clinical Proteomic Tumor Analysis Consortium — multi-organ CT",
        "modality": "CT",
        "anatomy": "ABDOMEN",
        "conditions": ["hepatic-steatosis", "renal-cyst"],
    },
    # --- MRI collections (new for v2.0) ---
    "TCGA-GBM": {
        "description": "Brain MRI — glioblastoma (262 subjects, DICOM)",
        "modality": "MR",
        "anatomy": "BRAIN",
        "conditions": [
            "hemorrhagic-stroke",
            "traumatic-brain-injury",
            "status-epilepticus",
        ],
        "v2_levels": [1, 2],
    },
    "TCGA-LGG": {
        "description": "Brain MRI — low-grade glioma (199 subjects, DICOM)",
        "modality": "MR",
        "anatomy": "BRAIN",
        "conditions": [
            "hemorrhagic-stroke",
            "status-epilepticus",
        ],
        "v2_levels": [1, 2],
    },
    "Duke-Breast-Cancer-MRI": {
        "description": "Breast MRI — dynamic contrast-enhanced (922 subjects, DICOM)",
        "modality": "MR",
        "anatomy": "BREAST",
        "conditions": [],
        "v2_levels": [2],  # Multi-sequence correlation
    },
    "PROSTATEx": {
        "description": "Prostate MRI — multiparametric (346 subjects, DICOM)",
        "modality": "MR",
        "anatomy": "PROSTATE",
        "conditions": [],
        "v2_levels": [2],
    },
    "ReMIND": {
        "description": "Brain MRI — pre/intra-operative (114 subjects, DICOM)",
        "modality": "MR",
        "anatomy": "BRAIN",
        "conditions": ["traumatic-brain-injury"],
        "v2_levels": [1, 2],
    },
    "RIDER-Neuro-MRI": {
        "description": "Brain MRI — longitudinal repeat scans (DICOM)",
        "modality": "MR",
        "anatomy": "BRAIN",
        "conditions": [],
        "v2_levels": [4],  # Longitudinal comparison
    },
    # --- Ultrasound collections ---
    "B-mode-CEUS-Liver": {
        "description": "Liver ultrasound — B-mode and contrast-enhanced (DICOM)",
        "modality": "US",
        "anatomy": "LIVER",
        "conditions": ["acute-cholecystitis", "ascending-cholangitis"],
    },
}


def get_idc_client():
    """Get IDCClient instance, raising ImportError with install hint."""
    try:
        from idc_index import IDCClient  # type: ignore[import-untyped]

        return IDCClient()
    except ImportError:
        raise ImportError(
            "idc-index is required for IDC discovery. "
            "Install with: pip install idc-index\n"
            "Or: pip install radslice[sourcing]"
        )


def list_collections(client, modality: str | None = None) -> list[dict]:
    """List available IDC collections, optionally filtered by modality."""
    try:
        df = client.get_collections()
    except Exception as e:
        logger.error("Failed to fetch collections: %s", e)
        return []

    records = df.to_dict("records") if hasattr(df, "to_dict") else []

    if modality:
        records = [r for r in records if modality.upper() in str(r.get("Modality", "")).upper()]

    return records


def query_series(
    client,
    modality: str | None = None,
    anatomy: str | None = None,
    collection: str | None = None,
    description: str | None = None,
    top: int = 10,
) -> list[dict]:
    """Query IDC index for matching DICOM series."""
    try:
        # Build SQL query against the local SQLite index
        conditions = []
        if modality:
            conditions.append(f"Modality = '{modality.upper()}'")
        if anatomy:
            conditions.append(f"BodyPartExamined = '{anatomy.upper()}'")
        if collection:
            conditions.append(f"collection_id LIKE '%{collection}%'")
        if description:
            conditions.append(f"StudyDescription LIKE '%{description}%'")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM index WHERE {where_clause} LIMIT {top}"

        logger.info("Query: %s", sql)
        df = client.sql_query(sql)

        if df is None or (hasattr(df, "empty") and df.empty):
            return []

        return df.to_dict("records") if hasattr(df, "to_dict") else []

    except Exception as e:
        logger.error("IDC query failed: %s", e)
        return []


def format_yaml_entry(series: dict, condition_id: str, window_preset: str | None = None) -> dict:
    """Format an IDC series as an image_sources.yaml candidate."""
    series_uid = series.get("SeriesInstanceUID", series.get("series_uid", ""))
    collection = series.get("collection_id", "idc")
    patient_id = series.get("PatientID", "unknown")
    modality = series.get("Modality", "CT").upper()

    safe_name = f"{condition_id}-{collection}-{patient_id}".lower().replace(" ", "-")

    # Map DICOM modality to directory
    modality_dir_map = {"CT": "ct", "MR": "mri", "US": "ultrasound", "CR": "xray", "DX": "xray"}
    mod_dir = modality_dir_map.get(modality, "ct")
    image_ref = f"{mod_dir}/idc/{safe_name}.dcm"

    entry = {
        "source": "idc",
        "source_id": patient_id,
        "series_uid": series_uid,
        "original_format": "dicom",
        "license": "CC-BY-4.0",
        "license_tier": "commercial_safe",
        "condition_id": condition_id,
        "task_ids": [],
        "validation_status": "sourced",
        "pathology_confirmed": False,
    }

    if window_preset:
        entry["window_preset"] = window_preset

    # Add study metadata as notes
    study_desc = series.get("StudyDescription", "")
    series_desc = series.get("SeriesDescription", "")
    notes_parts = [p for p in [study_desc, series_desc] if p]
    if notes_parts:
        entry["notes"] = "; ".join(notes_parts)[:200]

    return {"image_ref": image_ref, "entry": entry}


def discover_for_collection(
    client,
    collection_id: str,
    top: int = 10,
) -> list[dict]:
    """Discover series from a specific curated collection."""
    info = CURATED_COLLECTIONS.get(collection_id, {})
    modality = info.get("modality")
    anatomy = info.get("anatomy")

    results = query_series(
        client,
        modality=modality,
        anatomy=anatomy,
        collection=collection_id,
        top=top,
    )

    candidates = []
    conditions = info.get("conditions", ["unknown"])
    condition_id = conditions[0] if conditions else "unknown"

    # Window preset heuristic
    window_map = {
        "HEAD": "ct_brain",
        "CHEST": "ct_lung",
        "ABDOMEN": "ct_abdomen",
    }
    window_preset = window_map.get(anatomy, "ct_soft_tissue")

    for series in results:
        entry = format_yaml_entry(series, condition_id, window_preset)
        candidates.append(entry)

    return candidates


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
            images[ref] = c["entry"]
            added += 1

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)

    logger.info("Added %d new entries to %s", added, sources_path)
    return added


def batch_download_s5cmd(
    series_uids: list[str],
    output_dir: str = "corpus/images",
    dry_run: bool = False,
) -> dict[str, int]:
    """Batch download DICOM series from IDC via s5cmd (GCS public buckets).

    s5cmd is ~40x faster than gsutil for bulk downloads.
    Install: https://github.com/peak/s5cmd

    Falls back to idc-index download_from_selection if s5cmd is not available.
    """
    import subprocess

    stats = {"downloaded": 0, "skipped": 0, "failed": 0}

    if not series_uids:
        return stats

    # Check for s5cmd
    s5cmd_available = False
    try:
        result = subprocess.run(["s5cmd", "version"], capture_output=True, timeout=5)
        s5cmd_available = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    if s5cmd_available:
        logger.info("Using s5cmd for batch download of %d series", len(series_uids))

        if dry_run:
            for uid in series_uids:
                logger.info("  [dry-run] Would download series: %s", uid[:60])
                stats["skipped"] += 1
            return stats

        # Get GCS paths from idc-index
        try:
            client = get_idc_client()
            for uid in series_uids:
                try:
                    # Query for GCS path
                    sql = f"SELECT gcs_url FROM index WHERE SeriesInstanceUID = '{uid}' LIMIT 1"
                    df = client.sql_query(sql)
                    if df is not None and not df.empty:
                        gcs_url = df.iloc[0]["gcs_url"]
                        dest_dir = Path(output_dir) / "dicom"
                        dest_dir.mkdir(parents=True, exist_ok=True)

                        cmd = ["s5cmd", "--no-sign-request", "cp", f"{gcs_url}/*", str(dest_dir)]
                        result = subprocess.run(cmd, capture_output=True, timeout=300)
                        if result.returncode == 0:
                            stats["downloaded"] += 1
                        else:
                            stderr = result.stderr.decode()[:200]
                            logger.error("s5cmd failed for %s: %s", uid[:40], stderr)
                            stats["failed"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    logger.error("Download failed for series %s: %s", uid[:40], e)
                    stats["failed"] += 1
        except ImportError:
            logger.error("idc-index required for GCS path resolution")
            stats["failed"] = len(series_uids)
    else:
        logger.info(
            "s5cmd not available, falling back to idc-index for %d series",
            len(series_uids),
        )
        try:
            client = get_idc_client()
            for uid in series_uids:
                if dry_run:
                    stats["skipped"] += 1
                    continue
                try:
                    dest_dir = Path(output_dir) / "dicom"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    client.download_from_selection(
                        seriesInstanceUID=uid,
                        downloadDir=str(dest_dir),
                    )
                    stats["downloaded"] += 1
                except Exception as e:
                    logger.error("IDC download failed for %s: %s", uid[:40], e)
                    stats["failed"] += 1
        except ImportError:
            logger.error("Neither s5cmd nor idc-index available for batch download")
            stats["failed"] = len(series_uids)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Discover condition-matched DICOM images from NCI IDC"
    )
    parser.add_argument("--modality", help="DICOM modality (CT, CR, MR)")
    parser.add_argument("--anatomy", help="Body part (HEAD, CHEST, ABDOMEN)")
    parser.add_argument("--collection", help="IDC collection ID (e.g., CQ500)")
    parser.add_argument("--description", help="Study description keyword")
    parser.add_argument("--condition-id", help="OpenEM condition ID for output")
    parser.add_argument("--top", type=int, default=10, help="Max results")
    parser.add_argument(
        "--list-collections", action="store_true", help="List available collections"
    )
    parser.add_argument(
        "--list-curated", action="store_true", help="List curated collections for RadSlice"
    )
    parser.add_argument("--append", action="store_true", help="Append to image_sources.yaml")
    parser.add_argument(
        "--batch-download",
        action="store_true",
        help="Batch download discovered series via s5cmd (or idc-index fallback)",
    )
    parser.add_argument("--output-dir", default="corpus/images", help="Download output directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    parser.add_argument("--sources", default="corpus/image_sources.yaml", help="Image sources YAML")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    if args.list_curated:
        print("Curated IDC collections for RadSlice:\n")
        for cid, info in CURATED_COLLECTIONS.items():
            conds = ", ".join(info.get("conditions", []))
            print(f"  {cid:20s} {info['description']}")
            print(f"  {'':20s} Conditions: {conds}")
            print()
        return

    client = get_idc_client()

    if args.list_collections:
        records = list_collections(client, args.modality)
        if not records:
            print("No collections found (or idc-index not initialized).")
            return
        for r in records[:50]:
            print(f"  {r.get('collection_id', 'N/A'):30s} {r.get('Modality', '')}")
        return

    # Discovery mode
    if args.collection and args.collection in CURATED_COLLECTIONS:
        candidates = discover_for_collection(client, args.collection, args.top)
    else:
        if not args.condition_id:
            parser.error("--condition-id is required for custom queries")

        results = query_series(
            client,
            modality=args.modality,
            anatomy=args.anatomy,
            collection=args.collection,
            description=args.description,
            top=args.top,
        )

        candidates = [format_yaml_entry(s, args.condition_id) for s in results]

    if not candidates:
        print("No candidates found.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFound {len(candidates)} candidate(s):\n")
    for c in candidates:
        print(f"  {c['image_ref']}")
        e = c["entry"]
        print(f"    series_uid: {e.get('series_uid', 'N/A')[:60]}...")
        print(f"    notes: {e.get('notes', '')[:100]}")
        print()

    if args.append:
        added = append_to_sources(candidates, args.sources)
        print(f"Added {added} entries to {args.sources}")

    if args.batch_download:
        uids = [
            c["entry"].get("series_uid", "") for c in candidates if c["entry"].get("series_uid")
        ]
        if uids:
            print(f"\nBatch downloading {len(uids)} series...")
            stats = batch_download_s5cmd(uids, args.output_dir, dry_run=args.dry_run)
            print(f"Download stats: {stats}")
        else:
            print("No series UIDs to download.")


if __name__ == "__main__":
    main()
