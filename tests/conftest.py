from __future__ import annotations

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class LocalSite:
    """A real HTTP server on localhost, so sources exercise their actual httpx code.

    Unregistered paths answer 404.
    """

    url: str
    pages: dict[str, tuple[int, str]] = field(default_factory=dict)


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    site = LocalSite(url="")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, body = site.pages.get(self.path, (404, ""))
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
