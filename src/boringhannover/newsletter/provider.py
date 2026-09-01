"""Email delivery boundary: a rendered edition becomes a sent campaign.

The newsletter package works at edition/campaign level only and never stores
subscriber data. A provider receives a fully rendered edition and returns an
idempotency-safe result keyed by a provider message id.

``PreviewProvider`` writes rendered bodies for operator approval.
``ListmonkProvider`` creates and starts a campaign in the self-hosted Listmonk
service. Resend is configured as Listmonk's SMTP relay, never called from this
package, so subscriber addresses remain outside this repository and process.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import httpx

from boringhannover.newsletter.render import RenderedEdition


__all__ = [
    "EmailProvider",
    "ListmonkProvider",
    "PreviewProvider",
    "ProviderError",
    "SendOutcome",
    "resolve_provider",
]

_LISTMONK_REQUIRED_ENV: Final[tuple[str, ...]] = (
    "LISTMONK_URL",
    "LISTMONK_API_USER",
    "LISTMONK_API_TOKEN",
    "LISTMONK_LIST_ID",
    "LISTMONK_TEMPLATE_ID",
    "LISTMONK_FROM_EMAIL",
    "LISTMONK_MAX_RECIPIENTS",
)
_LISTMONK_MANAGED_UNSUBSCRIBE_HEADERS: Final[frozenset[str]] = frozenset(
    {"list-unsubscribe", "list-unsubscribe-post"}
)
_LISTMONK_ACCEPTED_STATUSES: Final[frozenset[str]] = frozenset(
    {"running", "scheduled", "finished"}
)


@dataclass(frozen=True, slots=True)
class SendOutcome:
    """What the provider reported for one delivery attempt."""

    provider_message_id: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when the provider accepted the send without reporting an error."""
        return self.error is None


class ProviderError(RuntimeError):
    """A provider could not deliver; the attempt must be marked failed."""


class EmailProvider(Protocol):
    """Turns a rendered edition into a delivered campaign."""

    name: str

    def send(self, edition: RenderedEdition, *, idempotency_key: str) -> SendOutcome:
        """Deliver one edition idempotently.

        Reusing ``idempotency_key`` must resume or return the original campaign,
        never create a second delivery. This covers a crash after provider
        acceptance but before the local ledger records completion.
        """


