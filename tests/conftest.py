"""Shared fixtures: a single built sample repo per test session."""

from __future__ import annotations

from pathlib import Path

import pytest

from commitscope.collect.git import GitRepo
from commitscope.config import Config, load_config
from tests.fixtures.build_repo import build_repo

# Tests run against the generated sample repo (src/ layout), not this project.
_CONFIG_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_config.yaml"


@pytest.fixture(scope="session")
def sample_repo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    target = tmp_path_factory.mktemp("commitscope_sample")
    shas = build_repo(target)
    return target, shas


@pytest.fixture(scope="session")
def git_repo(sample_repo: tuple[Path, dict[str, str]]) -> tuple[GitRepo, dict[str, str]]:
    target, shas = sample_repo
    return GitRepo(target), shas


@pytest.fixture(scope="session")
def project_config() -> Config:
    return load_config(_CONFIG_PATH)
