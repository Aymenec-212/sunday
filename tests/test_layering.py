"""Verify stages 1-3 and 5 never import narrate/."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN = "narrate"
ALLOWED_STAGES = ("collect", "analyze", "rules", "render")


def _imports_in_file(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_stages_never_import_narrate() -> None:
    root = Path(__file__).resolve().parents[1] / "commitscope"
    offenders: list[str] = []
    for stage in ALLOWED_STAGES:
        stage_dir = root / stage
        if not stage_dir.exists():
            continue
        for py_file in stage_dir.rglob("*.py"):
            if FORBIDDEN in _imports_in_file(py_file):
                offenders.append(str(py_file.relative_to(root.parent)))
    assert offenders == [], f"Forbidden narrate/ import in: {offenders}"
