"""Repository-truth checks: version authority, doc links, and dead config.

These guard the Phase 0 cleanup decisions from #34 so a future change cannot
silently reintroduce a second version source, a broken doc link, or a
reference to the removed ``sources.toml``.
"""

from __future__ import annotations

import re
import tomllib
from importlib.metadata import version
from pathlib import Path

import boringhannover


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = ("README.md", "MAINTENANCE.md", "CLAUDE.md")
_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def test_version_matches_pyproject() -> None:
    """pyproject.toml is the single version authority."""
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = pyproject["project"]["version"]

    assert boringhannover.__version__ == declared
    assert boringhannover.__version__ == version("boringhannover")


def test_local_doc_links_resolve() -> None:
    """README/MAINTENANCE/CLAUDE must not link to missing local files."""
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


def test_sources_toml_is_gone_and_unreferenced() -> None:
    """The dead sources.toml stays removed; nothing may reference it."""
    assert not (REPO_ROOT / "src" / "boringhannover" / "sources.toml").exists()

    candidates = [
        *REPO_ROOT.glob("*.md"),
        *REPO_ROOT.glob("*.toml"),
        *REPO_ROOT.glob("Dockerfile*"),
        *REPO_ROOT.glob("docker-compose*.yml"),
        *REPO_ROOT.glob("src/**/*.py"),
        *REPO_ROOT.glob(".github/**/*.yml"),
        *REPO_ROOT.glob(".github/**/*.yaml"),
    ]
    references = [
        str(path)
        for path in candidates
        if path.is_file()
        and "sources.toml" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert references == []
