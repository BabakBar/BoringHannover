"""Concurrent CLI runs must not scrape or overwrite another run's output."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("ending", ["success", "failure", "exception", "killed"])
def test_cli_refuses_overlap_and_releases_after_exit(
    tmp_path: Path, ending: str
) -> None:
    # A source controlled through stdin keeps the real aggregator in flight.
    # All built-in sources are disabled so no external services are contacted.
    worker = tmp_path / "worker.py"
    worker.write_text(
        """
import sys
from datetime import datetime
from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources import get_all_sources
from boringhannover.sources.base import BaseSource, register_source
from boringhannover.main import main

for source in get_all_sources().values():
    source.enabled = False

@register_source('gated')
class GatedSource(BaseSource):
    source_name = 'Gated source'
    source_type = 'concert'

    def fetch(self) -> list[Event]:
        print('FETCH_READY', flush=True)
        sys.stdin.readline()
        return [Event(
            title='Process fixture', date=datetime.now(BERLIN_TZ),
            venue='Test venue', url='https://example.com/event', category='radar',
        )]

main()
""",
        encoding="utf-8",
    )
    env = {
        "PATH": os.defpath,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        "PYTHON_DOTENV_DISABLED": "1",
    }
    command = [sys.executable, str(worker)]
    output = tmp_path / "output"
    output.mkdir()
    sentinel = output / "web_events.json"
    sentinel.write_bytes(b"existing publication")
    with (tmp_path / "owner.log").open("w+") as log:
        with subprocess.Popen(
            [*command, *([] if ending == "failure" else ["--local"])],
            cwd=tmp_path,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
        ) as owner:
            try:
                assert owner.stdout is not None
                # Logging goes to stdout too. Bound the readiness wait without
                # blocking on a pipe if the child fails before reaching fetch.
                with selectors.DefaultSelector() as selector:
                    selector.register(owner.stdout, selectors.EVENT_READ)
                    ready = False
                    received = b""
                    while selector.select(timeout=10):
                        chunk = os.read(owner.stdout.fileno(), 65536)
                        received += chunk
                        if b"FETCH_READY\n" in received:
                            ready = True
                            break
                        if not chunk:
                            break
                    assert ready, "owner did not reach source fetch"

                for args in ([], ["--local"]):
                    contender = subprocess.run(
                        [*command, *args],
                        cwd=tmp_path,
                        env=env,
                        input="",
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    assert contender.returncode == 1, (
                        contender.stdout + contender.stderr
                    )
                    assert "another run" in contender.stdout.lower()
                    assert "FETCH_READY" not in contender.stdout
                    assert sentinel.read_bytes() == b"existing publication"

                lock_inode = (output / ".run.lock").stat().st_ino
                independent = tmp_path / "independent"
                independent.mkdir()
                separate = subprocess.run(
                    [*command, "--local"],
                    cwd=independent,
                    env=env,
                    input="",
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                assert separate.returncode == 0, separate.stdout + separate.stderr

                if ending == "exception":
                    (output / "archive").write_bytes(b"not a directory")
                if ending == "killed":
                    owner.kill()
                else:
                    assert owner.stdin is not None
                    owner.stdin.write(b"continue\n")
                    owner.stdin.flush()
                owner.communicate(timeout=10)
                assert (
                    owner.returncode
                    == {"success": 0, "failure": 1, "exception": 1, "killed": -9}[
                        ending
                    ]
                )
                if ending == "exception":
                    (output / "archive").unlink()
            finally:
                if owner.poll() is None:
                    owner.kill()
                    owner.communicate(timeout=10)

        retry = subprocess.run(
            [*command, "--local"],
            cwd=tmp_path,
            env=env,
            input="",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert retry.returncode == 0, retry.stdout + retry.stderr
        assert "FETCH_READY" in retry.stdout
        assert (output / ".run.lock").stat().st_ino == lock_inode
        manifest = json.loads(sentinel.read_text())
        assert [event["title"] for event in manifest["concerts"]] == ["Process fixture"]


def test_cli_fails_before_scraping_when_lock_cannot_be_opened(tmp_path: Path) -> None:
    (tmp_path / "output/.run.lock").mkdir(parents=True)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from boringhannover.sources import get_all_sources
for source in get_all_sources().values():
    source.enabled = False
from boringhannover.main import main
main()
""",
            "--local",
        ],
        cwd=tmp_path,
        env={
            "PATH": os.defpath,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "PYTHON_DOTENV_DISABLED": "1",
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "Cannot acquire scraper run lock" in result.stdout
    assert "Fetching events" not in result.stdout
    assert not (tmp_path / "output/web_events.json").exists()
