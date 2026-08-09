"""Static symbol tables and before/after signature diffing (stdlib ast)."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from commitscope.analyze.pyast import (
    is_public_qualname,
    module_qualname,
    safe_parse,
)
from commitscope.models import SignatureChange, SymbolRef


@dataclass
class _Param:
    name: str
    annotation: str | None
    default: str | None       # repr of default, None when no default
    star: str | None          # "*" for *args, "**" for **kwargs, else None


@dataclass
class _Signature:
    params: list[_Param]
    return_annotation: str | None

    def rendered(self, name: str) -> str:
        return f"{name}({_render_params(self.params)})" + (
            f" -> {self.return_annotation}" if self.return_annotation else ""
        )


@dataclass
class _Symbol:
    qualname: str
    path: str
    lineno: int
    kind: str                 # function | method | class | module_var
    signature: _Signature | None

    def to_ref(self) -> SymbolRef:
        return SymbolRef(
            qualname=self.qualname,
            path=self.path,
            lineno=self.lineno,
            kind=self.kind,  # type: ignore[arg-type]
            is_public=is_public_qualname(self.qualname),
        )


def build_symbol_table(source: str | None, path: str) -> dict[str, _Symbol]:
    """Map qualname -> symbol for the top level (and one class level) of a file."""
    tree = safe_parse(source)
    if tree is None:
        return {}
    module = module_qualname(path)
    table: dict[str, _Symbol] = {}

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qn = f"{module}.{node.name}"
            table[qn] = _Symbol(qn, path, node.lineno, "function", _signature(node))
        elif isinstance(node, ast.ClassDef):
            qn = f"{module}.{node.name}"
            table[qn] = _Symbol(qn, path, node.lineno, "class", None)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    mqn = f"{module}.{node.name}.{child.name}"
                    table[mqn] = _Symbol(
                        mqn, path, child.lineno, "method", _signature(child)
                    )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target_name in _assign_target_names(node):
                qn = f"{module}.{target_name}"
                table[qn] = _Symbol(qn, path, node.lineno, "module_var", None)
    return table


def diff_file(
    path: str, before: str | None, after: str | None
) -> tuple[list[SymbolRef], list[SymbolRef], list[SignatureChange]]:
    """Diff a single file's symbols between two blob contents."""
    before_tbl = build_symbol_table(before, path)
    after_tbl = build_symbol_table(after, path)

    added = [after_tbl[q].to_ref() for q in after_tbl.keys() - before_tbl.keys()]
    removed = [before_tbl[q].to_ref() for q in before_tbl.keys() - after_tbl.keys()]

    sig_changes: list[SignatureChange] = []
    for qn in before_tbl.keys() & after_tbl.keys():
        b, a = before_tbl[qn], after_tbl[qn]
        if b.signature is None or a.signature is None:
            continue
        change = _diff_signature(qn, b.signature, a.signature)
        if change is not None:
            sig_changes.append(change)
    return added, removed, sig_changes


# -- signature extraction ----------------------------------------------------


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> _Signature:
    a = node.args
    params: list[_Param] = []

    posonly = list(a.posonlyargs)
    regular = list(a.args)
    positional = posonly + regular
    # defaults align to the tail of positional args.
    pos_defaults: list[str | None] = [None] * (
        len(positional) - len(a.defaults)
    ) + [_unparse(d) for d in a.defaults]

    for arg, default in zip(positional, pos_defaults):
        params.append(_Param(arg.arg, _unparse(arg.annotation), default, None))

    if a.vararg is not None:
        params.append(_Param(a.vararg.arg, _unparse(a.vararg.annotation), None, "*"))

    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        params.append(
            _Param(arg.arg, _unparse(arg.annotation), _unparse(default), None)
        )

    if a.kwarg is not None:
        params.append(_Param(a.kwarg.arg, _unparse(a.kwarg.annotation), None, "**"))

    return _Signature(params=params, return_annotation=_unparse(node.returns))


def _diff_signature(
    qualname: str, before: _Signature, after: _Signature
) -> SignatureChange | None:
    before_params = {p.name: p for p in before.params if p.star is None}
    after_params = {p.name: p for p in after.params if p.star is None}

    added_names = [n for n in after_params if n not in before_params]
    removed_names = [n for n in before_params if n not in after_params]

    params_without_default_added = [
        n for n in added_names if after_params[n].default is None
    ]
    defaults_changed = [
        n
        for n in before_params.keys() & after_params.keys()
        if before_params[n].default != after_params[n].default
    ]
    return_changed = before.return_annotation != after.return_annotation

    if not (
        added_names
        or removed_names
        or defaults_changed
        or return_changed
    ):
        return None

    return SignatureChange(
        qualname=qualname,
        before=before.rendered(qualname.rsplit(".", 1)[-1]),
        after=after.rendered(qualname.rsplit(".", 1)[-1]),
        params_added=sorted(added_names),
        params_removed=sorted(removed_names),
        params_without_default_added=sorted(params_without_default_added),
        defaults_changed=sorted(defaults_changed),
        return_annotation_changed=return_changed,
    )


# -- rendering / small helpers ----------------------------------------------


def _render_params(params: list[_Param]) -> str:
    chunks: list[str] = []
    for p in params:
        prefix = p.star or ""
        text = f"{prefix}{p.name}"
        if p.annotation:
            text += f": {p.annotation}"
        if p.default is not None:
            text += f" = {p.default}" if p.annotation else f"={p.default}"
        chunks.append(text)
    return ", ".join(chunks)


def _assign_target_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    names: list[str] = []
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
    return names


def _unparse(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    return ast.unparse(node)
