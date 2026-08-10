"""Shared Python-AST helpers used by several analyzers.

Kept deliberately small and side-effect free: parse text, resolve module
names, extract import bindings. No git, no filesystem, no network.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

# Directories never worth indexing, regardless of config.
SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "build", "dist",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".tox", "vendor",
}


def is_skipped_path(path: str) -> bool:
    return any(part in SKIP_DIRS for part in path.split("/"))


def select_python_files(files: list[str], cap: int) -> list[str]:
    """Deterministically pick indexable ``.py`` files, capped for safety."""
    return sorted(
        p for p in files if p.endswith(".py") and not is_skipped_path(p)
    )[:cap]


def normalize_dist_name(name: str) -> str:
    """PEP 503-style normalization for comparing dep names to import names."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def module_qualname(path: str) -> str:
    """Map a repo-relative ``.py`` path to a dotted module name.

    ``src/core/audio.py`` -> ``src.core.audio``
    ``src/core/__init__.py`` -> ``src.core``
    """
    normalized = path.replace("\\", "/")
    if normalized.endswith(".py"):
        normalized = normalized[: -len(".py")]
    parts = [p for p in normalized.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def safe_parse(source: str | None) -> ast.Module | None:
    """Parse Python source, returning ``None`` on any syntax error."""
    if source is None:
        return None
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError):
        return None


def is_public_qualname(qualname: str) -> bool:
    """Public == no dotted component is underscore-prefixed."""
    return all(not part.startswith("_") for part in qualname.split(".") if part)


@dataclass
class ImportBinding:
    """A name bound in a module by an import statement."""

    local_name: str          # name usable in the importing module
    target_qualname: str      # fully-qualified thing it points at
    target_module: str        # module the import pulls from
    lineno: int


@dataclass
class ImportInfo:
    bindings: list[ImportBinding] = field(default_factory=list)
    # module -> None; the set of modules this module imports from.
    imported_modules: set[str] = field(default_factory=set)


def extract_imports(tree: ast.Module, current_module: str) -> ImportInfo:
    """Collect import bindings from a module's top level.

    Relative imports are resolved against ``current_module``.
    """
    info = ImportInfo()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                info.bindings.append(
                    ImportBinding(
                        local_name=bound,
                        target_qualname=alias.name,
                        target_module=alias.name,
                        lineno=node.lineno,
                    )
                )
                info.imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_from_module(node, current_module)
            if module is None:
                continue
            info.imported_modules.add(module)
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                info.bindings.append(
                    ImportBinding(
                        local_name=bound,
                        target_qualname=f"{module}.{alias.name}",
                        target_module=module,
                        lineno=node.lineno,
                    )
                )
    return info


def _resolve_from_module(node: ast.ImportFrom, current_module: str) -> str | None:
    if node.level == 0:
        return node.module
    # Relative import: climb `level` packages up from the current module.
    parts = current_module.split(".")
    # A module's own package is its parent; level 1 == current package.
    base = parts[: len(parts) - node.level]
    if node.module:
        base = base + node.module.split(".")
    if not base:
        return None
    return ".".join(base)
