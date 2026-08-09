"""Data contracts for CommitScope. No logic."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FileChange(BaseModel):
    path: str
    status: Literal["A", "M", "D", "R"]
    old_path: str | None = None
    lines_added: int
    lines_removed: int


class SymbolRef(BaseModel):
    qualname: str
    path: str
    lineno: int
    kind: Literal["function", "method", "class", "module_var"]
    is_public: bool


class SignatureChange(BaseModel):
    qualname: str
    before: str | None
    after: str | None
    params_added: list[str]
    params_removed: list[str]
    params_without_default_added: list[str]
    defaults_changed: list[str]
    return_annotation_changed: bool


class Reference(BaseModel):
    qualname: str
    from_path: str
    lineno: int
    in_this_commit: bool


class ImportEdge(BaseModel):
    from_module: str
    to_module: str
    from_layer: str | None
    to_layer: str | None


class Facts(BaseModel):
    schema_version: int = 1
    sha: str
    parent_sha: str
    author_email: str
    committed_at: datetime
    message_subject: str
    is_merge: bool

    files: list[FileChange]
    symbols_added: list[SymbolRef]
    symbols_removed: list[SymbolRef]
    signature_changes: list[SignatureChange]
    references_to_changed: list[Reference]
    import_edges_added: list[ImportEdge]
    import_edges_removed: list[ImportEdge]
    env_vars_added: list[str]
    env_vars_removed: list[str]
    deps_added: list[str]
    deps_removed: list[str]
    docs_touched: list[str]
    tests_touched: list[str]

    facts_hash: str = ""

    def compute_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"facts_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Finding(BaseModel):
    id: str
    rule_id: str
    severity: Literal["high", "medium", "low", "info"]
    subject: str
    title: str
    evidence: list[str]
    facts_refs: list[str]
    narration: str | None = None
    redacted: bool = False


class CommitData(BaseModel):
    """Raw output from the collect stage."""

    sha: str
    parent_sha: str
    author_email: str
    committed_at: datetime
    message_subject: str
    message_body: str
    is_merge: bool
    files: list[FileChange]
