"""Stage 4: the one optional model call. Cosmetic by construction.

Given findings and the slice of facts they reference, ask a model for a
one-sentence gloss per finding. Everything it returns is schema-checked,
id-allowlisted, length-capped, and grounded against ``facts_refs`` before it
is accepted. On any failure the finding simply stays un-narrated — the run
never fails because of the model.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable

from commitscope.models import Facts, Finding
from commitscope.narrate.cache import NarrationCache
from commitscope.narrate.grounding import validate_narration
from commitscope.narrate.schema import NarrationResponse

ModelCall = Callable[[str], str]

_MAX_ATTEMPTS = 2  # one initial call + one retry with the violation appended


@dataclass
class NarrationSettings:
    api_key: str | None = None
    model: str = "claude-haiku-4-5-20251001"
    base_url: str = "https://api.anthropic.com/v1/messages"
    max_tokens: int = 1024
    timeout: float = 30.0


def settings_from_env() -> NarrationSettings:
    return NarrationSettings(
        api_key=os.environ.get("COMMITSCOPE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"),
        model=os.environ.get("COMMITSCOPE_MODEL", NarrationSettings.model),
    )


def narrate(
    findings: list[Finding],
    facts: Facts,
    cache: NarrationCache,
    call_model: ModelCall | None = None,
    settings: NarrationSettings | None = None,
) -> dict[str, str]:
    """Return ``{finding_id: narration}`` for whatever could be grounded."""
    results: dict[str, str] = {}
    pending: list[Finding] = []
    for finding in findings:
        cached = cache.get(facts.facts_hash, finding.id)
        if cached is not None:
            results[finding.id] = cached
        else:
            pending.append(finding)

    if not pending:
        return results

    if call_model is None:
        settings = settings or settings_from_env()
        if not settings.api_key:
            return results  # no model configured — degrade silently
        call_model = _make_anthropic_call(settings)

    refs_by_id = {f.id: f.facts_refs for f in pending}
    allowed_ids = set(refs_by_id)
    violation_note = ""

    for _ in range(_MAX_ATTEMPTS):
        remaining = [f for f in pending if f.id not in results]
        if not remaining:
            break
        prompt = _build_prompt(remaining, facts, violation_note)
        try:
            raw = call_model(prompt)
            accepted, violations = _parse_and_validate(raw, allowed_ids, refs_by_id)
        except Exception:
            break  # network / provider failure: keep whatever we have
        for finding_id, text in accepted.items():
            results[finding_id] = text
            cache.set(facts.facts_hash, finding_id, text)
        if not violations:
            break
        violation_note = "Your previous response had problems: " + "; ".join(
            f"{fid}: {reason}" for fid, reason in violations.items()
        )

    return results


def _parse_and_validate(
    raw: str, allowed_ids: set[str], refs_by_id: dict[str, list[str]]
) -> tuple[dict[str, str], dict[str, str]]:
    response = NarrationResponse.model_validate_json(_extract_json(raw))
    accepted: dict[str, str] = {}
    violations: dict[str, str] = {}
    for item in response.narrations:
        if item.id not in allowed_ids:
            continue  # id allowlist — invented finding ids are dropped
        ok, reason = validate_narration(item.text, refs_by_id[item.id])
        if ok:
            accepted[item.id] = item.text.strip()
        else:
            violations[item.id] = reason
    return accepted, violations


def _extract_json(raw: str) -> str:
    """Tolerate a stray ```json fence or surrounding prose around the object."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return raw
    return raw[start : end + 1]


def _build_prompt(findings: list[Finding], facts: Facts, violation_note: str) -> str:
    payload = {
        "commit_subject": facts.message_subject,
        "findings": [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "title": f.title,
                "subject": f.subject,
                "evidence": f.evidence,
                "allowed_identifiers": f.facts_refs,
            }
            for f in findings
        ],
    }
    instructions = (
        "You are annotating the findings of a deterministic code analyzer.\n"
        "For each finding, write ONE plain-English sentence (<= 60 words) that a\n"
        "reviewer would want to read. Do not invent facts. You may ONLY mention\n"
        "identifiers that appear in that finding's allowed_identifiers list; refer\n"
        "to anything else in generic words. No code blocks, no backticks.\n"
        'Respond with STRICT JSON only: {"narrations":[{"id":"...","text":"..."}]}\n'
        "Use the exact finding ids given. Do not add findings.\n"
    )
    if violation_note:
        instructions += "\n" + violation_note + "\n"
    return instructions + "\nFINDINGS:\n" + json.dumps(payload, indent=2)


def _make_anthropic_call(settings: NarrationSettings) -> ModelCall:
    def call(prompt: str) -> str:
        import httpx  # imported lazily so stages that never narrate stay import-light

        response = httpx.post(
            settings.base_url,
            headers={
                "x-api-key": settings.api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.model,
                "max_tokens": settings.max_tokens,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=settings.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )

    return call
