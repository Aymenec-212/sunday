"""CLI smoke tests: explain, run (writes artifacts), and never-raise contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from commitscope.cli import main
from commitscope.collect.git import GitRepo


def test_explain_reports_findings(
    git_repo: tuple[GitRepo, dict[str, str]], capsys: pytest.CaptureFixture[str]
) -> None:
    git, shas = git_repo
    code = main(["explain", "--sha", shas["c04_break_signature"], "--repo", str(git.root)])
    assert code == 0
    out = capsys.readouterr().out
    assert "R001" in out


def test_run_writes_artifacts(
    git_repo: tuple[GitRepo, dict[str, str]], tmp_path: Path
) -> None:
    git, shas = git_repo
    short = shas["c05_layer_violation"][:8]
    code = main([
        "run",
        "--sha", shas["c05_layer_violation"],
        "--repo", str(git.root),
        "--output", str(tmp_path),
        "--no-llm",
    ])
    assert code == 0
    assert (tmp_path / f"report-{short}.md").exists()
    assert (tmp_path / f"facts-{short}.json").exists()
    assert (tmp_path / f"findings-{short}.json").exists()
    assert "R003" in (tmp_path / f"report-{short}.md").read_text(encoding="utf-8")


def test_bad_sha_exits_zero_by_default(
    git_repo: tuple[GitRepo, dict[str, str]], tmp_path: Path
) -> None:
    git, _ = git_repo
    # A garbage sha must not raise or return non-zero — observer, not a gate.
    code = main([
        "explain", "--sha", "deadbeefdeadbeef", "--repo", str(git.root),
    ])
    assert code == 0


def test_bad_sha_exits_nonzero_with_strict(
    git_repo: tuple[GitRepo, dict[str, str]]
) -> None:
    git, _ = git_repo
    code = main([
        "--strict", "explain", "--sha", "deadbeefdeadbeef", "--repo", str(git.root),
    ])
    assert code == 1
