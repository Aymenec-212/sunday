"""Test fixture repo builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.build_repo import COMMIT_DESCRIPTIONS, build_repo


@pytest.fixture(scope="module")
def fixture_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    repo = tmp_path_factory.mktemp("sample_repo")
    build_repo(repo)
    return repo


def test_build_repo_creates_commits(fixture_repo: Path) -> None:
    import subprocess

    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=fixture_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [line for line in result.stdout.strip().splitlines() if line]
    assert len(lines) == len(COMMIT_DESCRIPTIONS)


def test_build_repo_has_layer_structure(fixture_repo: Path) -> None:
    assert (fixture_repo / "src/api/routes.py").exists()
    assert (fixture_repo / "src/core/audio.py").exists()
    assert (fixture_repo / "src/infra/settings.py").exists()
