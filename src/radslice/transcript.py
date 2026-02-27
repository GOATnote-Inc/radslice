"""Full trial transcript recording (JSON)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TranscriptEntry:
    """A single transcript entry for one trial of one task."""

    task_id: str
    model: str
    trial: int
    prompt: list[dict[str, Any]]
    response: str
    latency_ms: float
    timestamp: float
    cached: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptWriter:
    """Streaming JSONL transcript writer."""

    output_path: Path

    def __post_init__(self):
        self.output_path = Path(self.output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def write_entry(self, entry: TranscriptEntry) -> None:
        """Append a single entry to the transcript JSONL."""
        with open(self.output_path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def write_header(self, config: dict[str, Any]) -> None:
        """Write a config header line (type=header)."""
        header = {"type": "header", "config": config, "timestamp": time.time()}
        with open(self.output_path, "a") as f:
            f.write(json.dumps(header) + "\n")


def load_transcript(path: str | Path) -> list[TranscriptEntry]:
    """Load transcript entries from JSONL (skipping header lines)."""
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if data.get("type") == "header":
                continue
            entries.append(
                TranscriptEntry(
                    task_id=data["task_id"],
                    model=data["model"],
                    trial=data["trial"],
                    prompt=data["prompt"],
                    response=data["response"],
                    latency_ms=data["latency_ms"],
                    timestamp=data["timestamp"],
                    cached=data.get("cached", False),
                    error=data.get("error"),
                    metadata=data.get("metadata", {}),
                )
            )
    return entries
