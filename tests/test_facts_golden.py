"""Golden facts: assert the analyzer's output is *true*, not merely stable.

Two layers of protection:
  * explicit assertions that document what each fixture commit should surface;
  * a full-snapshot compare against committed golden JSON (regression guard).

Regenerate snapshots after an intentional change with:
    COMMITSCOPE_REGEN=1 pytest tests/test_facts_golden.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from commitscope.analyze.assemble import build_facts
from commitscope.collect.git import GitRepo
from commitscope.config import Config
from commitscope.models import Facts
from tests.fixtures.build_repo import COMMIT_DESCRIPTIONS

_GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"


def _facts_for(git: GitRepo, config: Config, sha: str) -> Facts:
    return build_facts(git, git.get_commit_data(sha), config)


@pytest.mark.parametrize("key", list(COMMIT_DESCRIPTIONS))
def test_golden_snapshot(
    key: str, git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = _facts_for(git, project_config, shas[key])
    got = json.loads(facts.model_dump_json())

    path = _GOLDEN_DIR / f"{key}.json"
    if os.environ.get("COMMITSCOPE_REGEN"):
        _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert path.exists(), f"missing golden file for {key} (run COMMITSCOPE_REGEN=1)"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert got == expected


# -- explicit truth assertions ----------------------------------------------


def test_c04_signature_break_has_external_callers(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = _facts_for(git, project_config, shas["c04_break_signature"])
    changes = [c for c in facts.signature_changes if c.qualname.endswith("chunk_audio")]
    assert changes, "expected chunk_audio signature change"
    assert "normalize" in changes[0].params_without_default_added
    external = [r for r in facts.references_to_changed if not r.in_this_commit]
    assert {r.from_path for r in external} == {"src/api/routes.py", "tests/test_audio.py"}


def test_c05_layer_violation_edge(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = _facts_for(git, project_config, shas["c05_layer_violation"])
    edges = [(e.from_layer, e.to_layer) for e in facts.import_edges_added]
    assert ("core", "api") in edges


def test_c06_env_var_added(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = _facts_for(git, project_config, shas["c06_undocumented_env"])
    assert facts.env_vars_added == ["API_KEY"]


def test_c07_dependency_added(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = _facts_for(git, project_config, shas["c07_unimported_dep"])
    assert "pandas" in facts.deps_added


def test_c09_public_symbol_added_without_tests(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = _facts_for(git, project_config, shas["c09_test_gap"])
    added = {s.qualname for s in facts.symbols_added if s.is_public}
    assert "src.core.audio.resample_audio" in added
    assert facts.tests_touched == []


def test_c10_public_removal_with_external_reference(
    git_repo: tuple[GitRepo, dict[str, str]], project_config: Config
) -> None:
    git, shas = git_repo
    facts = _facts_for(git, project_config, shas["c10_remove_symbol"])
    removed = {s.qualname for s in facts.symbols_removed if s.is_public}
    assert "src.core.audio.normalize_audio" in removed
    external = [
        r
        for r in facts.references_to_changed
        if r.qualname == "src.core.audio.normalize_audio" and not r.in_this_commit
    ]
    assert external, "expected a dangling external reference to the removed symbol"
