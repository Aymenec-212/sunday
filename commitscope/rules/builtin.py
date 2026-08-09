"""The eight built-in rules. Pure functions: ``(Facts, Config) -> [Finding]``.

No I/O, no network, no file reads. Every fact a finding is allowed to mention
is recorded in ``facts_refs`` so the narration grounding check (stage 4) can
reject anything invented.
"""

from __future__ import annotations

import re
from collections import defaultdict

from commitscope.config import Config
from commitscope.models import Facts, Finding, Reference


def _normalize_dist_name(name: str) -> str:
    """PEP 503 normalization for comparing dep names to import names."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()

# dist-name (PEP 503) -> the top-level module it actually imports as.
_IMPORT_ALIASES = {
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "pillow": "pil",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
    "python-dateutil": "dateutil",
    "msgpack-python": "msgpack",
    "protobuf": "google",
    "setuptools": "setuptools",
}


def _finding(
    rule_id: str,
    severity: str,
    subject: str,
    title: str,
    evidence: list[str],
    facts_refs: list[str],
) -> Finding:
    refs = sorted({r for r in facts_refs if r})
    return Finding(
        id=f"{rule_id}:{subject}",
        rule_id=rule_id,
        severity=severity,  # type: ignore[arg-type]
        subject=subject,
        title=title,
        evidence=sorted(set(evidence)),
        facts_refs=refs,
    )


def _short(qualname: str) -> str:
    return qualname.rsplit(".", 1)[-1]


def _external_refs_by_qualname(facts: Facts) -> dict[str, list[Reference]]:
    grouped: dict[str, list[Reference]] = defaultdict(list)
    for ref in facts.references_to_changed:
        if not ref.in_this_commit:
            grouped[ref.qualname].append(ref)
    return grouped


def _module_path(module: str) -> str:
    return f"{module.replace('.', '/')}.py"


# -- R001 --------------------------------------------------------------------


def breaking_signature(facts: Facts, config: Config) -> list[Finding]:
    external = _external_refs_by_qualname(facts)
    findings: list[Finding] = []
    for change in facts.signature_changes:
        if not (change.params_without_default_added or change.params_removed):
            continue
        callers = external.get(change.qualname, [])
        if not callers:
            continue
        short = _short(change.qualname)
        evidence = [f"{r.from_path}:{r.lineno}" for r in callers]
        findings.append(
            _finding(
                "R001",
                "high",
                change.qualname,
                f"Breaking change to `{short}` with {len(callers)} external caller(s)",
                evidence,
                [change.qualname, short]
                + change.params_without_default_added
                + change.params_removed
                + [r.from_path for r in callers],
            )
        )
    return findings


# -- R002 --------------------------------------------------------------------


def public_symbol_removed(facts: Facts, config: Config) -> list[Finding]:
    external = _external_refs_by_qualname(facts)
    findings: list[Finding] = []
    for symbol in facts.symbols_removed:
        if not symbol.is_public:
            continue
        callers = external.get(symbol.qualname, [])
        if not callers:
            continue
        short = _short(symbol.qualname)
        evidence = [f"{r.from_path}:{r.lineno}" for r in callers]
        findings.append(
            _finding(
                "R002",
                "high",
                symbol.qualname,
                f"Public symbol `{short}` removed but still referenced by "
                f"{len(callers)} caller(s)",
                evidence,
                [symbol.qualname, short, symbol.path]
                + [r.from_path for r in callers],
            )
        )
    return findings


# -- R003 --------------------------------------------------------------------


def layer_violation(facts: Facts, config: Config) -> list[Finding]:
    allowed = {tuple(edge) for edge in config.allowed_edges}
    findings: list[Finding] = []
    for edge in facts.import_edges_added:
        if edge.from_layer is None or edge.to_layer is None:
            continue
        if edge.from_layer == edge.to_layer:
            continue
        if (edge.from_layer, edge.to_layer) in allowed:
            continue
        subject = f"{edge.from_module}->{edge.to_module}"
        from_path = _module_path(edge.from_module)
        findings.append(
            _finding(
                "R003",
                "high",
                subject,
                f"Layer violation: `{edge.from_layer}` must not import "
                f"`{edge.to_layer}` ({edge.from_module} -> {edge.to_module})",
                [from_path],
                [
                    edge.from_module,
                    edge.to_module,
                    from_path,
                    _module_path(edge.to_module),
                ],
            )
        )
    return findings


# -- R004 --------------------------------------------------------------------


def undocumented_env_var(facts: Facts, config: Config) -> list[Finding]:
    documented = set(facts.documented_env_vars)
    findings: list[Finding] = []
    for name in facts.env_vars_added:
        if name in documented:
            continue
        example = config.env_example_paths[0] if config.env_example_paths else ".env.example"
        findings.append(
            _finding(
                "R004",
                "medium",
                name,
                f"Environment variable `{name}` is read but not documented",
                [f"{example} (missing {name})"],
                [name, example, *config.doc_paths],
            )
        )
    return findings


# -- R005 --------------------------------------------------------------------


def wide_blast_radius(facts: Facts, config: Config) -> list[Finding]:
    # Blast radius is a concern for symbols that *changed* under callers, not
    # for brand-new symbols added alongside their own callers in this commit.
    changed = {c.qualname for c in facts.signature_changes}
    changed |= {s.qualname for s in facts.symbols_removed}

    grouped: dict[str, list[Reference]] = defaultdict(list)
    for ref in facts.references_to_changed:
        if ref.qualname in changed:
            grouped[ref.qualname].append(ref)

    findings: list[Finding] = []
    for qualname, refs in grouped.items():
        files = sorted({r.from_path for r in refs})
        if len(refs) < config.blast_threshold or len(files) < 3:
            continue
        short = _short(qualname)
        findings.append(
            _finding(
                "R005",
                "medium",
                qualname,
                f"Wide blast radius: `{short}` changed and is referenced "
                f"{len(refs)} times across {len(files)} files",
                files,
                [qualname, short, *files],
            )
        )
    return findings


# -- R006 --------------------------------------------------------------------


def unimported_dependency(facts: Facts, config: Config) -> list[Finding]:
    imported = set(facts.imported_top_modules)
    findings: list[Finding] = []
    for dep in facts.deps_added:
        canonical = _normalize_dist_name(dep)
        candidates = {canonical, _IMPORT_ALIASES.get(canonical, canonical)}
        if candidates & imported:
            continue
        findings.append(
            _finding(
                "R006",
                "medium",
                dep,
                f"Dependency `{dep}` was added but is never imported",
                [],
                [dep, canonical],
            )
        )
    return findings


# -- R007 --------------------------------------------------------------------


def arch_doc_stale(facts: Facts, config: Config) -> list[Finding]:
    edges = facts.import_edges_added + facts.import_edges_removed
    if not edges:
        return []
    if any(change.path == config.architecture_doc for change in facts.files):
        return []

    modules = sorted(
        {e.from_module for e in edges} | {e.to_module for e in edges}
    )
    evidence = sorted(f"{e.from_module} -> {e.to_module}" for e in edges)
    return [
        _finding(
            "R007",
            "low",
            config.architecture_doc,
            f"Import graph changed ({len(edges)} edge(s)) but "
            f"`{config.architecture_doc}` was not updated",
            evidence,
            [config.architecture_doc, *modules],
        )
    ]


# -- R008 --------------------------------------------------------------------


def test_gap(facts: Facts, config: Config) -> list[Finding]:
    if facts.tests_touched:
        return []
    findings: list[Finding] = []
    for symbol in facts.symbols_added:
        if symbol.kind == "module_var" or not symbol.is_public:
            continue
        if not config.is_source_path(symbol.path):
            continue
        short = _short(symbol.qualname)
        findings.append(
            _finding(
                "R008",
                "low",
                symbol.qualname,
                f"New public {symbol.kind} `{short}` added with no test changes",
                [f"{symbol.path}:{symbol.lineno}"],
                [symbol.qualname, short, symbol.path],
            )
        )
    return findings


BUILTIN_RULES = [
    breaking_signature,
    public_symbol_removed,
    layer_violation,
    undocumented_env_var,
    wide_blast_radius,
    unimported_dependency,
    arch_doc_stale,
    test_gap,
]
