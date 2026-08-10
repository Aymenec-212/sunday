"""Generate a git repo with known commits for golden tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def _commit(cwd: Path, message: str, env: dict[str, str] | None = None) -> str:
    _git(cwd, "add", "-A", env=env)
    _git(cwd, "commit", "-m", message, env=env)
    return _git(cwd, "rev-parse", "HEAD", env=env)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


COMMIT_DESCRIPTIONS: dict[str, str] = {
    "c01_scaffold": "Initial project scaffold",
    "c02_add_chunk_audio": "Add chunk_audio to core",
    "c03_add_api_route": "Add API route calling chunk_audio",
    "c04_break_signature": "Break chunk_audio signature (R001)",
    "c05_layer_violation": "Core imports from api (R003)",
    "c06_undocumented_env": "Add undocumented env var (R004)",
    "c07_unimported_dep": "Add unimported dependency (R006)",
    "c08_stale_arch_doc": "Change imports without updating ARCHITECTURE.md (R007)",
    "c09_test_gap": "Add public helper without tests (R008)",
    "c10_remove_symbol": "Remove public symbol with external refs (R002)",
    "c11_docs_only": "Update README only",
    "c12_skip_scope": "[skip scope] formatting tweak",
}


def build_repo(target: Path) -> dict[str, str]:
    """Build fixture repo; returns mapping of commit key -> sha."""
    if target.exists():
        import shutil

        shutil.rmtree(target)
    target.mkdir(parents=True)

    git_env = {
        "GIT_AUTHOR_NAME": "CommitScope Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@commitscope.test",
        "GIT_COMMITTER_NAME": "CommitScope Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@commitscope.test",
    }

    _run(["git", "init", "-b", "main"], cwd=target)
    _git(target, "config", "user.email", "fixture@commitscope.test")
    _git(target, "config", "user.name", "CommitScope Fixture")

    shas: dict[str, str] = {}
    commit_index = 0

    def do_commit(key: str) -> str:
        """Commit with a pinned date so the resulting SHA is reproducible."""
        nonlocal commit_index
        commit_index += 1
        date = f"2026-01-01T00:00:{commit_index:02d}+00:00"
        env = {**git_env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        return _commit(target, COMMIT_DESCRIPTIONS[key], env)

    # c01 — scaffold
    _write(
        target / "ARCHITECTURE.md",
        "# Architecture\n\n- api -> core\n- api -> infra\n- core -> infra\n",
    )
    _write(target / "README.md", "# Demo App\n\nSet `DATABASE_URL` in your environment.\n")
    _write(target / ".env.example", "DATABASE_URL=\n")
    _write(target / "requirements.txt", "requests>=2.31\n")
    _write(target / "src/core/__init__.py", "")
    _write(
        target / "src/core/audio.py",
        '"""Core audio utilities."""\n\n\ndef chunk_audio(path: str, sr: int = 16000) -> list[float]:\n    return []\n',
    )
    _write(target / "src/api/__init__.py", "")
    _write(target / "src/infra/__init__.py", "")
    _write(target / "tests/test_audio.py", 'from src.core.audio import chunk_audio\n\n\ndef test_chunk_audio():\n    assert chunk_audio("x.wav") == []\n')
    shas["c01_scaffold"] = do_commit("c01_scaffold")

    # c02 — extend core
    _write(
        target / "src/core/audio.py",
        '"""Core audio utilities."""\n\n\ndef chunk_audio(path: str, sr: int = 16000) -> list[float]:\n    """Split audio into chunks."""\n    return []\n\n\ndef normalize_audio(data: list[float]) -> list[float]:\n    return data\n',
    )
    shas["c02_add_chunk_audio"] = do_commit("c02_add_chunk_audio")

    # c03 — api route referencing chunk_audio (external caller for R001).
    # pipeline.py is a stable external caller of normalize_audio; it is never
    # touched again, so removing normalize_audio in c10 leaves a dangling
    # reference here — the external-reference precondition for R002.
    _write(
        target / "src/api/routes.py",
        '"""API routes."""\n\nfrom src.core.audio import chunk_audio\n\n\ndef process_upload(path: str) -> list[float]:\n    return chunk_audio(path)\n',
    )
    _write(
        target / "src/api/pipeline.py",
        '"""Audio pipeline."""\n\nfrom src.core.audio import normalize_audio\n\n\ndef run(data: list[float]) -> list[float]:\n    return normalize_audio(data)\n',
    )
    shas["c03_add_api_route"] = do_commit("c03_add_api_route")

    # c04 — R001: break signature (add required param), api still calls old signature
    _write(
        target / "src/core/audio.py",
        '"""Core audio utilities."""\n\n\ndef chunk_audio(path: str, sr: int, normalize: bool) -> list[float]:\n    """Split audio into chunks."""\n    return []\n\n\ndef normalize_audio(data: list[float]) -> list[float]:\n    return data\n',
    )
    shas["c04_break_signature"] = do_commit("c04_break_signature")

    # c05 — R003: core imports from api (forbidden edge)
    _write(
        target / "src/core/bridge.py",
        '"""Bridge module."""\n\nfrom src.api.routes import process_upload\n\n\ndef relay(path: str) -> list[float]:\n    return process_upload(path)\n',
    )
    shas["c05_layer_violation"] = do_commit("c05_layer_violation")

    # c06 — R004: undocumented env var
    _write(
        target / "src/infra/settings.py",
        '"""Infrastructure settings."""\n\nimport os\n\nAPI_KEY = os.environ["API_KEY"]\n',
    )
    shas["c06_undocumented_env"] = do_commit("c06_undocumented_env")

    # c07 — R006: add dep without import
    _write(target / "requirements.txt", "requests>=2.31\npandas>=2.0\n")
    shas["c07_unimported_dep"] = do_commit("c07_unimported_dep")

    # c08 — R007: change import edges, ARCHITECTURE.md untouched
    _write(
        target / "src/api/routes.py",
        '"""API routes."""\n\nfrom src.core.audio import chunk_audio\nfrom src.infra.settings import API_KEY\n\n\ndef process_upload(path: str) -> list[float]:\n    _ = API_KEY\n    return chunk_audio(path, 16000, False)\n',
    )
    shas["c08_stale_arch_doc"] = do_commit("c08_stale_arch_doc")

    # c09 — R008: new public symbol, no test changes
    _write(
        target / "src/core/audio.py",
        '"""Core audio utilities."""\n\n\ndef chunk_audio(path: str, sr: int, normalize: bool) -> list[float]:\n    """Split audio into chunks."""\n    return []\n\n\ndef normalize_audio(data: list[float]) -> list[float]:\n    return data\n\n\ndef resample_audio(data: list[float], target_sr: int) -> list[float]:\n    """Resample audio to target sample rate."""\n    return data\n',
    )
    shas["c09_test_gap"] = do_commit("c09_test_gap")

    # c10 — R002: remove public symbol referenced elsewhere
    _write(
        target / "src/core/audio.py",
        '"""Core audio utilities."""\n\n\ndef chunk_audio(path: str, sr: int, normalize: bool) -> list[float]:\n    """Split audio into chunks."""\n    return []\n\n\ndef resample_audio(data: list[float], target_sr: int) -> list[float]:\n    """Resample audio to target sample rate."""\n    return data\n',
    )
    shas["c10_remove_symbol"] = do_commit("c10_remove_symbol")

    # c11 — docs only (skip globs)
    _write(target / "README.md", "# Demo App\n\nSet `DATABASE_URL` in your environment.\n\n## Usage\n\nRun the API.\n")
    shas["c11_docs_only"] = do_commit("c11_docs_only")

    # c12 — skip scope marker (actual code change so commit is non-empty)
    _write(
        target / "src/core/audio.py",
        '"""Core audio utilities."""\n\n\ndef chunk_audio(path: str, sr: int, normalize: bool) -> list[float]:\n    """Split audio into chunks."""\n    return []\n\n\ndef resample_audio(data: list[float], target_sr: int) -> list[float]:\n    """Resample audio to target sample rate."""\n    return data  # no-op\n',
    )
    shas["c12_skip_scope"] = do_commit("c12_skip_scope")

    return shas


if __name__ == "__main__":
    import json
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/sample_repo")
    mapping = build_repo(out)
    print(json.dumps(mapping, indent=2))
