"""Grounding must reject hallucinated identifiers — the check that matters."""

from __future__ import annotations

from commitscope.narrate.grounding import extract_identifiers, validate_narration

REFS = [
    "src.core.audio.chunk_audio",
    "chunk_audio",
    "src/api/routes.py",
    "API_KEY",
    "normalize",
]


def test_grounded_narration_passes() -> None:
    text = "The change to src.core.audio.chunk_audio breaks callers in src/api/routes.py."
    ok, reason = validate_narration(text, REFS)
    assert ok, reason


def test_invented_filename_rejected() -> None:
    text = "This also touches src/core/secret_handler.py which callers rely on."
    ok, reason = validate_narration(text, REFS)
    assert not ok
    assert "secret_handler.py" in reason


def test_invented_qualname_rejected() -> None:
    text = "The function src.core.audio.chunk_video lost a parameter."
    ok, reason = validate_narration(text, REFS)
    assert not ok
    assert "chunk_video" in reason


def test_invented_constant_rejected() -> None:
    text = "It now reads SECRET_TOKEN from the environment."
    ok, reason = validate_narration(text, REFS)
    assert not ok
    assert "SECRET_TOKEN" in reason


def test_bare_english_words_allowed() -> None:
    text = "A required parameter was added, so existing callers will break at runtime."
    ok, reason = validate_narration(text, REFS)
    assert ok, reason


def test_prose_abbreviations_not_treated_as_identifiers() -> None:
    text = "Callers, e.g. the API layer, must pass the new argument now."
    assert "e.g" not in extract_identifiers(text)
    ok, _ = validate_narration(text, REFS)
    assert ok


def test_too_long_rejected() -> None:
    text = " ".join(["word"] * 61)
    ok, reason = validate_narration(text, REFS)
    assert not ok
    assert "too_long" in reason


def test_code_fence_rejected() -> None:
    text = "Broken signature:\n```python\nchunk_audio(x)\n```"
    ok, reason = validate_narration(text, REFS)
    assert not ok
    assert "code_fence" in reason


def test_path_basename_tolerated() -> None:
    # facts_ref carries the full path; the model referring to just the basename is fine.
    ok, reason = validate_narration("See routes.py for the caller.", REFS)
    assert ok, reason
