"""One test per rule, both directions, over hand-built Facts (pure functions)."""

from __future__ import annotations

from datetime import datetime, timezone

from commitscope.config import Config
from commitscope.models import (
    Facts,
    FileChange,
    ImportEdge,
    Reference,
    SignatureChange,
    SymbolRef,
)
from commitscope.rules import builtin
from commitscope.rules.engine import run_rules


def make_facts(**overrides) -> Facts:
    base = dict(
        sha="a" * 40,
        parent_sha="b" * 40,
        author_email="dev@example.com",
        committed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        message_subject="test",
        is_merge=False,
        files=[],
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
        documented_env_vars=[],
        imported_top_modules=[],
    )
    base.update(overrides)
    return Facts(**base)


def _sig(qualname: str, **kw) -> SignatureChange:
    return SignatureChange(
        qualname=qualname,
        before="f()",
        after="f(x)",
        params_added=kw.get("params_added", []),
        params_removed=kw.get("params_removed", []),
        params_without_default_added=kw.get("params_without_default_added", []),
        defaults_changed=kw.get("defaults_changed", []),
        return_annotation_changed=kw.get("return_annotation_changed", False),
    )


def _ref(qualname: str, path: str, in_commit: bool, lineno: int = 1) -> Reference:
    return Reference(qualname=qualname, from_path=path, lineno=lineno, in_this_commit=in_commit)


def _sym(qualname: str, path: str, kind: str = "function", public: bool = True) -> SymbolRef:
    return SymbolRef(qualname=qualname, path=path, lineno=1, kind=kind, is_public=public)


# -- R001 --------------------------------------------------------------------


def test_r001_fires_on_break_with_external_caller() -> None:
    facts = make_facts(
        signature_changes=[_sig("m.f", params_without_default_added=["x"])],
        references_to_changed=[_ref("m.f", "other.py", in_commit=False)],
    )
    ids = [f.rule_id for f in builtin.breaking_signature(facts, Config())]
    assert ids == ["R001"]


def test_r001_silent_when_only_internal_callers() -> None:
    facts = make_facts(
        signature_changes=[_sig("m.f", params_without_default_added=["x"])],
        references_to_changed=[_ref("m.f", "m.py", in_commit=True)],
    )
    assert builtin.breaking_signature(facts, Config()) == []


def test_r001_silent_when_new_param_has_default() -> None:
    facts = make_facts(
        signature_changes=[_sig("m.f", params_added=["x"], defaults_changed=[])],
        references_to_changed=[_ref("m.f", "other.py", in_commit=False)],
    )
    assert builtin.breaking_signature(facts, Config()) == []


# -- R002 --------------------------------------------------------------------


def test_r002_fires_on_public_removal_with_external_ref() -> None:
    facts = make_facts(
        symbols_removed=[_sym("m.gone", "m.py")],
        references_to_changed=[_ref("m.gone", "caller.py", in_commit=False)],
    )
    assert [f.rule_id for f in builtin.public_symbol_removed(facts, Config())] == ["R002"]


def test_r002_silent_for_private_or_unreferenced() -> None:
    private = make_facts(
        symbols_removed=[_sym("m._gone", "m.py", public=False)],
        references_to_changed=[_ref("m._gone", "caller.py", in_commit=False)],
    )
    unref = make_facts(symbols_removed=[_sym("m.gone", "m.py")])
    assert builtin.public_symbol_removed(private, Config()) == []
    assert builtin.public_symbol_removed(unref, Config()) == []


# -- R003 --------------------------------------------------------------------


def test_r003_fires_on_forbidden_edge() -> None:
    config = Config(allowed_edges=[("api", "core")])
    facts = make_facts(
        import_edges_added=[
            ImportEdge(from_module="src.core.b", to_module="src.api.r",
                       from_layer="core", to_layer="api")
        ]
    )
    assert [f.rule_id for f in builtin.layer_violation(facts, config)] == ["R003"]


def test_r003_silent_on_allowed_same_or_unmapped() -> None:
    config = Config(allowed_edges=[("api", "core")])
    allowed = make_facts(import_edges_added=[
        ImportEdge(from_module="src.api.r", to_module="src.core.b",
                   from_layer="api", to_layer="core")])
    same = make_facts(import_edges_added=[
        ImportEdge(from_module="src.core.a", to_module="src.core.b",
                   from_layer="core", to_layer="core")])
    unmapped = make_facts(import_edges_added=[
        ImportEdge(from_module="x", to_module="y", from_layer=None, to_layer="core")])
    assert builtin.layer_violation(allowed, config) == []
    assert builtin.layer_violation(same, config) == []
    assert builtin.layer_violation(unmapped, config) == []


