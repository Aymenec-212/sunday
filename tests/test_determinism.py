"""Determinism: the same commit always produces the same facts_hash."""

from __future__ import annotations

from pathlib import Path

from commitscope.analyze.assemble import build_facts
from commitscope.collect.git import GitRepo
from commitscope.config import Config
from tests.fixtures.build_repo import COMMIT_DESCRIPTIONS, build_repo


def test_hash_stable_across_runs(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    for key, sha in shas.items():
        commit = git.get_commit_data(sha)
        first = build_facts(git, commit, project_config)
        second = build_facts(git, commit, project_config)
        assert first.facts_hash == second.facts_hash, f"unstable hash for {key}"
        assert len(first.facts_hash) == 64


def test_hash_excludes_itself(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    commit = git.get_commit_data(shas["c04_break_signature"])
    facts = build_facts(git, commit, project_config)
    # Recomputing after the field is populated must yield the same digest.
    assert facts.compute_hash() == facts.facts_hash


def test_fixture_shas_are_reproducible(tmp_path: Path) -> None:
    a = build_repo(tmp_path / "a")
    b = build_repo(tmp_path / "b")
    assert a == b
    assert set(a) == set(COMMIT_DESCRIPTIONS)
