"""Render facts + findings to Markdown. Templates only — no analysis logic.

The report is deterministic: it contains no wall-clock value. A grounded
narration, when present, is added as a blockquote line under its finding and
is the *only* thing that differs from the ``--no-llm`` rendering.
"""

from __future__ import annotations

from commitscope import __version__
from commitscope.models import Facts, Finding

_SEVERITY_ORDER = ["high", "medium", "low", "info"]
_SEVERITY_LABEL = {
    "high": "🔴 High",
    "medium": "🟠 Medium",
    "low": "🟡 Low",
    "info": "⚪ Info",
}

# Deterministic, identifier-free explanations rendered even with the LLM off.
_RULE_EXPLANATION = {
    "R001": "A required parameter was added or removed while external callers still use the old signature.",
    "R002": "A public symbol was deleted while other modules still reference it.",
    "R003": "A new import crosses an architectural layer boundary that the config forbids.",
    "R004": "An environment variable is read in code but not declared in the example env file or docs.",
    "R005": "A changed symbol is referenced widely, so the change has a large blast radius.",
    "R006": "A dependency was added to the manifest but is never imported anywhere in the tree.",
    "R007": "The import graph changed but the architecture document was not updated.",
    "R008": "A new public symbol was added without any accompanying test changes.",
}


def comment_marker(sha: str) -> str:
    """Idempotency marker used to find/replace a prior comment for this commit."""
    return f"<!-- commitscope:{sha} -->"


def render_report(
    facts: Facts,
    findings: list[Finding],
    narrations: dict[str, str] | None = None,
) -> str:
    narrations = narrations or {}
    short = facts.sha[:8]
    lines: list[str] = [comment_marker(facts.sha)]
    lines.append(f"# CommitScope · `{short}` — {facts.message_subject}")
    lines.append("")
    lines.append(_summary_line(findings))
    lines.append("")

    if findings:
        lines.append("## Findings")
        for severity in _SEVERITY_ORDER:
            bucket = [f for f in findings if f.severity == severity]
            if not bucket:
                continue
            lines.append("")
            lines.append(f"### {_SEVERITY_LABEL[severity]}")
            for finding in bucket:
                lines.extend(_render_finding(finding, narrations.get(finding.id)))

    lines.append("")
    lines.append("## Commit facts")
    lines.extend(_render_facts(facts))
    lines.append("")
    lines.append("---")
    lines.append(f"_CommitScope v{__version__}_")
    lines.append("")
    return "\n".join(lines)


def render_skip_report(sha: str, subject: str, reason: str) -> str:
    short = sha[:8]
    return "\n".join(
        [
            comment_marker(sha),
            f"# CommitScope · `{short}` — {subject}",
            "",
            f"**Skipped:** {reason}",
            "",
            "---",
            f"_CommitScope v{__version__}_",
            "",
        ]
    )


def _summary_line(findings: list[Finding]) -> str:
    if not findings:
        return "**No findings.** This commit looks clean by the configured rules."
    counts = {sev: sum(1 for f in findings if f.severity == sev) for sev in _SEVERITY_ORDER}
    parts = [f"{counts[s]} {s}" for s in _SEVERITY_ORDER if counts[s]]
    total = len(findings)
    return f"**{total} finding{'s' if total != 1 else ''}** — " + ", ".join(parts)


def _render_finding(finding: Finding, narration: str | None) -> list[str]:
    out = [f"- **[{finding.rule_id}] {finding.title}**"]
    out.append(f"  - {_RULE_EXPLANATION.get(finding.rule_id, '')}".rstrip())
    if finding.evidence:
        joined = ", ".join(f"`{e}`" for e in finding.evidence)
        out.append(f"  - Evidence: {joined}")
    if finding.redacted:
        out.append("  - _Some evidence was redacted (possible secret)._")
    if narration:
        out.append(f"  > {narration}")
    return out


def _render_facts(facts: Facts) -> list[str]:
    added = sum(f.lines_added for f in facts.files)
    removed = sum(f.lines_removed for f in facts.files)
    rows = [
        f"- Files changed: {len(facts.files)} (+{added} / −{removed})",
        f"- Symbols added: {len(facts.symbols_added)}, removed: {len(facts.symbols_removed)}",
        f"- Signature changes: {len(facts.signature_changes)}",
        f"- Import edges added: {len(facts.import_edges_added)}, "
        f"removed: {len(facts.import_edges_removed)}",
    ]
    if facts.env_vars_added:
        rows.append(f"- Env vars added: {', '.join(f'`{v}`' for v in facts.env_vars_added)}")
    if facts.deps_added:
        rows.append(f"- Dependencies added: {', '.join(f'`{d}`' for d in facts.deps_added)}")
    rows.append(f"- Tests touched: {len(facts.tests_touched)}")
    return rows
