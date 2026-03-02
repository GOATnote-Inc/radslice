#!/usr/bin/env python3
"""Validate that downloaded images exhibit the target pathology using a vision LLM.

Uses existing RadSlice providers and image loading infrastructure to verify
pathology presence. This is the critical quality gate for image sourcing.

Usage:
    # Validate a single task's image
    python scripts/validate_pathology.py --task-id XRAY-001

    # Validate all downloaded images
    python scripts/validate_pathology.py --all --model gpt-5.2

    # Dry run
    python scripts/validate_pathology.py --all --dry-run

    # Filter by modality
    python scripts/validate_pathology.py --all --modality xray --model gpt-5.2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger("validate_pathology")

VERIFICATION_PROMPT = """You are a board-certified radiologist validating whether a medical image
exhibits specific pathological findings.

**Condition:** {condition}
**Primary diagnosis:** {diagnosis}

**Required findings to verify:**
{findings_list}

For each finding listed above, state whether it is:
- PRESENT: clearly visible in the image
- ABSENT: definitively not present
- UNCERTAIN: cannot determine from this image

Then provide an overall assessment:
- PASS: if >= 50% of required findings are PRESENT
- FAIL: if < 50% of required findings are PRESENT or image is wrong modality/anatomy

Note: If this image contains multiple panels or is a composite,
focus on the most clinically relevant panel and note which panel
you are assessing. A composite image with the target pathology
in at least one panel should still be assessed for those findings.

