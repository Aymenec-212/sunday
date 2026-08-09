"""Rule engine: run pure rules over Facts, order the findings deterministically."""

from __future__ import annotations

from typing import Callable

from commitscope.config import Config
from commitscope.models import Facts, Finding

Rule = Callable[[Facts, Config], list[Finding]]

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def run_rules(facts: Facts, config: Config, rules: list[Rule] | None = None) -> list[Finding]:
    from commitscope.rules.builtin import BUILTIN_RULES

    active = rules if rules is not None else BUILTIN_RULES
    findings: list[Finding] = []
    for rule in active:
        findings.extend(rule(facts, config))
    return sort_findings(findings)


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.rule_id, f.id),
    )
