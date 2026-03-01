"""Matrix execution engine: tasks x models x trials with concurrency control."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from radslice.grading.grader import GradeResult, RubricGrader
from radslice.image import EncodedImage, load_and_encode
from radslice.providers.base import Provider
from radslice.task import Task, load_tasks_from_dir
from radslice.transcript import TranscriptEntry, TranscriptWriter

logger = logging.getLogger(__name__)

PROMPT_TEMPLATES = {
    "diagnosis": (
        "You are an expert radiologist. Analyze the provided medical image and give your "
        "interpretation.\n\n"
        "Provide:\n"
        "1. Primary diagnosis\n"
        "2. Key findings with anatomic locations\n"
        "3. Differential diagnoses\n"
        "4. Severity assessment\n"
        "5. Recommended next steps"
    ),
    "finding_detection": (
        "You are an expert radiologist. Examine the provided medical image carefully.\n\n"
        "List all significant findings you observe, including:\n"
        "- Description of each finding\n"
        "- Anatomic location\n"
        "- Clinical significance"
    ),
    "vqa": (
        "You are an expert radiologist. Answer the following question about "
        "the provided medical image.\n\n{question}"
    ),
    "report_generation": (
        "You are an expert radiologist. Generate a structured radiology report "
        "for the provided medical image.\n\n"
        "Include: Technique, Comparison, Findings, and Impression sections."
    ),
    "incidental_detection": (
        "You are an expert radiologist. Analyze the provided medical image thoroughly.\n\n"
        "Identify ALL findings, both the primary pathology and any incidental or secondary "
        "findings. For each finding, provide:\n"
        "1. Description of the finding\n"
        "2. Anatomic location\n"
        "3. Clinical significance (critical / significant / incidental / benign)\n"
        "4. Recommended action (e.g., urgent follow-up, routine follow-up, no action needed)\n\n"
        "Organize your response as:\n"
        "- **Primary Finding**: [diagnosis and details]\n"
        "- **Incidental Findings**: [list each with significance and recommended action]"
    ),
    "report_audit": (
        "You are an expert radiologist performing a second-opinion audit. "
        "You are given a medical image AND a radiologist's report. "
        "Your task is to identify errors in the report.\n\n"
        "Review the image independently, then compare your interpretation against the "
        "provided report. For each error found, classify it as:\n"
        "- **missed_finding**: Finding visible on the image but not mentioned in the report\n"
        "- **wrong_laterality**: Correct finding but attributed to the wrong side\n"
        "- **severity_underestimate**: Finding identified but severity understated\n"
        "- **hallucinated_finding**: Finding described in the report but not present on the image\n"
        "- **wrong_diagnosis**: Incorrect diagnostic conclusion\n\n"
        "For each error, state:\n"
        "1. Error type\n"
        "2. What the report claims (or omits)\n"
        "3. What the correct interpretation should be\n"
        "4. Severity of the error (critical / major / minor)\n\n"
        "## Report to Audit:\n{provided_report}"
    ),
}


@dataclass(frozen=True)
class MatrixConfig:
    """Configuration for a matrix evaluation run."""

    tasks_dir: str
    models: list[dict[str, str]]  # [{name, provider, model_id}]
    n_trials: int = 3
    max_concurrency: int = 5
    modality_filter: str | None = None
    task_ids: list[str] | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> MatrixConfig:
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls(
            tasks_dir=raw["tasks_dir"],
            models=raw["models"],
            n_trials=raw.get("n_trials", 3),
            max_concurrency=raw.get("max_concurrency", 5),
            modality_filter=raw.get("modality_filter"),
            task_ids=raw.get("task_ids"),
        )


@dataclass
class RunResult:
    """Aggregated results from a matrix run."""

    grades: list[GradeResult] = field(default_factory=list)
    transcripts: list[TranscriptEntry] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def to_jsonl(self, path: str | Path) -> None:
        """Write grades to JSONL."""
        with open(path, "w") as f:
            for grade in self.grades:
                f.write(json.dumps(grade.to_dict()) + "\n")


def _build_prompt(task: Task) -> str:
    """Build the prompt text from task template."""
    template = PROMPT_TEMPLATES.get(task.prompt_template, PROMPT_TEMPLATES["diagnosis"])
    if task.task_type == "vqa" and task.metadata.get("question"):
        template = template.format(question=task.metadata["question"])
    elif task.task_type == "report_audit" and task.ground_truth.provided_report:
        template = template.format(provided_report=task.ground_truth.provided_report)
    return template


def _load_image_if_exists(task: Task, corpus_dir: str | Path) -> EncodedImage | None:
    """Try to load the task's image. Returns None if not found.

    Tries the exact image_ref path first, then falls back to alternate
    extensions (.dcm, .dicom) for DICOM files.
    """
    img_path = Path(corpus_dir) / "images" / task.image_ref
    if not img_path.exists():
        # Try alternate extensions for DICOM
        for ext in (".dcm", ".dicom"):
            alt = img_path.with_suffix(ext)
            if alt.exists():
                img_path = alt
                break
        else:
            return None
    return load_and_encode(img_path, window_preset=task.window_preset)


class MatrixExecutor:
    """Executes tasks across models and trials with concurrency control."""

    def __init__(
        self,
        providers: dict[str, Provider],
        grader: RubricGrader,
        corpus_dir: str | Path = "corpus",
        output_dir: str | Path = "results",
        resume: bool = False,
    ):
        self._providers = providers
        self._grader = grader
        self._corpus_dir = Path(corpus_dir)
        self._output_dir = Path(output_dir)
        self._resume = resume
        self._completed: set[str] = set()

        if resume:
            self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        """Load completed task+model+trial combos from existing results."""
        grades_path = self._output_dir / "grades.jsonl"
        if grades_path.exists():
            with open(grades_path) as f:
                for line in f:
                    data = json.loads(line.strip())
                    key = f"{data['task_id']}:{data['model']}:{data['trial']}"
                    self._completed.add(key)
            logger.info("Resumed with %d completed entries", len(self._completed))

    async def run(self, config: MatrixConfig) -> RunResult:
        """Execute the full matrix evaluation."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Load tasks
        tasks = load_tasks_from_dir(config.tasks_dir)
        if config.modality_filter:
            tasks = [t for t in tasks if t.modality == config.modality_filter]
        if config.task_ids:
            id_set = set(config.task_ids)
            tasks = [t for t in tasks if t.id in id_set]

        logger.info(
            "Running matrix: %d tasks × %d models × %d trials = %d total",
            len(tasks),
            len(config.models),
            config.n_trials,
            len(tasks) * len(config.models) * config.n_trials,
        )

        result = RunResult(config={"matrix": config.__dict__})
        transcript_writer = TranscriptWriter(self._output_dir / "transcripts.jsonl")
        transcript_writer.write_header(result.config)

        sem = asyncio.Semaphore(config.max_concurrency)

        async def run_one(task: Task, model_cfg: dict, trial: int) -> None:
            key = f"{task.id}:{model_cfg['name']}:{trial}"
            if key in self._completed:
                return

            async with sem:
                try:
                    grade, transcript = await self._execute_single(task, model_cfg, trial)
                    result.grades.append(grade)
                    result.transcripts.append(transcript)
                    transcript_writer.write_entry(transcript)
                    # Append grade to checkpoint
                    with open(self._output_dir / "grades.jsonl", "a") as f:
                        f.write(json.dumps(grade.to_dict()) + "\n")
                except Exception as exc:
                    logger.error("Error on %s: %s", key, exc)
                    result.errors.append({"key": key, "error": str(exc)})

        # Build all work items
        coros = []
        for task in tasks:
            for model_cfg in config.models:
                for trial in range(config.n_trials):
                    coros.append(run_one(task, model_cfg, trial))

        await asyncio.gather(*coros)

        logger.info(
            "Complete: %d grades, %d errors",
            len(result.grades),
            len(result.errors),
        )
        return result

    async def _execute_single(
        self, task: Task, model_cfg: dict, trial: int
    ) -> tuple[GradeResult, TranscriptEntry]:
        """Execute and grade a single task/model/trial combo."""
        provider_name = model_cfg["provider"]
        model_id = model_cfg["model_id"]
        model_name = model_cfg["name"]

        provider = self._providers[provider_name]
        image = _load_image_if_exists(task, self._corpus_dir)
        prompt = _build_prompt(task)

        messages = [{"role": "user", "content": prompt}]
        images = [image] if image else None

        start = time.monotonic()
        response = await provider.complete(
            messages=messages,
            model=model_id,
            images=images,
            temperature=0.0,
            seed=42,
        )
        latency_ms = (time.monotonic() - start) * 1000

        # Grade the response
        grade = await self._grader.grade(
            task=task,
            response=response.text,
            model=model_name,
            trial=trial,
        )

        transcript = TranscriptEntry(
            task_id=task.id,
            model=model_name,
            trial=trial,
            prompt=messages,
            response=response.text,
            latency_ms=latency_ms,
            timestamp=time.time(),
            cached=response.cached,
            metadata={
                "provider": provider_name,
                "model_id": model_id,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            },
        )

        return grade, transcript
