"""Load and validate commitscope.yaml."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    # Layers are the one thing that cannot be inferred — architecture must be
    # declared, so an undeclared repo simply has R003 off. Everything else has
    # a sensible zero-config default so CommitScope works on any Python repo.
    layers: dict[str, list[str]] = Field(default_factory=dict)
    allowed_edges: list[tuple[str, str]] = Field(default_factory=list)
    skip_globs: list[str] = Field(
        default_factory=lambda: [
            "docs/**",
            "**/*.md",
            "**/package-lock.json",
            "**/poetry.lock",
            "**/*.lock",
            "vendor/**",
            "**/*.ipynb",
        ]
    )
    skip_merge_commits: bool = True
    blast_threshold: int = 5
    max_files_changed: int = 100
    max_lines_changed: int = 3000
    max_files_indexed: int = 2000
    # Empty means "auto-detect from the repo tree at run time" (see pipeline).
    source_roots: list[str] = Field(default_factory=list)
    test_patterns: list[str] = Field(
        default_factory=lambda: ["tests/**", "test/**", "**/test_*.py", "**/*_test.py"]
    )
    env_example_paths: list[str] = Field(default_factory=lambda: [".env.example"])
    doc_paths: list[str] = Field(
        default_factory=lambda: ["README.md", "ARCHITECTURE.md"]
    )
    architecture_doc: str = "ARCHITECTURE.md"
    run_timeout_seconds: int = 90

    @field_validator("allowed_edges", mode="before")
    @classmethod
    def _normalize_edges(cls, value: object) -> list[tuple[str, str]]:
        if not value:
            return []
        return [(edge[0], edge[1]) for edge in value]  # type: ignore[index]

    def resolve_layer(self, path: str) -> str | None:
        normalized = path.replace("\\", "/")
        for layer_name, patterns in sorted(self.layers.items()):
            if any(_glob_match(normalized, pattern) for pattern in patterns):
                return layer_name
        return None

    def is_skipped_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return any(_glob_match(normalized, pattern) for pattern in self.skip_globs)

    def is_test_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return any(_glob_match(normalized, pattern) for pattern in self.test_patterns)

    def is_source_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        for root in self.source_roots:
            if root in ("", "."):  # flat layout: the repo root is the source root
                return True
            if normalized == root or normalized.startswith(f"{root}/"):
                return True
        return False


def _glob_match(path: str, pattern: str) -> bool:
    """Glob match with ``**`` globstar semantics that ``fnmatch`` lacks.

    ``**/*.md`` also matches a root-level ``README.md``; ``docs/**`` matches the
    directory itself and everything beneath it.
    """
    if fnmatch(path, pattern):
        return True
    if pattern.startswith("**/") and fnmatch(path, pattern[3:]):
        return True
    if pattern.endswith("/**"):
        base = pattern[:-3]
        if path == base or path.startswith(f"{base}/"):
            return True
    return False


def load_config(path: Path | None = None) -> Config:
    config_path = path or Path("commitscope.yaml")
    if not config_path.exists():
        return Config()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return Config.model_validate(raw)
