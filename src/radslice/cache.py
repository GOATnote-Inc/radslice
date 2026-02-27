"""SHA-256 disk cache for API responses. Atomic writes, integrity checks."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


class ResponseCache:
    """Disk-based response cache with SHA-256 keying and integrity verification."""

    def __init__(self, cache_dir: str | Path):
        self._dir = Path(cache_dir) / ".response_cache"
        self._quarantine = Path(cache_dir) / ".cache_corrupted"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0
        self._corruption_events = 0

    @staticmethod
    def cache_key(model: str, messages: list[dict], temperature: float, seed: int) -> str:
        """Deterministic SHA-256 of request parameters."""
        payload = json.dumps(
            {"model": model, "messages": messages, "temperature": temperature, "seed": seed},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _path_for_key(self, key: str) -> Path:
        """Two-level subdirectory to avoid huge flat dirs."""
        return self._dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> str | None:
        """Look up cached response. Returns None on miss or corruption."""
        path = self._path_for_key(key)
        if not path.exists():
            self._misses += 1
            return None

        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            self._quarantine_file(path, key)
            self._misses += 1
            return None

        response = data.get("response", "")
        expected_hash = data.get("response_hash", "")
        actual_hash = hashlib.sha256(response.encode()).hexdigest()

        if actual_hash != expected_hash:
            self._quarantine_file(path, key)
            self._misses += 1
            return None

        self._hits += 1
        return response

    def put(self, key: str, response: str, model: str = "") -> None:
        """Store response with integrity hash. Atomic write via rename."""
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "response": response,
            "response_hash": hashlib.sha256(response.encode()).hexdigest(),
            "model": model,
            "cached_at": time.time(),
        }

        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, indent=2))
        os.replace(str(tmp), str(path))

    def _quarantine_file(self, path: Path, key: str) -> None:
        """Move corrupted cache file to quarantine."""
        self._corruption_events += 1
        self._quarantine.mkdir(parents=True, exist_ok=True)
        dest = self._quarantine / f"{key}.json"
        try:
            os.replace(str(path), str(dest))
        except OSError:
            pass

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "corruption_events": self._corruption_events,
        }
