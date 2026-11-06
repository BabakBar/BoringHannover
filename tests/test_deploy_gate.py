"""The release gate must fail before publication without complete same-SHA CI."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from conftest import LocalSite


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
CHECKS = (
    "Version pins in sync",
    "Backend (Python 3.14)",
    "Backend (Python 3.15)",
    "Frontend (Bun)",
    "Workflow audit (zizmor)",
    "Docker Build",
)


@pytest.mark.parametrize(
    "case",
    [
        "push",
        "manual",
        "pending-then-passed",
        "failed-run",
        "cancelled-run",
        "unfinished-run",
        "missing-run",
        "wrong-sha",
        "pull-request",
        "fork",
        "wrong-workflow",
        "failed-job",
        "skipped-job",
        "missing-job",
        "truncated-jobs",
        "superseded",
        "api-error",
        "malformed-json",
        "newer-failure",
    ],
)
def test_only_complete_trusted_ci_can_reach_publication(
    local_site: LocalSite, tmp_path: Path, case: str
) -> None:
    run = {
        "id": 12,
        "run_attempt": 2,
        "head_sha": SHA,
        "head_branch": "master",
        "head_repository": {"full_name": "test/events"},
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
    }
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success", "head_sha": SHA}
        for name in CHECKS
    ]
    head = SHA
    runs = [run]
    if case == "manual":
        run["event"] = "workflow_dispatch"
    elif case in ("failed-run", "cancelled-run"):
        run["conclusion"] = "failure" if case == "failed-run" else "cancelled"
    elif case == "unfinished-run":
        run.update(status="in_progress", conclusion=None)
    elif case == "missing-run":
        runs = []
    elif case == "wrong-sha":
        run["head_sha"] = "b" * 40
    elif case == "pull-request":
        run["event"] = "pull_request"
    elif case == "fork":
        run["head_repository"] = {"full_name": "other/events"}
    elif case == "wrong-workflow":
        run["path"] = ".github/workflows/other.yml"
    elif case in ("failed-job", "skipped-job"):
        jobs[-1]["conclusion"] = "failure" if case == "failed-job" else "skipped"
    elif case == "missing-job":
        jobs.pop()
    elif case == "superseded":
        head = "b" * 40
    elif case == "newer-failure":
        runs.append({**run, "id": 13, "conclusion": "failure"})

    base = "/repos/test/events"
    local_site.pages[f"{base}/git/ref/heads/master"] = (
        200,
        json.dumps({"object": {"sha": head}}),
    )
    local_site.pages[f"{base}/actions/workflows/ci.yml/runs"] = (
        503 if case == "api-error" else 200,
        "bad JSON" if case == "malformed-json" else json.dumps({"workflow_runs": runs}),
    )
    local_site.pages[f"{base}/actions/runs/12/attempts/2/jobs"] = (
        200,
        json.dumps(
            {"total_count": len(jobs) + (case == "truncated-jobs"), "jobs": jobs}
        ),
    )
    if case == "pending-then-passed":
        run.update(status="in_progress", conclusion=None)
        local_site.pages[f"{base}/actions/workflows/ci.yml/runs"] = (
            200,
            json.dumps({"workflow_runs": runs}),
        )

        def complete_ci() -> None:
            deadline = time.monotonic() + 10
            while not any("ci.yml/runs?" in path for path in local_site.requests):
                if time.monotonic() >= deadline:
                    return
                time.sleep(0.01)
            time.sleep(0.1)
            run.update(status="completed", conclusion="success")
            local_site.pages[f"{base}/actions/workflows/ci.yml/runs"] = (
                200,
                json.dumps({"workflow_runs": runs}),
            )

        threading.Thread(target=complete_ci, daemon=True).start()
    marker = tmp_path / "published"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'bash "$1" "$2" "$4" && touch "$3"',
            "gate",
            str(ROOT / "scripts/wait-for-ci.sh"),
            SHA,
            str(marker),
            "20" if case == "pending-then-passed" else "0",
        ],
        env={
            **os.environ,
            "GITHUB_API_URL": local_site.url,
            "GITHUB_REPOSITORY": "test/events",
            "GH_TOKEN": "local-test-token",
        },
        capture_output=True,
        text=True,
        timeout=25,
    )
    accepted = case in ("push", "manual", "pending-then-passed")
    assert marker.exists() is accepted, result.stdout + result.stderr
    assert (result.returncode == 0) is accepted
    if accepted:
        assert (
            f"{base}/actions/runs/12/attempts/2/jobs?per_page=100"
            in local_site.requests
        )
    if case == "pending-then-passed":
        assert sum("ci.yml/runs?" in path for path in local_site.requests) >= 2
