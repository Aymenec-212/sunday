"""Tests for the collect stage (git wrapper)."""

from __future__ import annotations

from pathlib import Path

import pytest

from commitscope.collect.git import GitRepo, _parse_name_status, _parse_numstat
from tests.fixtures.build_repo import build_repo


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> tuple[GitRepo, dict[str, str]]:
    target = tmp_path_factory.mktemp("collect_repo")
    shas = build_repo(target)
    return GitRepo(target), shas


def test_commit_metadata(repo: tuple[GitRepo, dict[str, str]]) -> None:
    git, shas = repo
    data = git.get_commit_data(shas["c04_break_signature"])
    assert data.sha == shas["c04_break_signature"]
    assert data.parent_sha == shas["c03_add_api_route"]
    assert data.is_merge is False
    assert data.author_email == "fixture@commitscope.test"
    assert data.message_subject.startswith("Break chunk_audio signature")
    assert [f.path for f in data.files] == ["src/core/audio.py"]
    assert data.files[0].status == "M"


def test_root_commit_has_no_parent(repo: tuple[GitRepo, dict[str, str]]) -> None:
    git, shas = repo
    data = git.get_commit_data(shas["c01_scaffold"])
    assert data.parent_sha == ""
    # --root makes every file in the initial commit an addition.
    assert all(f.status == "A" for f in data.files)
    assert any(f.path == "src/core/audio.py" for f in data.files)


def test_show_file_reads_blob(repo: tuple[GitRepo, dict[str, str]]) -> None:
    git, shas = repo
    text = git.show_file(shas["c04_break_signature"], "src/core/audio.py")
    assert text is not None
    assert "normalize: bool" in text
    assert git.show_file(shas["c04_break_signature"], "does/not/exist.py") is None


def test_parse_name_status_rename() -> None:
    raw = "R083\x00orig.py\x00renamed.py\x00"
    assert _parse_name_status(raw) == [("R", "renamed.py", "orig.py")]


def test_parse_numstat_rename_and_binary() -> None:
    raw = "1\t0\t\x00orig.py\x00renamed.py\x00"
    assert _parse_numstat(raw) == {"renamed.py": (1, 0)}
    assert _parse_numstat("-\t-\tbin.dat\x00") == {"bin.dat": (0, 0)}
