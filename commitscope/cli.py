"""CommitScope CLI. Never raises: it catches, logs, degrades, and exits 0.

An analyzer crash must never block a push or turn someone's CI red on
unrelated work. ``--strict`` opts into a non-zero exit for local debugging.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from commitscope.collect.git import GitRepo
from commitscope.config import load_config
from commitscope.narrate.cache import NarrationCache
from commitscope.pipeline import RunResult, run_commit, time_limit
from commitscope.publish.github import publish_commit_comment, write_job_summary

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="commitscope", description="Analyze git commits")
    parser.add_argument("--config", type=Path, default=Path("commitscope.yaml"))
    parser.add_argument(
        "--strict", action="store_true", help="Exit non-zero on failure (default: exit 0)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Analyze a single commit")
    run.add_argument("--sha", required=True)
    run.add_argument("--repo", type=Path, default=Path("."))
    run.add_argument("--output", type=Path, default=Path(".commitscope"))
    run.add_argument("--no-llm", action="store_true", help="Disable narration")
    run.add_argument("--publish", action="store_true", help="Post/refresh the commit comment")
    run.add_argument("--max-cost-usd", type=float, default=0.05)

    replay = sub.add_parser("replay", help="Replay analysis over recent commits")
    replay.add_argument("--last", type=int, default=10)
    replay.add_argument("--repo", type=Path, default=Path("."))
    replay.add_argument("--output", type=Path, default=Path(".commitscope"))
    replay.add_argument("--no-llm", action="store_true")

    explain = sub.add_parser("explain", help="Print findings for a commit to stdout")
    explain.add_argument("--sha", required=True)
    explain.add_argument("--repo", type=Path, default=Path("."))

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
        if args.command == "run":
            return _cmd_run(args, config)
        if args.command == "replay":
            return _cmd_replay(args, config)
        if args.command == "explain":
            return _cmd_explain(args, config)
        return 0
    except Exception:  # noqa: BLE001 - top-level guard; observer, not a gate
        logger.exception("commitscope failed")
        return 1 if getattr(args, "strict", False) else 0


def _cmd_run(args: argparse.Namespace, config) -> int:
    repo = GitRepo(args.repo)
    cache = NarrationCache(args.output / "cache")
    result = _analyze(repo, args.sha, config, llm=not args.no_llm, cache=cache, strict=args.strict)

    _write_artifacts(args.output, result)
    print(result.report)

    write_job_summary(result.report)
    if args.publish:
        published = publish_commit_comment(result.report, result.sha)
        logger.info("commit comment %s", "published" if published else "not published")
    return 0


def _cmd_replay(args: argparse.Namespace, config) -> int:
    repo = GitRepo(args.repo)
    cache = NarrationCache(args.output / "cache")
    shas = repo.list_commits(last=args.last)

    print(f"# CommitScope replay — {len(shas)} commit(s)\n")
    for sha in shas:
        result = _analyze(repo, sha, config, llm=not args.no_llm, cache=cache, strict=args.strict)
        _write_artifacts(args.output, result)
        print(_replay_line(result))
    print(f"\nReports written to {args.output}/")
    return 0


def _cmd_explain(args: argparse.Namespace, config) -> int:
    repo = GitRepo(args.repo)
    result = _analyze(repo, args.sha, config, llm=False, cache=None, strict=args.strict)
    if result.skipped:
        print(f"{result.sha[:8]} skipped: {result.skip_reason}")
        return 0
    if not result.findings:
        print(f"{result.sha[:8]} — no findings")
        return 0
    print(f"{result.sha[:8]} — {len(result.findings)} finding(s)")
    for finding in result.findings:
        print(f"  [{finding.severity:>6}] {finding.rule_id} {finding.title}")
        for item in finding.evidence:
            print(f"           evidence: {item}")
    return 0


def _analyze(repo, sha, config, *, llm, cache, strict=False) -> RunResult:
    """Run one commit under the configured time budget, degrading on failure."""
    try:
        with time_limit(config.run_timeout_seconds):
            return run_commit(repo, sha, config, llm=llm, cache=cache)
    except Exception as exc:  # noqa: BLE001 - degrade to a minimal report
        if strict:
            raise
        logger.warning("analysis of %s degraded: %s", sha[:8], exc)
        from commitscope.render.markdown import render_skip_report

        report = render_skip_report(sha, "(unavailable)", f"analysis error: {exc}")
        return RunResult(sha, "(unavailable)", report, skipped=True, skip_reason=str(exc))


def _write_artifacts(output: Path, result: RunResult) -> None:
    output.mkdir(parents=True, exist_ok=True)
    short = result.sha[:8]
    (output / f"report-{short}.md").write_text(result.report, encoding="utf-8")
    if result.facts is not None:
        (output / f"facts-{short}.json").write_text(
            result.facts.model_dump_json(indent=2), encoding="utf-8"
        )
    (output / f"findings-{short}.json").write_text(
        json.dumps([f.model_dump() for f in result.findings], indent=2),
        encoding="utf-8",
    )


def _replay_line(result: RunResult) -> str:
    if result.skipped:
        return f"- `{result.sha[:8]}` {result.subject} — skipped ({result.skip_reason})"
    if not result.findings:
        return f"- `{result.sha[:8]}` {result.subject} — clean"
    tags = ", ".join(sorted({f.rule_id for f in result.findings}))
    return f"- `{result.sha[:8]}` {result.subject} — {len(result.findings)} finding(s): {tags}"


if __name__ == "__main__":
    sys.exit(main())
