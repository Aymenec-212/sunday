"""The grounding check — the one place a weak validator defeats the design.

Every identifier-shaped token a narration uses must be traceable to the
finding's ``facts_refs``. If the model invents a filename, a function, or a
constant, the token won't be in ``facts_refs`` and the narration is rejected
wholesale. Bare English words are intentionally *not* checked — only the
high-signal shapes (dotted qualnames, ``*.py`` paths, SCREAMING_CASE names).
"""

from __future__ import annotations

import re

MAX_WORDS = 60

_PATH = re.compile(r"[A-Za-z0-9_./\\-]+\.py\b")
_SCREAMING = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


def extract_identifiers(text: str) -> set[str]:
    """Pull the identifier-shaped tokens worth grounding out of ``text``."""
    tokens: set[str] = set()
    tokens.update(_PATH.findall(text))
    tokens.update(_SCREAMING.findall(text))
    for match in _DOTTED.finditer(text):
        token = match.group()
        if token.endswith(".py"):
            continue  # a filename — already covered by the path pattern
        if _is_prose_abbreviation(token):
            continue  # "e.g.", "i.e.", initialisms
        tokens.add(token)
    return tokens


def validate_narration(text: str, facts_refs: list[str]) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``reason`` is empty when ``ok`` is True."""
    if len(text.split()) > MAX_WORDS:
        return False, f"too_long ({len(text.split())} words > {MAX_WORDS})"
    if "```" in text:
        return False, "contains_code_fence"

    allowed = set(facts_refs)
    allowed |= {ref.rsplit("/", 1)[-1] for ref in facts_refs}  # basename tolerance

    for token in extract_identifiers(text):
        if token not in allowed:
            return False, f"ungrounded_identifier:{token}"
    return True, ""


def _is_prose_abbreviation(token: str) -> bool:
    # "e.g", "i.e", "U.S.A" — every dotted component is a single character.
    return all(len(part) <= 1 for part in token.split("."))