Respond in this exact JSON format:
{{
  "findings": [
    {{"finding": "<finding text>", "status": "PRESENT|ABSENT|UNCERTAIN"}}
  ],
  "overall": "PASS|FAIL",
  "confidence": 0.0-1.0,
  "notes": "<brief explanation>"
}}"""


def load_image_sources(path: str = "corpus/image_sources.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_image_sources(data: dict, path: str = "corpus/image_sources.yaml"):
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)


def load_task(task_path: Path) -> dict:
    with open(task_path) as f:
        return yaml.safe_load(f)


def find_task_by_id(task_id: str, tasks_dir: str = "configs/tasks") -> dict | None:
    for yaml_path in Path(tasks_dir).rglob("*.yaml"):
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        if raw and raw.get("id") == task_id:
            return raw
    return None


def build_findings_list(task: dict) -> str:
    gt = task.get("ground_truth", {})
    findings = gt.get("key_findings", [])
    lines = []
    for i, f in enumerate(findings, 1):
        req = " (REQUIRED)" if f.get("required", True) else " (optional)"
        lines.append(f"{i}. {f['finding']} — location: {f['location']}{req}")
    return "\n".join(lines) if lines else "No specific findings listed."


def build_verification_prompt(task: dict) -> str:
    gt = task.get("ground_truth", {})
    return VERIFICATION_PROMPT.format(
        condition=task.get("condition_id", "unknown"),
        diagnosis=gt.get("primary_diagnosis", "unknown"),
        findings_list=build_findings_list(task),
    )


def parse_validation_response(text: str) -> dict:
    """Parse JSON response from validation LLM."""
    # Try to extract JSON from response
    text = text.strip()

    # Handle markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        result = json.loads(text)
        return result
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON response, attempting extraction")
        # Try to find JSON object in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    return {
        "overall": "FAIL", "confidence": 0.0,
        "notes": "Failed to parse response", "findings": [],
    }


async def validate_single(
    task_id: str,
    tasks_dir: str = "configs/tasks",
    images_dir: str = "corpus/images",
    model: str = "gpt-5.2",
    dry_run: bool = False,
) -> dict:
    """Validate pathology for a single task."""
    task = find_task_by_id(task_id, tasks_dir)
    if not task:
        return {"task_id": task_id, "status": "error", "reason": "Task not found"}

    image_ref = task.get("image_ref", "")
    image_path = Path(images_dir) / image_ref
    condition_id = task.get("condition_id", "unknown")

    if dry_run:
        return {
            "task_id": task_id,
            "condition_id": condition_id,
            "image_ref": image_ref,
            "image_exists": image_path.exists(),
            "status": "dry_run",
            "model": model,
        }

    if not image_path.exists():
        return {
            "task_id": task_id,
            "condition_id": condition_id,
            "image_ref": image_ref,
            "status": "skipped",
            "reason": "Image file not found",
        }

    # Load and encode image
    from radslice.image import load_and_encode

    try:
        encoded = load_and_encode(
            image_path, window_preset=task.get("window_preset")
        )
    except Exception as e:
        return {
            "task_id": task_id,
            "condition_id": condition_id,
            "status": "error",
            "reason": f"Failed to load image: {e}",
        }

    # Build prompt
    prompt = build_verification_prompt(task)

    # Call vision LLM
    provider = _get_provider(model)
    try:
        response = await provider.complete(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            images=[encoded],
            temperature=0.0,
            seed=42,
            max_tokens=2048,
        )
    except Exception as e:
        return {
            "task_id": task_id,
            "condition_id": condition_id,
            "status": "error",
            "reason": f"LLM call failed: {e}",
        }

    # Parse response
    result = parse_validation_response(response.text)

    return {
        "task_id": task_id,
        "condition_id": condition_id,
        "image_ref": image_ref,
        "status": "validated",
        "overall": result.get("overall", "FAIL"),
        "confidence": result.get("confidence", 0.0),
        "findings": result.get("findings", []),
        "notes": result.get("notes", ""),
        "model": model,
    }


def _get_provider(model: str):
    """Get the appropriate provider for the model."""
    if "gpt" in model.lower():
        from radslice.providers.openai import OpenAIProvider

        return OpenAIProvider()
    elif "opus" in model.lower() or "sonnet" in model.lower() or "claude" in model.lower():
        from radslice.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    elif "gemini" in model.lower():
        from radslice.providers.google import GoogleProvider

        return GoogleProvider()
    else:
        from radslice.providers.openai import OpenAIProvider

        return OpenAIProvider()


async def validate_batch(
    tasks_dir: str = "configs/tasks",
    images_dir: str = "corpus/images",
    model: str = "gpt-5.2",
    modality: str | None = None,
    dry_run: bool = False,
    sources_path: str = "corpus/image_sources.yaml",
) -> list[dict]:
    """Validate pathology for all downloaded images."""
    results = []

    # Find all tasks with downloaded images
    tasks_path = Path(tasks_dir)
    for yaml_path in sorted(tasks_path.rglob("*.yaml")):
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        if not raw or "id" not in raw:
            continue

        if modality and raw.get("modality") != modality:
            continue

        task_id = raw["id"]
        image_ref = raw.get("image_ref", "")
        image_path = Path(images_dir) / image_ref

        # Only validate images that exist on disk
        if not dry_run and not image_path.exists():
            continue

        result = await validate_single(
            task_id, tasks_dir, images_dir, model, dry_run
        )
        results.append(result)

        # Print progress
        status = result.get("overall", result.get("status", "?"))
        logger.info(
            "[%s] %s — %s",
            task_id,
            raw.get("condition_id", "?"),
            status,
        )

    return results


def update_sources_from_results(
    results: list[dict], sources_path: str = "corpus/image_sources.yaml"
):
    """Update image_sources.yaml with validation results."""
    # Lazy import audit trail
    try:
        from audit import update_provenance_validation
    except ImportError:
        update_provenance_validation = None

    sources = load_image_sources(sources_path)
    images = sources.get("images", {})
    updated = 0

    for r in results:
        if r.get("status") != "validated":
            continue

        image_ref = r.get("image_ref", "")
        if image_ref not in images:
            continue

        passed = r.get("overall", "FAIL") == "PASS"
        images[image_ref]["validation_status"] = "validated" if passed else "failed"
        images[image_ref]["pathology_confirmed"] = passed
        updated += 1

        # Update provenance audit trail
        if update_provenance_validation is not None:
            try:
                update_provenance_validation(image_ref, {
                    "model": r.get("model", "unknown"),
                    "overall": r.get("overall", "FAIL"),
                    "confidence": r.get("confidence", 0.0),
                    "notes": r.get("notes", ""),
                })
            except Exception as e:
                logger.debug("Provenance update skipped for %s: %s", image_ref, e)

    if updated > 0:
        save_image_sources(sources, sources_path)
        logger.info("Updated %d entries in %s", updated, sources_path)

    return updated


def main():
    parser = argparse.ArgumentParser(
        description="Validate pathology presence in RadSlice corpus images"
    )
    parser.add_argument("--task-id", help="Validate a single task")
    parser.add_argument("--all", action="store_true", help="Validate all downloaded images")
    parser.add_argument("--modality", choices=["xray", "ct", "mri", "ultrasound"])
    parser.add_argument("--model", default="gpt-5.2", help="Vision LLM for validation")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be validated")
    parser.add_argument("--tasks-dir", default="configs/tasks")
    parser.add_argument("--images-dir", default="corpus/images")
    parser.add_argument("--sources", default="corpus/image_sources.yaml")
    parser.add_argument("--update-sources", action="store_true", help="Update image_sources.yaml")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    if not args.task_id and not args.all:
        parser.error("Provide --task-id or --all")

    if args.task_id:
        result = asyncio.run(
            validate_single(
                args.task_id, args.tasks_dir, args.images_dir, args.model, args.dry_run
            )
        )
        results = [result]
    else:
        results = asyncio.run(
            validate_batch(
                args.tasks_dir,
                args.images_dir,
                args.model,
                args.modality,
                args.dry_run,
                args.sources,
            )
        )

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.get("overall") == "PASS")
    failed = sum(1 for r in results if r.get("overall") == "FAIL")
    errors = sum(1 for r in results if r.get("status") == "error")
    skipped = sum(1 for r in results if r.get("status") in ("skipped", "dry_run"))

    print("\nValidation Summary:")
    print(f"  Total:   {total}")
    print(f"  PASS:    {passed}")
    print(f"  FAIL:    {failed}")
    print(f"  Errors:  {errors}")
    print(f"  Skipped: {skipped}")

    if args.update_sources and not args.dry_run:
        updated = update_sources_from_results(results, args.sources)
        print(f"  Updated: {updated} entries in {args.sources}")

    # Output detailed results as JSON
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
