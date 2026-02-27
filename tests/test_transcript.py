"""Tests for transcript.py — recording and loading."""

from __future__ import annotations

import time

import pytest

from radslice.transcript import TranscriptEntry, TranscriptWriter, load_transcript


class TestTranscriptEntry:
    def test_frozen(self):
        entry = TranscriptEntry(
            task_id="XRAY-001",
            model="test",
            trial=0,
            prompt=[{"role": "user", "content": "test"}],
            response="test response",
            latency_ms=100.0,
            timestamp=time.time(),
        )
        with pytest.raises(AttributeError):
            entry.task_id = "changed"

    def test_to_dict(self):
        entry = TranscriptEntry(
            task_id="XRAY-001",
            model="test",
            trial=0,
            prompt=[{"role": "user", "content": "test"}],
            response="test response",
            latency_ms=100.0,
            timestamp=1234567890.0,
        )
        d = entry.to_dict()
        assert d["task_id"] == "XRAY-001"
        assert d["model"] == "test"
        assert d["latency_ms"] == 100.0

    def test_defaults(self):
        entry = TranscriptEntry(
            task_id="t",
            model="m",
            trial=0,
            prompt=[],
            response="r",
            latency_ms=0.0,
            timestamp=0.0,
        )
        assert entry.cached is False
        assert entry.error is None
        assert entry.metadata == {}


class TestTranscriptWriter:
    def test_write_and_load(self, tmp_path):
        path = tmp_path / "transcript.jsonl"
        writer = TranscriptWriter(output_path=path)

        writer.write_header({"model": "test"})

        for i in range(5):
            entry = TranscriptEntry(
                task_id=f"XRAY-{i:03d}",
                model="test",
                trial=0,
                prompt=[{"role": "user", "content": f"prompt {i}"}],
                response=f"response {i}",
                latency_ms=100.0 * i,
                timestamp=time.time(),
            )
            writer.write_entry(entry)

        entries = load_transcript(path)
        assert len(entries) == 5
        assert entries[0].task_id == "XRAY-000"
        assert entries[4].response == "response 4"

    def test_header_skipped_on_load(self, tmp_path):
        path = tmp_path / "transcript.jsonl"
        writer = TranscriptWriter(output_path=path)
        writer.write_header({"test": "config"})
        writer.write_entry(
            TranscriptEntry(
                task_id="t",
                model="m",
                trial=0,
                prompt=[],
                response="r",
                latency_ms=0.0,
                timestamp=0.0,
            )
        )
        entries = load_transcript(path)
        assert len(entries) == 1

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "transcript.jsonl"
        writer = TranscriptWriter(output_path=path)
        writer.write_entry(
            TranscriptEntry(
                task_id="t",
                model="m",
                trial=0,
                prompt=[],
                response="r",
                latency_ms=0.0,
                timestamp=0.0,
            )
        )
        assert path.exists()

    def test_empty_lines_skipped(self, tmp_path):
        path = tmp_path / "transcript.jsonl"
        with open(path, "w") as f:
            f.write('{"type": "header", "config": {}, "timestamp": 0}\n')
            f.write("\n")
            f.write(
                '{"task_id": "t", "model": "m", "trial": 0, "prompt": [], "response": "r", "latency_ms": 0, "timestamp": 0}\n'
            )
            f.write("\n")
        entries = load_transcript(path)
        assert len(entries) == 1
