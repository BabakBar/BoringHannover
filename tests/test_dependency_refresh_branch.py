import os
import subprocess
from pathlib import Path

import pytest


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github/workflows/dependency-refresh.yml"
)


@pytest.mark.parametrize(
    ("review", "open_pr", "changed", "expected"),
    [
        ("false", "true", False, "refresh"),
        ("true", "true", False, "keep"),
        ("true", "false", False, "refresh"),
        ("true", "true", True, "refresh"),
    ],
)
def test_refresh_preserves_only_unchanged_open_review_prs(
    tmp_path: Path, review: str, open_pr: str, changed: bool, expected: str
) -> None:
    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull},
        )

    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    (tmp_path / "uv.lock").write_text("dependency version 1\n")
    (tmp_path / "events.json").write_text("old events\n")
    git("add", ".")
    git("commit", "-m", "existing PR")
    git("update-ref", "refs/remotes/origin/automation/dependency-refresh", "HEAD")
    (tmp_path / "events.json").write_text("new events\n")
    if changed:
        (tmp_path / "uv.lock").write_text("dependency version 2\n")
    git("add", ".")
    git("commit", "-m", "refresh from updated master")
    condition = next(
        line.strip()
        for line in WORKFLOW.read_text().splitlines()
        if "if " in line and 'git diff --quiet "refs/remotes/origin/' in line
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            "branch=automation/dependency-refresh; update_files=(uv.lock); "
            + condition
            + " echo keep; else echo refresh; fi",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REQUIRES_REVIEW": review,
            "pr": "https://example.com/pr" if open_pr == "true" else "",
        },
    )
    assert result.stdout.strip() == expected
