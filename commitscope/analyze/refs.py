"""Repo-wide reference index: who calls the symbols this commit changed.

Reads every ``.py`` blob at the commit and resolves dotted names against each
file's imports, so a call to ``chunk_audio`` in another module is attributed
to ``src.core.audio.chunk_audio``.
"""

from __future__ import annotations

import ast

from commitscope.analyze.pyast import (
    extract_imports,
    module_qualname,
    safe_parse,
    select_python_files,
)
from commitscope.collect.git import GitRepo
from commitscope.config import Config
from commitscope.models import Reference


def build_reference_index(
    repo: GitRepo,
    sha: str,
    targets: set[str],
    changed_paths: set[str],
    config: Config,
) -> list[Reference]:
    """Find references to any qualname in ``targets`` across the tree at ``sha``."""
    if not targets:
        return []

    paths = select_python_files(repo.list_tree_files(sha), config.max_files_indexed)

    references: list[Reference] = []
    for path in paths:
        source = repo.show_file(sha, path)
        tree = safe_parse(source)
        if tree is None:
            continue
        references.extend(
            _references_in_module(tree, path, targets, path in changed_paths)
        )
    return references


def _references_in_module(
    tree: ast.Module, path: str, targets: set[str], in_commit: bool
) -> list[Reference]:
    module = module_qualname(path)
    imports = extract_imports(tree, module)

    # local name -> qualified prefix it resolves to
    local_prefix: dict[str, str] = {}
    for binding in imports.bindings:
        local_prefix[binding.local_name] = binding.target_qualname

    inner_values = {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    found: list[Reference] = []
    for node in ast.walk(tree):
        if node in inner_values:
            continue  # not the outermost node of a dotted expression
        dotted = _dotted_name(node)
        if dotted is None:
            continue
        resolved = _resolve(dotted, local_prefix)
        if resolved in targets:
            found.append(
                Reference(
                    qualname=resolved,
                    from_path=path,
                    lineno=node.lineno,
                    in_this_commit=in_commit,
                )
            )
    return found


def _dotted_name(node: ast.AST) -> str | None:
    """Return the dotted string for a pure Name/Attribute chain, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _resolve(dotted: str, local_prefix: dict[str, str]) -> str:
    head, _, rest = dotted.partition(".")
    if head in local_prefix:
        prefix = local_prefix[head]
        return f"{prefix}.{rest}" if rest else prefix
    return dotted
