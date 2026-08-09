"""Smoke tests for config and models."""

from __future__ import annotations

from datetime import datetime, timezone

from commitscope.config import Config, load_config
from commitscope.models import Facts, FileChange


def test_load_default_config() -> None:
    config = Config()
    assert config.blast_threshold == 5
    assert config.skip_merge_commits is True


def test_resolve_layer() -> None:
    config = Config(
        layers={
            "api": ["src/api/**"],
            "core": ["src/core/**"],
        }
    )
    assert config.resolve_layer("src/api/routes.py") == "api"
    assert config.resolve_layer("src/core/audio.py") == "core"
    assert config.resolve_layer("other.py") is None


def test_facts_hash_is_stable() -> None:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    facts = Facts(
        sha="abc123",
        parent_sha="def456",
        author_email="dev@example.com",
        committed_at=ts,
        message_subject="test",
        is_merge=False,
        files=[
            FileChange(path="src/a.py", status="M", lines_added=1, lines_removed=0),
        ],
        symbols_added=[],
        symbols_removed=[],
        signature_changes=[],
        references_to_changed=[],
        import_edges_added=[],
        import_edges_removed=[],
        env_vars_added=[],
        env_vars_removed=[],
        deps_added=[],
        deps_removed=[],
        docs_touched=[],
        tests_touched=[],
    )
    h1 = facts.compute_hash()
    h2 = facts.compute_hash()
    assert h1 == h2
    assert len(h1) == 64
