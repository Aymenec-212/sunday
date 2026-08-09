"""CommitScope CLI entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from commitscope.config import load_config

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="commitscope", description="Analyze git commits")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("commitscope.yaml"),
        help="Path to commitscope.yaml",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on failure (default: always exit 0)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Analyze a single commit")
    run.add_argument("--sha", required=True, help="Commit SHA to analyze")
    run.add_argument("--repo", type=Path, default=Path("."), help="Repository path")
    run.add_argument("--output", type=Path, default=Path(".commitscope"), help="Output directory")

    replay = sub.add_parser("replay", help="Replay analysis over recent commits")
    replay.add_argument("--last", type=int, default=10, help="Number of recent commits")
    replay.add_argument("--repo", type=Path, default=Path("."), help="Repository path")
    replay.add_argument("--output", type=Path, default=Path(".commitscope"), help="Output directory")

    explain = sub.add_parser("explain", help="Explain findings for a commit")
    explain.add_argument("--sha", required=True, help="Commit SHA")
    explain.add_argument("--repo", type=Path, default=Path("."), help="Repository path")

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        logger.info("Loaded config with %d layer(s)", len(config.layers))

        if args.command == "run":
            logger.info("Run not yet implemented — sha=%s repo=%s", args.sha, args.repo)
        elif args.command == "replay":
            logger.info("Replay not yet implemented — last=%d repo=%s", args.last, args.repo)
        elif args.command == "explain":
            logger.info("Explain not yet implemented — sha=%s repo=%s", args.sha, args.repo)

        return 0
    except Exception:
        logger.exception("commitscope failed")
        return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
