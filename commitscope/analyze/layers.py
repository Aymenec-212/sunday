"""Import edges between first-party modules, tagged with architectural layers."""

from __future__ import annotations

from commitscope.analyze.pyast import extract_imports, module_qualname, safe_parse
from commitscope.collect.git import GitRepo
from commitscope.config import Config
from commitscope.models import CommitData, ImportEdge

# An edge, as a hashable tuple: (from_module, to_module, from_layer, to_layer)
_Edge = tuple[str, str, str | None, str | None]


def collect_import_edges(
    repo: GitRepo, commit: CommitData, config: Config
) -> tuple[list[ImportEdge], list[ImportEdge]]:
    after_tree = set(repo.list_tree_files(commit.sha))
    before_tree = (
        set(repo.list_tree_files(commit.parent_sha)) if commit.parent_sha else set()
    )

    before_edges: set[_Edge] = set()
    after_edges: set[_Edge] = set()

    for change in commit.files:
        if not change.path.endswith(".py"):
            continue

        if change.status != "A":
            old_path = (
                change.old_path if change.status == "R" and change.old_path
                else change.path
            )
            source = repo.show_file(commit.parent_sha, old_path)
            before_edges |= _edges_from(source, old_path, before_tree, config)

        if change.status != "D":
            source = repo.show_file(commit.sha, change.path)
            after_edges |= _edges_from(source, change.path, after_tree, config)

    added = [_to_model(e) for e in sorted(after_edges - before_edges)]
    removed = [_to_model(e) for e in sorted(before_edges - after_edges)]
    return added, removed


def _edges_from(
    source: str | None, path: str, tree: set[str], config: Config
) -> set[_Edge]:
    tree_module = safe_parse(source)
    if tree_module is None:
        return set()
    from_module = module_qualname(path)
    imports = extract_imports(tree_module, from_module)

    edges: set[_Edge] = set()
    for to_module in imports.imported_modules:
        if to_module == from_module:
            continue
        if not _is_internal(to_module, tree):
            continue
        edges.add(
            (
                from_module,
                to_module,
                config.resolve_layer(path),
                config.resolve_layer(_module_to_path(to_module)),
            )
        )
    return edges


def _is_internal(module: str, tree: set[str]) -> bool:
    stem = module.replace(".", "/")
    return f"{stem}.py" in tree or f"{stem}/__init__.py" in tree


def _module_to_path(module: str) -> str:
    # A representative path for layer-glob matching (works for module or package).
    return f"{module.replace('.', '/')}.py"


def _to_model(edge: _Edge) -> ImportEdge:
    from_module, to_module, from_layer, to_layer = edge
    return ImportEdge(
        from_module=from_module,
        to_module=to_module,
        from_layer=from_layer,
        to_layer=to_layer,
    )
