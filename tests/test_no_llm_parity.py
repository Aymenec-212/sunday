"""--no-llm output must equal full output minus the narration lines."""

from __future__ import annotations

from commitscope.analyze.assemble import build_facts
from commitscope.collect.git import GitRepo
from commitscope.config import Config
from commitscope.render.markdown import render_report
from commitscope.rules.engine import run_rules


def _strip_narration(report: str) -> str:
    return "\n".join(
        line for line in report.splitlines() if not line.lstrip().startswith(">")
    )


def test_narration_is_purely_cosmetic(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = build_facts(git, git.get_commit_data(shas["c05_layer_violation"]), project_config)
    findings = run_rules(facts, project_config)
    assert findings, "fixture commit should produce findings"

    # A grounded narration for every finding (using an allowed identifier).
    narrations = {
        f.id: f"This concerns {f.facts_refs[0]} and matters for review."
        for f in findings
    }

    full = render_report(facts, findings, narrations)
    no_llm = render_report(facts, findings, {})

    assert full != no_llm, "narrations should visibly change the report"
    assert ">" in full
    assert _strip_narration(full) == _strip_narration(no_llm)


def test_report_is_deterministic(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = build_facts(git, git.get_commit_data(shas["c04_break_signature"]), project_config)
    findings = run_rules(facts, project_config)
    first = render_report(facts, findings, {})
    second = render_report(facts, findings, {})
    assert first == second
    assert first.startswith(f"<!-- commitscope:{facts.sha} -->")