# -- R004 --------------------------------------------------------------------


def test_r004_fires_for_undocumented_env_var() -> None:
    facts = make_facts(env_vars_added=["API_KEY"], documented_env_vars=["DATABASE_URL"])
    assert [f.rule_id for f in builtin.undocumented_env_var(facts, Config())] == ["R004"]


def test_r004_silent_when_documented() -> None:
    facts = make_facts(env_vars_added=["API_KEY"], documented_env_vars=["API_KEY"])
    assert builtin.undocumented_env_var(facts, Config()) == []


# -- R005 --------------------------------------------------------------------


def test_r005_fires_on_wide_blast_radius() -> None:
    refs = [_ref("m.f", f"file{i}.py", in_commit=False) for i in range(5)]
    facts = make_facts(references_to_changed=refs)
    assert [f.rule_id for f in builtin.wide_blast_radius(facts, Config())] == ["R005"]


def test_r005_silent_below_threshold_or_few_files() -> None:
    below = make_facts(references_to_changed=[
        _ref("m.f", f"file{i}.py", in_commit=False) for i in range(2)])
    many_refs_few_files = make_facts(references_to_changed=[
        _ref("m.f", "same.py", in_commit=False, lineno=i) for i in range(6)])
    assert builtin.wide_blast_radius(below, Config()) == []
    assert builtin.wide_blast_radius(many_refs_few_files, Config()) == []


# -- R006 --------------------------------------------------------------------


def test_r006_fires_for_unimported_dep() -> None:
    facts = make_facts(deps_added=["pandas"], imported_top_modules=["requests"])
    assert [f.rule_id for f in builtin.unimported_dependency(facts, Config())] == ["R006"]


def test_r006_silent_when_imported_including_alias() -> None:
    direct = make_facts(deps_added=["pandas"], imported_top_modules=["pandas"])
    alias = make_facts(deps_added=["PyYAML"], imported_top_modules=["yaml"])
    assert builtin.unimported_dependency(direct, Config()) == []
    assert builtin.unimported_dependency(alias, Config()) == []


# -- R007 --------------------------------------------------------------------


def test_r007_fires_when_edges_change_and_arch_untouched() -> None:
    facts = make_facts(import_edges_added=[
        ImportEdge(from_module="src.a", to_module="src.b", from_layer=None, to_layer=None)],
        files=[FileChange(path="src/a.py", status="M", lines_added=1, lines_removed=0)])
    assert [f.rule_id for f in builtin.arch_doc_stale(facts, Config())] == ["R007"]


def test_r007_silent_when_arch_updated_or_no_edges() -> None:
    updated = make_facts(
        import_edges_added=[ImportEdge(from_module="src.a", to_module="src.b",
                                       from_layer=None, to_layer=None)],
        files=[FileChange(path="ARCHITECTURE.md", status="M", lines_added=1, lines_removed=0)])
    no_edges = make_facts(files=[FileChange(path="src/a.py", status="M",
                                            lines_added=1, lines_removed=0)])
    assert builtin.arch_doc_stale(updated, Config()) == []
    assert builtin.arch_doc_stale(no_edges, Config()) == []


# -- R008 --------------------------------------------------------------------


def test_r008_fires_for_new_public_symbol_without_tests() -> None:
    facts = make_facts(symbols_added=[_sym("src.m.f", "src/m.py")], tests_touched=[])
    assert [f.rule_id for f in builtin.test_gap(facts, Config())] == ["R008"]


def test_r008_silent_when_tests_touched_or_private() -> None:
    with_tests = make_facts(symbols_added=[_sym("src.m.f", "src/m.py")],
                            tests_touched=["tests/test_m.py"])
    private = make_facts(symbols_added=[_sym("src.m._f", "src/m.py", public=False)])
    outside_src = make_facts(symbols_added=[_sym("scripts.f", "scripts/f.py")])
    assert builtin.test_gap(with_tests, Config()) == []
    assert builtin.test_gap(private, Config()) == []
    assert builtin.test_gap(outside_src, Config()) == []


# -- engine ------------------------------------------------------------------


def test_engine_orders_by_severity_then_rule() -> None:
    facts = make_facts(
        signature_changes=[_sig("m.f", params_without_default_added=["x"])],
        references_to_changed=[_ref("m.f", "other.py", in_commit=False)],
        env_vars_added=["API_KEY"],
        symbols_added=[_sym("src.m.f", "src/m.py")],
        tests_touched=[],
    )
    findings = run_rules(facts, Config())
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, key=["high", "medium", "low", "info"].index)
    # high (R001) precedes medium (R004) precedes low (R008)
    assert findings[0].rule_id == "R001"
