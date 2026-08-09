"""Narration orchestration: caching, id allowlist, retry, and clean fallback."""

from __future__ import annotations

import json
from pathlib import Path

from commitscope.models import Finding
from commitscope.narrate.cache import NarrationCache
from commitscope.narrate.client import narrate


def _finding(fid: str = "R001:m.f") -> Finding:
    return Finding(
        id=fid,
        rule_id="R001",
        severity="high",
        subject="m.f",
        title="Breaking change",
        evidence=["caller.py:3"],
        facts_refs=["m.f", "caller.py"],
    )


class _FakeFacts:
    facts_hash = "deadbeef"
    message_subject = "break m.f"


def _response(fid: str, text: str) -> str:
    return json.dumps({"narrations": [{"id": fid, "text": text}]})


def test_valid_narration_applied_and_cached(tmp_path: Path) -> None:
    cache = NarrationCache(tmp_path)
    finding = _finding()
    calls = []

    def call(prompt: str) -> str:
        calls.append(prompt)
        return _response(finding.id, "A required argument was added; callers break.")

    out = narrate([finding], _FakeFacts(), cache, call_model=call)
    assert out[finding.id].startswith("A required argument")
    assert len(calls) == 1
    # Cached now: a call_model that explodes must never be invoked.
    def boom(_: str) -> str:
        raise AssertionError("should have hit cache")

    out2 = narrate([finding], _FakeFacts(), cache, call_model=boom)
    assert out2 == out


def test_unknown_finding_id_dropped(tmp_path: Path) -> None:
    cache = NarrationCache(tmp_path)
    finding = _finding()

    def call(_: str) -> str:
        return _response("R999:ghost", "Invented finding narration.")

    out = narrate([finding], _FakeFacts(), cache, call_model=call)
    assert out == {}


def test_ungrounded_then_retry_succeeds(tmp_path: Path) -> None:
    cache = NarrationCache(tmp_path)
    finding = _finding()
    attempts = []

    def call(prompt: str) -> str:
        attempts.append(prompt)
        if len(attempts) == 1:
            return _response(finding.id, "The bug is in src/core/ghost_file.py entirely.")
        return _response(finding.id, "A required argument was added; callers break.")

    out = narrate([finding], _FakeFacts(), cache, call_model=call)
    assert out[finding.id].startswith("A required argument")
    assert len(attempts) == 2
    assert "previous response had problems" in attempts[1]


def test_persistent_hallucination_falls_back(tmp_path: Path) -> None:
    cache = NarrationCache(tmp_path)
    finding = _finding()

    def call(_: str) -> str:
        return _response(finding.id, "It lives in src/core/ghost_file.py, trust me.")

    out = narrate([finding], _FakeFacts(), cache, call_model=call)
    assert out == {}  # never accepted, no narration


def test_no_model_configured_degrades(tmp_path: Path) -> None:
    cache = NarrationCache(tmp_path)
    # call_model=None and no api key -> empty result, no crash.
    from commitscope.narrate.client import NarrationSettings

    out = narrate([_finding()], _FakeFacts(), cache, settings=NarrationSettings(api_key=None))
    assert out == {}
