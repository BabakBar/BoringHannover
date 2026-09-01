"""Listmonk provider contract against a real local HTTP server."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from boringhannover.newsletter.provider import (
    ListmonkProvider,
    ProviderError,
    resolve_provider,
)
from boringhannover.newsletter.render import RenderedEdition


@dataclass
class _Request:
    method: str
    path: str
    body: dict[str, Any] | None
    authorization: str | None


@dataclass
class _ServerState:
    campaigns: list[dict[str, Any]] = field(default_factory=list)
    requests: list[_Request] = field(default_factory=list)
    subscriber_count: int = 4
    fail_status: int | None = None


@dataclass(frozen=True)
class _TestServer:
    url: str
    state: _ServerState


def _handler_for(state: _ServerState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _body(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return None
            body = json.loads(self.rfile.read(length))
            assert isinstance(body, dict)
            return body

        def _record(self, body: dict[str, Any] | None = None) -> None:
            state.requests.append(
                _Request(
                    method=self.command,
                    path=self.path,
                    body=body,
                    authorization=self.headers.get("Authorization"),
                )
            )

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _maybe_fail(self) -> bool:
            if state.fail_status is None:
                return False
            self._json(state.fail_status, {"message": "test API failure"})
            return True

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            self._record()
            if self._maybe_fail():
                return
            parsed = urlparse(self.path)
            if parsed.path == "/api/lists/7":
                self._json(
                    200,
                    {
                        "data": {
                            "id": 7,
                            "status": "active",
                            "subscriber_count": state.subscriber_count,
                        }
                    },
                )
                return
            if parsed.path != "/api/campaigns":
                self._json(404, {"message": "not found"})
                return
            query = parse_qs(parsed.query).get("query", [""])[0]
            results = [
                campaign
                for campaign in state.campaigns
                if query.lower() in str(campaign.get("name", "")).lower()
            ]
            self._json(200, {"data": {"results": results}})

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            body = self._body()
            self._record(body)
            if self._maybe_fail():
                return
            if self.path != "/api/campaigns" or body is None:
                self._json(404, {"message": "not found"})
                return
            campaign = {
                **body,
                "id": len(state.campaigns) + 41,
                "uuid": f"campaign-{len(state.campaigns) + 41}",
                "status": "draft",
            }
            state.campaigns.append(campaign)
            self._json(200, {"data": campaign})

        def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API
            body = self._body()
            self._record(body)
            if self._maybe_fail():
                return
            parsed = urlparse(self.path)
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "campaigns"]:
                self._json(404, {"message": "not found"})
                return
            campaign_id = int(parts[2])
            campaign = next(
                item for item in state.campaigns if item["id"] == campaign_id
            )
            assert body is not None
            campaign["status"] = body["status"]
            self._json(200, {"data": campaign})

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


@pytest.fixture
def listmonk_server() -> Iterator[_TestServer]:
    state = _ServerState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(state))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield _TestServer(url=f"http://{host}:{port}", state=state)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _provider(server: _TestServer) -> ListmonkProvider:
    return ListmonkProvider(
        base_url=server.url,
        api_user="newsletter-bot",
        api_token="secret-token",
        list_id=7,
        template_id=3,
        from_email="BoringHannover <newsletter@boringhannover.de>",
        max_recipients=90,
    )


def _rendered() -> RenderedEdition:
    return RenderedEdition(
        subject="Hannover this week",
        html='<p>Hello</p><a href="{{ UnsubscribeURL }}">Unsubscribe</a>',
        text="Hello\nUnsubscribe: {{ UnsubscribeURL }}",
        headers={
            "List-Unsubscribe": "<{{ UnsubscribeURL }}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "X-Edition-Key": "hannover:2026-W35:en",
            "X-Edition-Revision": "abc123",
        },
    )


def _campaign(name: str, *, status: str, campaign_id: int = 9) -> dict[str, Any]:
    return {
        "id": campaign_id,
        "uuid": f"uuid-{campaign_id}",
        "name": name,
        "subject": "Hannover this week",
        "status": status,
    }


def test_creates_and_starts_a_campaign(listmonk_server: _TestServer) -> None:
    provider = _provider(listmonk_server)

    outcome = provider.send(_rendered(), idempotency_key="edition:revision:audience")

    assert outcome.ok
    assert outcome.provider_message_id == "listmonk:campaign-41"
    assert [request.method for request in listmonk_server.state.requests] == [
        "GET",
        "POST",
        "GET",
        "PUT",
    ]

    create = listmonk_server.state.requests[1]
    assert create.body == {
        "name": "BoringHannover | edition:revision:audience",
        "subject": "Hannover this week",
        "lists": [7],
        "from_email": "BoringHannover <newsletter@boringhannover.de>",
        "type": "regular",
        "content_type": "html",
        "body": _rendered().html,
        "altbody": _rendered().text,
        "messenger": "email",
        "template_id": 3,
        "tags": ["boringhannover", "weekly-digest"],
        "headers": [
            {"X-Edition-Key": "hannover:2026-W35:en"},
            {"X-Edition-Revision": "abc123"},
        ],
        "attribs": {"idempotency_key": "edition:revision:audience"},
    }
    expected_auth = base64.b64encode(b"newsletter-bot:secret-token").decode()
    assert all(
        request.authorization == f"Basic {expected_auth}"
        for request in listmonk_server.state.requests
    )
    assert listmonk_server.state.requests[3].body == {"status": "running"}


def test_reuses_an_existing_running_campaign(listmonk_server: _TestServer) -> None:
    name = "BoringHannover | edition:revision:audience"
    listmonk_server.state.campaigns.append(_campaign(name, status="running"))

    outcome = _provider(listmonk_server).send(
        _rendered(), idempotency_key="edition:revision:audience"
    )

    assert outcome.ok
    assert outcome.provider_message_id == "listmonk:uuid-9"
    assert [request.method for request in listmonk_server.state.requests] == ["GET"]


def test_resumes_an_existing_draft_campaign(listmonk_server: _TestServer) -> None:
    name = "BoringHannover | edition:revision:audience"
    listmonk_server.state.campaigns.append(_campaign(name, status="draft"))

    outcome = _provider(listmonk_server).send(
        _rendered(), idempotency_key="edition:revision:audience"
    )

    assert outcome.ok
    assert [request.method for request in listmonk_server.state.requests] == [
        "GET",
        "GET",
        "PUT",
    ]


def test_refuses_to_start_above_the_free_tier_safety_cap(
    listmonk_server: _TestServer,
) -> None:
    listmonk_server.state.subscriber_count = 91

    outcome = _provider(listmonk_server).send(
        _rendered(), idempotency_key="edition:revision:audience"
    )

    assert not outcome.ok
    assert "91 confirmed subscribers" in (outcome.error or "")
    assert "limit is 90" in (outcome.error or "")
    assert [request.method for request in listmonk_server.state.requests] == [
        "GET",
        "POST",
        "GET",
    ]


@pytest.mark.parametrize("status", ["paused", "cancelled"])
def test_refuses_to_override_an_operator_stopped_campaign(
    listmonk_server: _TestServer, status: str
) -> None:
    name = "BoringHannover | edition:revision:audience"
    listmonk_server.state.campaigns.append(_campaign(name, status=status))

    outcome = _provider(listmonk_server).send(
        _rendered(), idempotency_key="edition:revision:audience"
    )

    assert not outcome.ok
    assert status in (outcome.error or "")
    assert [request.method for request in listmonk_server.state.requests] == ["GET"]


def test_duplicate_campaign_names_fail_closed(listmonk_server: _TestServer) -> None:
    name = "BoringHannover | edition:revision:audience"
    listmonk_server.state.campaigns.extend(
        [
            _campaign(name, status="running", campaign_id=9),
            _campaign(name, status="draft", campaign_id=10),
        ]
    )

    outcome = _provider(listmonk_server).send(
        _rendered(), idempotency_key="edition:revision:audience"
    )

    assert not outcome.ok
    assert "multiple campaigns" in (outcome.error or "")


def test_api_errors_are_returned_without_leaking_the_token(
    listmonk_server: _TestServer,
) -> None:
    listmonk_server.state.fail_status = 503

    outcome = _provider(listmonk_server).send(
        _rendered(), idempotency_key="edition:revision:audience"
    )

    assert not outcome.ok
    assert "503" in (outcome.error or "")
    assert "secret-token" not in (outcome.error or "")


def test_resolve_listmonk_requires_all_provider_settings() -> None:
    with pytest.raises(ProviderError, match="LISTMONK_API_TOKEN"):
        resolve_provider(
            "listmonk",
            ".",
            environ={
                "LISTMONK_URL": "https://newsletter.example.org",
                "LISTMONK_API_USER": "newsletter-bot",
            },
        )


def test_resolve_listmonk_builds_the_provider() -> None:
    provider = resolve_provider(
        "listmonk",
        ".",
        environ={
            "LISTMONK_URL": "https://newsletter.example.org",
            "LISTMONK_API_USER": "newsletter-bot",
            "LISTMONK_API_TOKEN": "token",
            "LISTMONK_LIST_ID": "7",
            "LISTMONK_TEMPLATE_ID": "3",
            "LISTMONK_FROM_EMAIL": "BoringHannover <newsletter@example.org>",
            "LISTMONK_MAX_RECIPIENTS": "90",
        },
    )

    assert isinstance(provider, ListmonkProvider)


def test_resolve_listmonk_rejects_a_malformed_url_as_configuration_error() -> None:
    with pytest.raises(ProviderError, match="LISTMONK_URL"):
        resolve_provider(
            "listmonk",
            ".",
            environ={
                "LISTMONK_URL": "http://[::1",
                "LISTMONK_API_USER": "newsletter-bot",
                "LISTMONK_API_TOKEN": "token",
                "LISTMONK_LIST_ID": "7",
                "LISTMONK_TEMPLATE_ID": "3",
                "LISTMONK_FROM_EMAIL": "BoringHannover <newsletter@example.org>",
                "LISTMONK_MAX_RECIPIENTS": "90",
            },
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LISTMONK_LIST_ID", "zero"),
        ("LISTMONK_TEMPLATE_ID", "0"),
        ("LISTMONK_MAX_RECIPIENTS", "-1"),
    ],
)
def test_resolve_listmonk_rejects_invalid_numeric_settings(
    name: str, value: str
) -> None:
    environ = {
        "LISTMONK_URL": "https://newsletter.example.org",
        "LISTMONK_API_USER": "newsletter-bot",
        "LISTMONK_API_TOKEN": "token",
        "LISTMONK_LIST_ID": "7",
        "LISTMONK_TEMPLATE_ID": "3",
        "LISTMONK_FROM_EMAIL": "BoringHannover <newsletter@example.org>",
        "LISTMONK_MAX_RECIPIENTS": "90",
    }
    environ[name] = value

    with pytest.raises(ProviderError, match=name):
        resolve_provider("listmonk", ".", environ=environ)
