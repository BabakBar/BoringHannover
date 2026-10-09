from __future__ import annotations

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest


if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class LocalSite:
    """A real HTTP server on localhost, so sources exercise their actual httpx code.

    Pages match on the full path first, then on the path without its query.
    Unregistered paths answer 404. Every requested path is recorded.
    """

    url: str
    pages: dict[str, tuple[int, str]] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    site = LocalSite(url="")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            site.requests.append(self.path)
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
