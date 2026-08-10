"""Top-level orchestration: collect → analyze → rules → (narrate) → render.

This module and ``cli`` are the only places allowed to import ``narrate``.
Everything here is defensive: a failure degrades to the last good artifact.
"""

from __future__ import annotations

import contextlib
import logging
import signal
from dataclasses import dataclass, field
from typing import Iterator

from commitscope.analyze.assemble import build_facts
from commitscope.collect.git import GitRepo
from commitscope.config import Config
from commitscope.models import CommitData, Facts, Finding
from commitscope.narrate.cache import NarrationCache
from commitscope.narrate.client import ModelCall, narrate
from commitscope.render.markdown import render_report, render_skip_report
from commitscope.rules.engine import run_rules

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    sha: str
    subject: str
    report: str
    findings: list[Finding] = field(default_factory=list)
    facts: Facts | None = None
    skipped: bool = False
    skip_reason: str | None = None


# Top-level directories that hold Python but are never the "source" for R008.
_NON_SOURCE_DIRS = {
    "tests", "test", "docs", "doc", "examples", "example",
    "scripts", "benchmarks", "bench",
}


def detect_source_roots(files: list[str], config: Config) -> list[str]:
    """Infer source roots from a repo's tree when none are configured.

    A top-level directory containing first-party Python is a source root; a
    repo with modules at the root reports ``"."`` (flat layout).
    """
    tops: set[str] = set()
    flat = False
    for path in files:
        if not path.endswith(".py") or config.is_skipped_path(path):
            continue
        parts = path.split("/")
        if len(parts) == 1:
            flat = True
            continue
        top = parts[0]
        if top in _NON_SOURCE_DIRS or top.startswith("."):
            continue
        tops.add(top)
    if tops:
        return sorted(tops)
    return ["."] if flat else []


def skip_reason(commit: CommitData, config: Config) -> str | None:
    """Cheapest-first skip checks. Returns a reason string or None."""
    if config.skip_merge_commits and commit.is_merge:
        return "merge commit"
    message = f"{commit.message_subject}\n{commit.message_body}"
    if "[skip scope]" in message:
        return "[skip scope] marker in commit message"
    if commit.files:
        non_skipped = [f for f in commit.files if not config.is_skipped_path(f.path)]
        if not non_skipped:
            return "all changed files match skip globs"
    if len(commit.files) > config.max_files_changed:
        return f"too many files changed ({len(commit.files)} > {config.max_files_changed})"
    total_lines = sum(f.lines_added + f.lines_removed for f in commit.files)
    if total_lines > config.max_lines_changed:
        return f"too many lines changed ({total_lines} > {config.max_lines_changed})"
    return None


def run_commit(
    repo: GitRepo,
    sha: str,
    config: Config,
    *,
    llm: bool = False,
    cache: NarrationCache | None = None,
    call_model: ModelCall | None = None,
) -> RunResult:
    commit = repo.get_commit_data(sha)
    reason = skip_reason(commit, config)
    if reason is not None:
        report = render_skip_report(commit.sha, commit.message_subject, reason)
        return RunResult(commit.sha, commit.message_subject, report, skipped=True, skip_reason=reason)

    # Zero-config: infer source roots from the tree when the repo declares none.
    if not config.source_roots:
        detected = detect_source_roots(repo.list_tree_files(commit.sha), config)
        config = config.model_copy(update={"source_roots": detected})

    facts = build_facts(repo, commit, config)
    findings = run_rules(facts, config)

    narrations: dict[str, str] = {}
    if llm and findings and cache is not None:
        try:
            narrations = narrate(findings, facts, cache, call_model=call_model)
        except Exception as exc:  # noqa: BLE001 - the run never fails on narration
            logger.warning("narration failed, continuing without it: %s", exc)

    report = render_report(facts, findings, narrations)
    return RunResult(commit.sha, commit.message_subject, report, findings=findings, facts=facts)


@contextlib.contextmanager
def time_limit(seconds: int) -> Iterator[None]:
    """Best-effort in-process wall-clock cap (POSIX main thread only)."""
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):  # type: ignore[no-untyped-def]
        raise TimeoutError(f"run exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
