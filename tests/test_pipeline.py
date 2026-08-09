"""Skip conditions and end-to-end run_commit behavior."""

from __future__ import annotations

from datetime import datetime, timezone

from commitscope.collect.git import GitRepo
from commitscope.config import Config
from commitscope.models import CommitData, FileChange
from commitscope.pipeline import run_commit, skip_reason


def _commit(**overrides) -> CommitData:
    base = dict(
        sha="a" * 40,
        parent_sha="b" * 40,
        author_email="dev@example.com",
        committed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        message_subject="change things",
        message_body="",
        is_merge=False,
        files=[FileChange(path="src/core/a.py", status="M", lines_added=3, lines_removed=1)],
    )
    base.update(overrides)
    return CommitData(**base)


def test_skip_merge_commit() -> None:
    assert skip_reason(_commit(is_merge=True), Config()) == "merge commit"


def test_skip_scope_marker() -> None:
    commit = _commit(message_subject="[skip scope] tidy")
    assert "skip scope" in (skip_reason(commit, Config()) or "")


def test_skip_when_all_files_docs() -> None:
    config = Config(skip_globs=["**/*.md"])
    commit = _commit(files=[FileChange(path="README.md", status="M", lines_added=1, lines_removed=0)])
    assert skip_reason(commit, config) == "all changed files match skip globs"


def test_skip_too_many_files() -> None:
    config = Config(max_files_changed=2)
    files = [FileChange(path=f"src/f{i}.py", status="A", lines_added=1, lines_removed=0) for i in range(5)]
    assert "too many files" in (skip_reason(_commit(files=files), config) or "")


def test_skip_too_many_lines() -> None:
    config = Config(max_lines_changed=10)
    commit = _commit(files=[FileChange(path="src/big.py", status="M", lines_added=50, lines_removed=0)])
    assert "too many lines" in (skip_reason(commit, config) or "")


def test_normal_commit_not_skipped() -> None:
    assert skip_reason(_commit(), Config()) is None


def test_run_commit_produces_findings(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    result = run_commit(git, shas["c04_break_signature"], project_config)
    assert not result.skipped
    assert any(f.rule_id == "R001" for f in result.findings)
    assert result.report.startswith("<!-- commitscope:")


def test_run_commit_skips_marked_commit(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    result = run_commit(git, shas["c12_skip_scope"], project_config)
    assert result.skipped
    assert "Skipped" in result.report
