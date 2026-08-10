"""Publish a report: GitHub commit comment (idempotent) and/or job summary.

All network calls degrade quietly — publishing is a courtesy, never a gate.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from commitscope.render.markdown import comment_marker

logger = logging.getLogger(__name__)


def write_job_summary(report: str) -> bool:
    """Append the report to GitHub's job summary if running in Actions."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return False
    try:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(report)
            handle.write("\n")
        return True
    except OSError as exc:  # pragma: no cover - filesystem edge
        logger.warning("could not write job summary: %s", exc)
        return False


def find_existing_comment(comments: list[dict], sha: str) -> int | None:
    """Return the id of a prior CommitScope comment for this sha, if any."""
    marker = comment_marker(sha)
    for comment in comments:
        if marker in (comment.get("body") or ""):
            return comment.get("id")
    return None


def publish_commit_comment(
    report: str,
    sha: str,
    *,
    repository: str | None = None,
    token: str | None = None,
    api_url: str | None = None,
) -> bool:
    """Create or update the commit comment carrying this sha's marker."""
    repository = repository or os.environ.get("GITHUB_REPOSITORY")
    token = token or os.environ.get("GITHUB_TOKEN")
    api_url = (api_url or os.environ.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
    if not repository or not token:
        logger.info("commit comment skipped: missing GITHUB_REPOSITORY or GITHUB_TOKEN")
        return False

    try:
        import httpx

        headers = {
            "authorization": f"Bearer {token}",
            "accept": "application/vnd.github+json",
            "x-github-api-version": "2022-11-28",
        }
        with httpx.Client(timeout=30.0, headers=headers) as client:
            listing = client.get(
                f"{api_url}/repos/{repository}/commits/{sha}/comments",
                params={"per_page": 100},
            )
            listing.raise_for_status()
            existing = find_existing_comment(listing.json(), sha)

            if existing is not None:
                resp = client.patch(
                    f"{api_url}/repos/{repository}/comments/{existing}",
                    json={"body": report},
                )
            else:
                resp = client.post(
                    f"{api_url}/repos/{repository}/commits/{sha}/comments",
                    json={"body": report},
                )
            resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - publishing must never raise
        logger.warning("commit comment failed: %s", exc)
        return False
