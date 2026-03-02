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
        "description": "National Lung Screening Trial — CXR and CT",
        "modality": "CT",
        "anatomy": "CHEST",
        "conditions": ["pneumonia", "pulmonary-nodule"],
    },
    "MIDRC-RICORD": {
        "description": "COVID-19 CXR and CT",
        "modality": "CT",
        "anatomy": "CHEST",
        "conditions": ["pneumonia", "ards"],
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


def format_yaml_entry(
    series: dict, condition_id: str, window_preset: str | None = None
) -> dict:
    """Format an IDC series as an image_sources.yaml candidate."""
    series_uid = series.get("SeriesInstanceUID", series.get("series_uid", ""))
    collection = series.get("collection_id", "idc")
    patient_id = series.get("PatientID", "unknown")

    safe_name = f"{condition_id}-{collection}-{patient_id}".lower().replace(" ", "-")
    image_ref = f"ct/idc/{safe_name}.dcm"

    entry = {
        "source": "idc",
        "source_id": patient_id,
        "series_uid": series_uid,
        "original_format": "dicom",
        "license": "CC-BY-4.0",
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
        "--sources", default="corpus/image_sources.yaml", help="Image sources YAML"
    )
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


if __name__ == "__main__":
    main()
