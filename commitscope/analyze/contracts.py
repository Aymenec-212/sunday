"""Contract-surface facts: env vars, dependencies, docs & tests touched."""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatch

from commitscope.analyze.pyast import (
    normalize_dist_name,
    safe_parse,
    select_python_files,
)
from commitscope.collect.git import GitRepo
from commitscope.config import Config
from commitscope.models import CommitData

_ENV_PATTERNS = [
    re.compile(r"environ\s*\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"(?:getenv|environ\.get)\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
]
# All-caps tokens in prose/.env docs, e.g. DATABASE_URL, API_KEY, PORT.
_DOC_ENV_TOKEN = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")

_REQUIREMENTS_FILES = ("requirements.txt",)
_PYPROJECT = "pyproject.toml"


@dataclass
class ContractsResult:
    env_vars_added: list[str] = field(default_factory=list)
    env_vars_removed: list[str] = field(default_factory=list)
    deps_added: list[str] = field(default_factory=list)
    deps_removed: list[str] = field(default_factory=list)
    docs_touched: list[str] = field(default_factory=list)
    tests_touched: list[str] = field(default_factory=list)


def collect_contracts(
    repo: GitRepo, commit: CommitData, config: Config
) -> ContractsResult:
    result = ContractsResult()

    env_added: set[str] = set()
    env_removed: set[str] = set()
    deps_added: set[str] = set()
    deps_removed: set[str] = set()

    for change in commit.files:
        path = change.path

        if _is_doc(path, config):
            result.docs_touched.append(path)
        if config.is_test_path(path):
            result.tests_touched.append(path)

        before = None if change.status == "A" else repo.show_file(commit.parent_sha, _source_path(change))
        after = None if change.status == "D" else repo.show_file(commit.sha, path)

        if path.endswith(".py"):
            before_env = _extract_env(before)
            after_env = _extract_env(after)
            env_added |= after_env - before_env
            env_removed |= before_env - after_env

        if _is_dep_manifest(path):
            before_deps = _parse_deps(path, before)
            after_deps = _parse_deps(path, after)
            deps_added |= after_deps - before_deps
            deps_removed |= before_deps - after_deps

    result.env_vars_added = sorted(env_added)
    result.env_vars_removed = sorted(env_removed)
    result.deps_added = sorted(deps_added)
    result.deps_removed = sorted(deps_removed)
    result.docs_touched.sort()
    result.tests_touched.sort()
    return result


def collect_documented_env_vars(repo: GitRepo, sha: str, config: Config) -> list[str]:
    """Env var names documented in .env.example files or the doc/README set."""
    names: set[str] = set()
    for path in config.env_example_paths:
        content = repo.show_file(sha, path)
        if not content:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key = stripped.split("=", 1)[0].strip().lstrip("export ").strip()
            if key:
                names.add(key)
    for path in config.doc_paths:
        content = repo.show_file(sha, path)
        if content:
            names.update(_DOC_ENV_TOKEN.findall(content))
    return sorted(names)


def collect_imported_top_modules(repo: GitRepo, sha: str, config: Config) -> list[str]:
    """Top-level module names imported anywhere in the tree (PEP 503 normalized)."""
    tops: set[str] = set()
    for path in select_python_files(repo.list_tree_files(sha), config.max_files_indexed):
        tree = safe_parse(repo.show_file(sha, path))
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    tops.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    tops.add(node.module.split(".")[0])
    return sorted(normalize_dist_name(t) for t in tops)


def _source_path(change) -> str:  # type: ignore[no-untyped-def]
    # For renames, read the pre-image from its old path.
    return change.old_path if change.status == "R" and change.old_path else change.path


def _extract_env(source: str | None) -> set[str]:
    if not source:
        return set()
    names: set[str] = set()
    for pattern in _ENV_PATTERNS:
        names.update(pattern.findall(source))
    return names


def _is_dep_manifest(path: str) -> bool:
    base = path.split("/")[-1]
    return base in _REQUIREMENTS_FILES or base == _PYPROJECT


def _parse_deps(path: str, source: str | None) -> set[str]:
    if not source:
        return set()
    base = path.split("/")[-1]
    if base == _PYPROJECT:
        return _parse_pyproject_deps(source)
    return _parse_requirements(source)


def _parse_requirements(source: str) -> set[str]:
    names: set[str] = set()
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        names.add(_canonical_dep(line))
    return {n for n in names if n}


def _parse_pyproject_deps(source: str) -> set[str]:
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        return set()
    project = data.get("project", {})
    specs: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    return {_canonical_dep(s) for s in specs if _canonical_dep(s)}


def _canonical_dep(spec: str) -> str:
    # Strip extras, version constraints, environment markers, comments.
    name = re.split(r"[\s<>=!~;\[@#]", spec.strip(), maxsplit=1)[0]
    # PEP 503 normalization for reliable comparison against imports later.
    return re.sub(r"[-_.]+", "-", name).lower()


def _is_doc(path: str, config: Config) -> bool:
    base = path.split("/")[-1]
    return any(
        path == pattern or base == pattern or fnmatch(path, pattern)
        for pattern in config.doc_paths
    )
