"""Local links in the tracked docs must resolve."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = ("README.md", "CLAUDE.md")
_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def test_local_doc_links_resolve() -> None:
    """README/CLAUDE must not link to missing local files."""
    broken: list[str] = []
    for name in DOC_FILES:
        doc = REPO_ROOT / name
        if not doc.exists():
            continue
        for target in _LINK_RE.findall(doc.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "<")):
                continue
            resolved = (doc.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{name}: {target}")

    assert not broken, f"broken local doc links: {broken}"
