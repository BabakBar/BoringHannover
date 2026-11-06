from __future__ import annotations

import base64
import hashlib
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx
import pytest
from bs4 import BeautifulSoup

from boringhannover.sources.festivals.hannover_christmas import (
    HannoverChristmasCalendarSource,
)


if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class LocalSite:
    """A real HTTP server on localhost, so sources exercise their actual httpx code.

    Pages match on the full path first, then on the path without its query.
    Unregistered paths answer 404. Every requested path and User-Agent is
    recorded.
    """

    url: str
    pages: dict[str, tuple[int, str]] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)
    user_agents: list[str] = field(default_factory=list)
    puts: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    put_statuses: dict[str, int] = field(default_factory=dict)


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    site = LocalSite(url="")

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            site.puts.append((self.path, payload))
            body = json.dumps({"commit": {"sha": "c" * 40}}).encode()
            self.send_response(site.put_statuses.get(self.path, 200))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            site.requests.append(self.path)
            site.user_agents.append(self.headers.get("User-Agent", ""))
            status, body = site.pages.get(
                self.path, site.pages.get(urlsplit(self.path).path, (404, ""))
            )
            payload = body.encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    site.url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()


def serve_github_publication(
    site: LocalSite,
    files: dict[str, bytes],
    *,
    revision: str = "a" * 40,
    tree_sha: str = "b" * 40,
    parents: tuple[str, ...] = (),
) -> None:
    site.pages["/repos/test/events"] = (200, json.dumps({"default_branch": "master"}))
    commit = (
        200,
        json.dumps(
            {
                "sha": revision,
                "commit": {"tree": {"sha": tree_sha}},
                "parents": [{"sha": parent} for parent in parents],
            }
        ),
    )
    site.pages["/repos/test/events/commits/master"] = commit
    site.pages[f"/repos/test/events/commits/{revision}"] = commit
    entries = []
    for path, raw in files.items():
        sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})
        site.pages[f"/repos/test/events/contents/{path}"] = (
            200,
            json.dumps(
                {
                    "type": "file",
                    "encoding": "base64",
                    "size": len(raw),
                    "sha": sha,
                    "content": base64.b64encode(raw).decode(),
                }
            ),
        )
    site.pages[f"/repos/test/events/git/trees/{tree_sha}"] = (
        200,
        json.dumps({"sha": tree_sha, "truncated": False, "tree": entries}),
    )


def serve_christmas_calendar(
    local_site: LocalSite,
) -> type[HannoverChristmasCalendarSource]:
    source = HannoverChristmasCalendarSource
    fixtures = Path(__file__).parent / "fixtures" / "hannover_christmas"
    listing = fixtures.joinpath("listing.html").read_text()
    local_site.pages["/christmas"] = (200, listing)
    local_site.pages["/api/v1/view/560429/10/10/line"] = (
        200,
        fixtures.joinpath("page2.json").read_text(),
    )
    cards = listing + "".join(
        json.loads(fixtures.joinpath("page2.json").read_text())["items"]
    )
    for link in BeautifulSoup(cards, "html.parser").select("a.content__read-more"):
        path = str(link["href"])
        # httpx sends Unicode paths percent-encoded, just as a real browser does.
        local_site.pages[httpx.URL(path).raw_path.decode()] = (
            200,
            fixtures.joinpath(f"{source._slug_from_url(path)}.html").read_text(),
        )

    class LocalChristmas(source):
        CALENDAR_URL = f"{local_site.url}/christmas"

    return LocalChristmas
