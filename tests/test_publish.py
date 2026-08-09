"""Publish helpers: marker matching and job-summary writing (no network)."""

from __future__ import annotations

from pathlib import Path

from commitscope.publish.github import find_existing_comment, write_job_summary
from commitscope.render.markdown import comment_marker


def test_find_existing_comment_matches_marker() -> None:
    sha = "c" * 40
    comments = [
        {"id": 1, "body": "unrelated chatter"},
        {"id": 2, "body": f"{comment_marker(sha)}\n# report"},
    ]
    assert find_existing_comment(comments, sha) == 2


def test_find_existing_comment_none_when_absent() -> None:
    comments = [{"id": 1, "body": "hello"}, {"id": 2, "body": None}]
    assert find_existing_comment(comments, "d" * 40) is None


def test_write_job_summary(tmp_path: Path, monkeypatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert write_job_summary("# hello") is True
    assert "# hello" in summary.read_text(encoding="utf-8")


def test_write_job_summary_noop_without_env(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert write_job_summary("# hello") is False