class PreviewProvider:
    """Writes the rendered edition to disk instead of delivering it."""

    name = "preview"

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def send(self, edition: RenderedEdition, *, idempotency_key: str) -> SendOutcome:
        """Write the four render outputs so a human can approve the edition."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            (self.output_dir / "subject.txt").write_text(
                f"{edition.subject}\n", encoding="utf-8"
            )
            (self.output_dir / "body.html").write_text(edition.html, encoding="utf-8")
            (self.output_dir / "body.txt").write_text(edition.text, encoding="utf-8")
            (self.output_dir / "headers.json").write_text(
                json.dumps(edition.headers, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            return SendOutcome(error=f"cannot write preview: {exc}")
        return SendOutcome(provider_message_id=f"preview:{idempotency_key}")


class ListmonkProvider:
    """Create and start one idempotent Listmonk campaign.

    Listmonk has no documented request-level idempotency key for campaigns. A
    deterministic campaign name is therefore reconciled before every create.
    If Listmonk accepted a create/start request but the response was lost, the
    next attempt finds and resumes that same campaign instead of creating a
    second send.
    """

    name = "listmonk"

    def __init__(
        self,
        *,
        base_url: str,
        api_user: str,
        api_token: str,
        list_id: int,
        template_id: int,
        from_email: str,
        max_recipients: int,
        timeout_seconds: float = 15.0,
    ) -> None:
        try:
            url = httpx.URL(base_url)
        except httpx.InvalidURL as exc:
            msg = "LISTMONK_URL must be an absolute http(s) URL"
            raise ProviderError(msg) from exc
        if url.scheme not in {"http", "https"} or not url.host:
            msg = "LISTMONK_URL must be an absolute http(s) URL"
            raise ProviderError(msg)
        if url.username or url.password:
            msg = "LISTMONK_URL must not contain credentials"
            raise ProviderError(msg)
        if list_id < 1:
            msg = "LISTMONK_LIST_ID must be a positive integer"
            raise ProviderError(msg)
        if template_id < 1:
            msg = "LISTMONK_TEMPLATE_ID must be a positive integer"
            raise ProviderError(msg)
        if max_recipients < 1:
            msg = "LISTMONK_MAX_RECIPIENTS must be a positive integer"
            raise ProviderError(msg)

        self.base_url = base_url.rstrip("/") + "/"
        self.api_user = api_user
        self._api_token = api_token
        self.list_id = list_id
        self.template_id = template_id
        self.from_email = from_email
        self.max_recipients = max_recipients
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ListmonkProvider:
        """Build the provider from secret-bearing runtime environment values."""
        env = os.environ if environ is None else environ
        missing = [name for name in _LISTMONK_REQUIRED_ENV if not env.get(name)]
        if missing:
            msg = "Listmonk provider requires: " + ", ".join(missing)
            raise ProviderError(msg)

        list_id = _positive_int(env["LISTMONK_LIST_ID"], "LISTMONK_LIST_ID")
        template_id = _positive_int(env["LISTMONK_TEMPLATE_ID"], "LISTMONK_TEMPLATE_ID")
        max_recipients = _positive_int(
            env["LISTMONK_MAX_RECIPIENTS"], "LISTMONK_MAX_RECIPIENTS"
        )
        return cls(
            base_url=env["LISTMONK_URL"],
            api_user=env["LISTMONK_API_USER"],
            api_token=env["LISTMONK_API_TOKEN"],
            list_id=list_id,
            template_id=template_id,
            from_email=env["LISTMONK_FROM_EMAIL"],
            max_recipients=max_recipients,
        )

    def send(self, edition: RenderedEdition, *, idempotency_key: str) -> SendOutcome:
        """Create or reconcile the campaign, then start it exactly once."""
        campaign_name = f"BoringHannover | {idempotency_key}"
        try:
            with httpx.Client(
                base_url=self.base_url,
                auth=(self.api_user, self._api_token),
                timeout=self.timeout_seconds,
            ) as client:
                campaign = self._find_campaign(client, campaign_name)
                if campaign is None:
                    campaign = self._create_campaign(
                        client,
                        campaign_name=campaign_name,
                        edition=edition,
                        idempotency_key=idempotency_key,
                    )
                elif campaign.get("subject") != edition.subject:
                    msg = (
                        "Listmonk campaign identity collision: existing campaign "
                        "has a different subject"
                    )
                    raise ProviderError(msg)

                campaign = self._ensure_started(client, campaign)
                return SendOutcome(provider_message_id=_campaign_message_id(campaign))
        except ProviderError as exc:
            return SendOutcome(error=str(exc))
        except httpx.HTTPError as exc:
            return SendOutcome(error=f"Listmonk request failed: {exc}")

    def _find_campaign(
        self, client: httpx.Client, campaign_name: str
    ) -> Mapping[str, Any] | None:
        data = _request_data(
            client,
            "GET",
            "api/campaigns",
            params={
                "query": campaign_name,
                "per_page": "all",
                "no_body": "true",
            },
        )
        if not isinstance(data, Mapping) or not isinstance(data.get("results"), list):
            msg = "Listmonk campaign search returned an invalid data shape"
            raise ProviderError(msg)
        matches = [
            item
            for item in data["results"]
            if isinstance(item, Mapping) and item.get("name") == campaign_name
        ]
        if len(matches) > 1:
            msg = f"Listmonk returned multiple campaigns named {campaign_name!r}"
            raise ProviderError(msg)
        return matches[0] if matches else None

    def _create_campaign(
        self,
        client: httpx.Client,
        *,
        campaign_name: str,
        edition: RenderedEdition,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        headers = [
            {name: value}
            for name, value in edition.headers.items()
            if name.lower() not in _LISTMONK_MANAGED_UNSUBSCRIBE_HEADERS
        ]
        data = _request_data(
            client,
            "POST",
            "api/campaigns",
            json={
                "name": campaign_name,
                "subject": edition.subject,
                "lists": [self.list_id],
                "from_email": self.from_email,
                "type": "regular",
                "content_type": "html",
                "body": edition.html,
                "altbody": edition.text,
                "messenger": "email",
                "template_id": self.template_id,
                "tags": ["boringhannover", "weekly-digest"],
                "headers": headers,
                "attribs": {"idempotency_key": idempotency_key},
            },
        )
        if not isinstance(data, Mapping):
            msg = "Listmonk campaign create returned an invalid data shape"
            raise ProviderError(msg)
        _campaign_id(data)
        return data

    def _ensure_started(
        self, client: httpx.Client, campaign: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        status = campaign.get("status")
        if status in _LISTMONK_ACCEPTED_STATUSES:
            return campaign
        if status != "draft":
            msg = (
                f"Listmonk campaign is {status!r}; refusing to override an "
                "operator-stopped or unknown state"
            )
            raise ProviderError(msg)

        self._ensure_recipient_limit(client)
        campaign_id = _campaign_id(campaign)
        data = _request_data(
            client,
            "PUT",
            f"api/campaigns/{campaign_id}/status",
            json={"status": "running"},
        )
        if not isinstance(data, Mapping):
            msg = "Listmonk campaign start returned an invalid data shape"
            raise ProviderError(msg)
        if data.get("status") not in _LISTMONK_ACCEPTED_STATUSES:
            msg = f"Listmonk did not start campaign {campaign_id}"
            raise ProviderError(msg)
        return data

    def _ensure_recipient_limit(self, client: httpx.Client) -> None:
        data = _request_data(client, "GET", f"api/lists/{self.list_id}")
        if not isinstance(data, Mapping):
            msg = "Listmonk list lookup returned an invalid data shape"
            raise ProviderError(msg)
        if data.get("status") != "active":
            msg = f"Listmonk list {self.list_id} is not active"
            raise ProviderError(msg)
        count = data.get("subscriber_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            msg = "Listmonk list lookup returned no valid subscriber count"
            raise ProviderError(msg)
        if count > self.max_recipients:
            msg = (
                f"Listmonk list has {count} confirmed subscribers; configured "
                f"delivery limit is {self.max_recipients}"
            )
            raise ProviderError(msg)


def _positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        msg = f"{name} must be a positive integer"
        raise ProviderError(msg) from exc
    if value < 1:
        msg = f"{name} must be a positive integer"
        raise ProviderError(msg)
    return value


def _campaign_id(campaign: Mapping[str, Any]) -> int:
    value = campaign.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        msg = "Listmonk campaign response has no valid numeric id"
        raise ProviderError(msg)
    return value


def _campaign_message_id(campaign: Mapping[str, Any]) -> str:
    uuid = campaign.get("uuid")
    if isinstance(uuid, str) and uuid:
        return f"listmonk:{uuid}"
    return f"listmonk:{_campaign_id(campaign)}"


def _request_data(
    client: httpx.Client,
    method: str,
    path: str,
    **kwargs: Any,
) -> Any:
    response = client.request(method, path, **kwargs)
    if response.is_error:
        message = _response_error(response)
        msg = (
            f"Listmonk API {method} /{path} returned {response.status_code}: {message}"
        )
        raise ProviderError(msg)
    try:
        payload = response.json()
    except ValueError as exc:
        msg = f"Listmonk API {method} /{path} returned invalid JSON"
        raise ProviderError(msg) from exc
    if not isinstance(payload, Mapping) or "data" not in payload:
        msg = f"Listmonk API {method} /{path} returned an invalid response"
        raise ProviderError(msg)
    return payload["data"]


def _response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.reason_phrase
    if isinstance(payload, Mapping) and isinstance(payload.get("message"), str):
        return payload["message"][:300]
    return response.reason_phrase


def resolve_provider(
    name: str,
    preview_dir: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> EmailProvider:
    """Return the provider for ``name``.

    Unknown names and incomplete Listmonk settings fail closed rather than
    silently not sending.
    """
    if name == "preview":
        return PreviewProvider(preview_dir)
    if name == "listmonk":
        return ListmonkProvider.from_env(environ)
    raise ProviderError(
        f"unknown newsletter provider {name!r}; choose 'preview' or 'listmonk'"
    )
