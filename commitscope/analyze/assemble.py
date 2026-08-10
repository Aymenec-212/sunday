"""Assemble the analyzer outputs into a sorted, hashed ``Facts`` artifact.

Every list is sorted by a documented, stable key *before* the model is built —
``os.walk``/``glob``/``set`` iteration order must never leak into the hash.
"""

from __future__ import annotations

from commitscope.analyze.contracts import (
    collect_contracts,
    collect_documented_env_vars,
    collect_imported_top_modules,
)
from commitscope.analyze.layers import collect_import_edges
from commitscope.analyze.refs import build_reference_index
from commitscope.analyze.symbols import diff_file
from commitscope.collect.git import GitRepo
from commitscope.config import Config
from commitscope.models import (
    CommitData,
    Facts,
    FileChange,
    ImportEdge,
    Reference,
    SignatureChange,
    SymbolRef,
)


def build_facts(repo: GitRepo, commit: CommitData, config: Config) -> Facts:
    symbols_added: list[SymbolRef] = []
    symbols_removed: list[SymbolRef] = []
    signature_changes: list[SignatureChange] = []

    for change in commit.files:
        if not change.path.endswith(".py"):
            continue
        old_path = (
            change.old_path if change.status == "R" and change.old_path
            else change.path
        )
        before = None if change.status == "A" else repo.show_file(commit.parent_sha, old_path)
        after = None if change.status == "D" else repo.show_file(commit.sha, change.path)
        added, removed, sig = diff_file(change.path, before, after)
        symbols_added.extend(added)
        symbols_removed.extend(removed)
        signature_changes.extend(sig)

    targets = (
        {c.qualname for c in signature_changes}
        | {s.qualname for s in symbols_removed}
        | {s.qualname for s in symbols_added}
    )
    changed_paths = {c.path for c in commit.files}
    references = build_reference_index(repo, commit.sha, targets, changed_paths, config)

    contracts = collect_contracts(repo, commit, config)
    edges_added, edges_removed = collect_import_edges(repo, commit, config)

    facts = Facts(
        sha=commit.sha,
        parent_sha=commit.parent_sha,
        author_email=commit.author_email,
        committed_at=commit.committed_at,
        message_subject=commit.message_subject,
        is_merge=commit.is_merge,
        files=_sorted_files(commit.files),
        symbols_added=_sorted_symbols(symbols_added),
        symbols_removed=_sorted_symbols(symbols_removed),
        signature_changes=sorted(signature_changes, key=lambda c: c.qualname),
        references_to_changed=_sorted_refs(references),
        import_edges_added=_sorted_edges(edges_added),
        import_edges_removed=_sorted_edges(edges_removed),
        env_vars_added=sorted(contracts.env_vars_added),
        env_vars_removed=sorted(contracts.env_vars_removed),
        deps_added=sorted(contracts.deps_added),
        deps_removed=sorted(contracts.deps_removed),
        docs_touched=sorted(contracts.docs_touched),
        tests_touched=sorted(contracts.tests_touched),
        documented_env_vars=collect_documented_env_vars(repo, commit.sha, config),
        imported_top_modules=collect_imported_top_modules(repo, commit.sha, config),
    )
    facts.facts_hash = facts.compute_hash()
    return facts


def _sorted_files(files: list[FileChange]) -> list[FileChange]:
    return sorted(files, key=lambda f: f.path)


def _sorted_symbols(symbols: list[SymbolRef]) -> list[SymbolRef]:
    return sorted(symbols, key=lambda s: (s.qualname, s.path, s.lineno))


def _sorted_refs(refs: list[Reference]) -> list[Reference]:
    return sorted(refs, key=lambda r: (r.qualname, r.from_path, r.lineno))


def _sorted_edges(edges: list[ImportEdge]) -> list[ImportEdge]:
    return sorted(edges, key=lambda e: (e.from_module, e.to_module))
