"""Pure git access. Zero interpretation — just facts straight from git.

Everything here reads from a specific commit/blob via ``git`` subprocesses so
the analysis is reproducible regardless of the local working-tree state.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from commitscope.models import CommitData, FileChange

# git status letters we understand. Copies (C) are folded into "A"; the
# model contract only allows A/M/D/R.
_STATUS_MAP = {"A": "A", "M": "M", "D": "D", "R": "R", "C": "A", "T": "M"}


class GitError(RuntimeError):
    """A git subprocess exited non-zero."""


class GitRepo:
    """Thin, reproducible wrapper over a git repository."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root).resolve()

    # -- low level -----------------------------------------------------------

    def _run(self, args: list[str], *, check: bool = True) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout

    # -- metadata ------------------------------------------------------------

    def rev_parse(self, ref: str) -> str:
        return self._run(["rev-parse", ref]).strip()

    def list_commits(self, ref: str = "HEAD", last: int | None = None) -> list[str]:
        """Return commit SHAs reachable from ``ref``, newest first."""
        args = ["log", "--format=%H"]
        if last is not None:
            args += ["-n", str(last)]
        args.append(ref)
        out = self._run(args)
        return [line.strip() for line in out.splitlines() if line.strip()]

    def get_commit_data(self, sha: str) -> CommitData:
        meta = self._run(
            ["show", "-s", "--format=%H%x1f%P%x1f%ae%x1f%cI%x1f%s", sha]
        ).strip("\n")
        # Only split on the first N separators; subject is last and single-line.
        parts = meta.split("\x1f")
        full_sha, parents_raw, author_email, committed_raw, subject = (
            parts + ["", "", "", "", ""]
        )[:5]
        parents = parents_raw.split() if parents_raw else []
        parent_sha = parents[0] if parents else ""
        is_merge = len(parents) > 1
        body = self._run(["show", "-s", "--format=%b", sha]).rstrip("\n")

        files = self._collect_files(full_sha, is_merge=is_merge)

        return CommitData(
            sha=full_sha,
            parent_sha=parent_sha,
            author_email=author_email,
            committed_at=_parse_iso(committed_raw),
            message_subject=subject,
            message_body=body,
            is_merge=is_merge,
            files=files,
        )

    # -- diff ----------------------------------------------------------------

    def _collect_files(self, sha: str, *, is_merge: bool) -> list[FileChange]:
        # Merge diffs are ambiguous (which parent?); the pipeline skips merges,
        # so we report no files rather than guessing.
        if is_merge:
            return []

        name_status = self._run(
            [
                "diff-tree", "--no-commit-id", "-r", "-M", "-z",
                "--name-status", "--root", sha,
            ]
        )
        numstat = self._run(
            [
                "diff-tree", "--no-commit-id", "-r", "-M", "-z",
                "--numstat", "--root", sha,
            ]
        )

        statuses = _parse_name_status(name_status)
        counts = _parse_numstat(numstat)

        changes: list[FileChange] = []
        for status, path, old_path in statuses:
            added, removed = counts.get(path, (0, 0))
            changes.append(
                FileChange(
                    path=path,
                    status=status,  # type: ignore[arg-type]
                    old_path=old_path,
                    lines_added=added,
                    lines_removed=removed,
                )
            )
        return changes

    # -- blobs ---------------------------------------------------------------

    def show_file(self, sha: str, path: str) -> str | None:
        """Return file text at ``sha``, or ``None`` if absent / undecodable."""
        result = subprocess.run(
            ["git", "show", f"{sha}:{path}"],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def list_tree_files(self, sha: str) -> list[str]:
        """All file paths present at ``sha`` (repo-relative, forward slashes)."""
        out = self._run(["ls-tree", "-r", "--name-only", "-z", sha])
        return [p for p in out.split("\x00") if p]


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.strip())


def _parse_name_status(raw: str) -> list[tuple[str, str, str | None]]:
    """Parse ``--name-status -z`` into (status, new_path, old_path) tuples."""
    tokens = [t for t in raw.split("\x00") if t != ""]
    out: list[tuple[str, str, str | None]] = []
    i = 0
    while i < len(tokens):
        raw_status = tokens[i]
        letter = raw_status[0]
        status = _STATUS_MAP.get(letter, "M")
        if letter in ("R", "C"):
            old_path = tokens[i + 1]
            new_path = tokens[i + 2]
            out.append((status, new_path, old_path))
            i += 3
        else:
            path = tokens[i + 1]
            out.append((status, path, None))
            i += 2
    return out


def _parse_numstat(raw: str) -> dict[str, tuple[int, int]]:
    """Parse ``--numstat -z`` into {new_path: (added, removed)}."""
    tokens = [t for t in raw.split("\x00") if t != ""]
    counts: dict[str, tuple[int, int]] = {}
    i = 0
    while i < len(tokens):
        head = tokens[i]
        fields = head.split("\t")
        added = _num(fields[0])
        removed = _num(fields[1])
        path_field = fields[2] if len(fields) > 2 else ""
        if path_field == "":
            # Rename: the following two tokens are old, new paths.
            new_path = tokens[i + 2]
            counts[new_path] = (added, removed)
            i += 3
        else:
            counts[path_field] = (added, removed)
            i += 1
    return counts


def _num(value: str) -> int:
    # Binary files report "-"; treat as zero line delta.
    return 0 if value == "-" else int(value)
