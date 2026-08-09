"""On-disk narration cache, keyed by facts_hash + finding id.

Re-running the same commit reproduces the identical report byte-for-byte,
because temperature 0 alone does not guarantee identical model output.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class NarrationCache:
    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def _path(self, facts_hash: str, finding_id: str) -> Path:
        key = hashlib.sha256(f"{facts_hash}\x00{finding_id}".encode("utf-8")).hexdigest()
        return self.directory / f"{key}.json"

    def get(self, facts_hash: str, finding_id: str) -> str | None:
        path = self._path(facts_hash, finding_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))["text"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def set(self, facts_hash: str, finding_id: str, text: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(facts_hash, finding_id)
        path.write_text(
            json.dumps({"id": finding_id, "text": text}), encoding="utf-8"
        )
