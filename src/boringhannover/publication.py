"""Validate published web records and preserve occasions omitted by discovery."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from collections.abc import Callable, Sequence
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn
from urllib.parse import quote, urlsplit

import httpx

from boringhannover.constants import (
    BERLIN_TZ,
    OCCASION_LOOKAHEAD_DAYS,
    OCCASION_RETENTION_DAYS,
)
from boringhannover.exporters import (
    _format_web_event,
    _occasion_programme_item,
    _write_json_atomic,
)
from boringhannover.occasions import (
    OccasionDefinition,
    _identity_key,
    collect_occasion_definitions,
    occasion_status_on,
)
from boringhannover.sanitize import sanitize_text


if TYPE_CHECKING:
    from boringhannover.models import Event


logger = logging.getLogger(__name__)
Record = dict[str, object]


class InconsistentPublication(ValueError):
    """A programme-first upload has not reached its matching manifest yet."""


# Bound decoding and the complete read, rather than trust remote Content-Length.
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_FILE_BYTES = 1024 * 1024
_MAX_PUBLICATION_BYTES = 8 * 1024 * 1024
_MAX_OCCASIONS = 100
_MANIFEST = "web/output/web_events.json"


def _invalid_number(_value: str) -> NoReturn:
    raise ValueError("Non-finite number in publication JSON")


def _unique_keys(pairs: list[tuple[str, object]]) -> Record:
    result: Record = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key in publication JSON")
        result[key] = value
    return result


def _decode(raw: bytes | bytearray) -> Record:
    return _object(
        json.loads(raw, parse_constant=_invalid_number, object_pairs_hook=_unique_keys)
    )


def _object(value: object) -> Record:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Publication requires a JSON object")
    return value


def _rows(value: object) -> list[Record]:
    if not isinstance(value, list):
        raise ValueError("Publication requires a JSON array")
    return [_object(item) for item in value]


def _text(record: Record, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Invalid publication field: {key}")
    return value


def _date(value: object) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Invalid publication date")
    return date.fromisoformat(value)


def _sha(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{40}", value):
        raise ValueError("Invalid publication Git SHA")
    return value


def _events(value: object) -> list[Record]:
    rows = _rows(value)
    for row in rows:
        for key in ("title", "date", "day", "venue"):
            _text(row, key)
        if row.get("dateISO") is not None:
            _date(row["dateISO"])
        for key in (
            "time",
            "endTime",
            "url",
            "eventType",
            "radarCategory",
            "genre",
            "programmeCategory",
            "description",
            "sourceName",
            "status",
            "imageUrl",
        ):
            if row.get(key) is not None:
                _text(row, key)
        if row.get("timeConfidence") not in (None, "confirmed", "fallback"):
            raise ValueError("Invalid programme time confidence")
    return rows


def _summary(value: object) -> Record:
    row = _object(value)
    for key in ("id", "slug", "name", "kind", "location", "description", "sourceUrl"):
        _text(row, key)
    if not row["id"] or not re.fullmatch(r"[a-z0-9-]+", _text(row, "slug")):
        raise ValueError("Invalid occasion identity")
    if row.get("programmePath") != f"occasions/{row['slug']}.json":
        raise ValueError("Occasion programme path does not match its slug")
    start, end = _date(row.get("startDate")), _date(row.get("endDate"))
    if start > end:
        raise ValueError("Occasion starts after its end")
    source = urlsplit(_text(row, "sourceUrl"))
    if (
        source.scheme != "https"
        or not source.hostname
        or source.username
        or source.password
    ):
        raise ValueError("Invalid occasion source URL")
    if row.get("status") not in ("upcoming", "happening_now", "final_weekend", "ended"):
        raise ValueError("Invalid occasion lifecycle")
    for key in ("programmeCount", "locationCount"):
        count = row.get(key)
        if type(count) is not int or count < 0:
            raise ValueError(f"Invalid occasion count: {key}")
    _events(row.get("preview"))
    confidence = row.get("scheduleConfidence")
    if "scheduleConfidence" in row and confidence not in (
        "continuous",
        "discrete",
        "unknown",
    ):
        raise ValueError("Invalid occasion schedule confidence")
    if "occurrences" in row:
        occurrences = _rows(row["occurrences"])
        if occurrences and confidence not in ("continuous", "discrete"):
            raise ValueError("Confirmed appointments require a parsed schedule")
        for occurrence in occurrences:
            if not start <= _date(occurrence.get("date")) <= end:
                raise ValueError("Occasion appointment outside its dates")
            for key in ("startTime", "endTime"):
                if key in occurrence:
                    time = _text(occurrence, key)
                    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time) and not (
                        key == "endTime" and time == "24:00"
                    ):
                        raise ValueError("Invalid appointment time")
    if "sourceStatus" in row and row["sourceStatus"] not in (
        "scheduled",
        "cancelled",
        "postponed",
        "rescheduled",
    ):
        raise ValueError("Invalid occasion source status")
    if "previousStartDate" in row:
        _date(row["previousStartDate"])
    if "hoursText" in row:
        _text(row, "hoursText")
    if "area" in row and row["area"] not in ("city", "region"):
        raise ValueError("Invalid occasion area")
    if "place" in row:
        place = _object(row["place"])
        if not _text(place, "street") or not _text(place, "locality"):
            raise ValueError("Invalid occasion address")
        if not re.fullmatch(r"\d{5}", _text(place, "postalCode")):
            raise ValueError("Invalid occasion postal code")
        for key in ("venue", "municipality"):
            if key in place:
                _text(place, key)
    if "admission" in row:
        for condition in _rows(row["admission"]):
            price = _text(condition, "price")
            if price != "free" and not re.fullmatch(r"€\d+(?:\.\d{2})?", price):
                raise ValueError("Invalid occasion admission")
            if "isFrom" in condition and (
                type(condition["isFrom"]) is not bool
                or (condition["isFrom"] and price == "free")
            ):
                raise ValueError("Invalid occasion minimum price")
            if "label" in condition:
                _text(condition, "label")
    return row


def _programmes(manifest: Record, read: Callable[[str], Record]) -> dict[str, Record]:
    summaries = _rows(manifest.get("occasions"))
    if len(summaries) > _MAX_OCCASIONS:
        raise ValueError("Published occasion inventory exceeds read budget")
    result: dict[str, Record] = {}
    slugs: set[str] = set()
    for value in summaries:
        summary = _summary(value)
        identity, slug = _text(summary, "id"), _text(summary, "slug")
        if identity in result or slug in slugs:
            raise ValueError("Duplicate published occasion identity or slug")
        slugs.add(slug)
        programme = read(_text(summary, "programmePath"))
        # A pinned commit can still be an intermediate programme-first upload.
        if programme.get("occasion") != summary:
            raise InconsistentPublication("Published manifest and programme disagree")
        _text(_object(programme.get("meta")), "updatedAt")
        items = _events(programme.get("programme"))
        if len(items) != summary["programmeCount"]:
            raise ValueError("Published programme count does not match its items")
        result[identity] = programme
    return result


def _get_json(client: httpx.Client, path: str, **params: str) -> Record:
    with client.stream("GET", path, params=params) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise ValueError("Publication HTTP response exceeds read budget")
    return _decode(body)


def read_published_occasions(client: httpx.Client, repo: str) -> dict[str, Record]:
    """Pin a coherent publication; recover interrupted uploads along the first parent."""
    prefix = f"/repos/{repo}"
    branch = _text(_get_json(client, prefix), "default_branch")
    commit = _get_json(client, f"{prefix}/commits/{quote(branch, safe='')}")
    manifest_sha: str | None = None
    blobs: dict[str, bytes] = {}
    visited: set[str] = set()
    # A run uploads at most 100 programmes. Keep recovery bounded, including
    # cached old/new blobs, and never rewind a changed manifest's source facts.
    for attempt in range(_MAX_OCCASIONS + 1):
        revision = _sha(commit.get("sha"))
        if revision in visited:
            raise ValueError("Cyclic publication recovery history")
        visited.add(revision)
        tree_sha = _sha(_object(_object(commit.get("commit")).get("tree")).get("sha"))
        tree = _get_json(client, f"{prefix}/git/trees/{tree_sha}", recursive="1")
        if tree.get("truncated") is not False or tree.get("sha") != tree_sha:
            raise ValueError("Cannot establish a complete publication tree")
        rows = _rows(tree.get("tree"))
        entries = {_text(entry, "path"): entry for entry in rows}
        if len(entries) != len(rows):
            raise ValueError("Duplicate paths in publication Git tree")
        if _MANIFEST not in entries:
            if attempt or any(
                path.startswith("web/output/occasions/") for path in entries
            ):
                raise ValueError(
                    "Missing manifest cannot establish an empty publication"
                )
            logger.info(
                "No publication manifest at accessible commit %s; bootstrap", revision
            )
            return {}
        current_manifest_sha = _sha(entries[_MANIFEST].get("sha"))
        if manifest_sha is not None and current_manifest_sha != manifest_sha:
            raise ValueError(
                "Cannot recover by rewinding a changed publication manifest"
            )
        manifest_sha = current_manifest_sha
        total = 0

        def read(
            path: str, entries: dict[str, Record] = entries, revision: str = revision
        ) -> Record:
            nonlocal total
            entry = entries.get(path)
            if (
                entry is None
                or entry.get("type") != "blob"
                or entry.get("mode") != "100644"
            ):
                raise ValueError(
                    "Publication reference is missing or is not a regular file"
                )
            sha = _sha(entry.get("sha"))
            if sha not in blobs:
                payload = _get_json(client, f"{prefix}/contents/{path}", ref=revision)
                if payload.get("type") != "file" or payload.get("encoding") != "base64":
                    raise ValueError("Invalid publication file response")
                raw = base64.b64decode(
                    "".join(_text(payload, "content").split()), validate=True
                )
                if len(raw) > _MAX_FILE_BYTES:
                    raise ValueError("Published file exceeds read budget")
                digest = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
                if (
                    payload.get("size") != len(raw)
                    or payload.get("sha") != digest
                    or sha != digest
                ):
                    raise ValueError(
                        "Publication file does not match its pinned Git blob"
                    )
                if (
                    sum(map(len, blobs.values())) + len(raw)
                    > 2 * _MAX_PUBLICATION_BYTES
                ):
                    raise ValueError("Publication recovery exceeds read budget")
                blobs[sha] = raw
            total += len(blobs[sha])
            if total > _MAX_PUBLICATION_BYTES:
                raise ValueError("Published files exceed read budget")
            return _decode(blobs[sha])

        manifest = read(_MANIFEST)
        timestamp = datetime.fromisoformat(
            _text(_object(manifest.get("meta")), "updatedAtISO")
        )
        if timestamp.tzinfo is None:
            raise ValueError("Publication timestamp requires a timezone")
        try:
            result = _programmes(manifest, lambda path: read(f"web/output/{path}"))
        except InconsistentPublication as cause:
            parents = _rows(commit.get("parents", []))
            if not parents or attempt == _MAX_OCCASIONS:
                raise ValueError(
                    "No coherent publication within recovery history"
                ) from cause
            parent = _sha(parents[0].get("sha"))
            commit = _get_json(client, f"{prefix}/commits/{parent}")
            if commit.get("sha") != parent:
                raise ValueError(
                    "Recovery commit does not match its parent reference"
                ) from cause
            continue
        if attempt:
            logger.warning(
                "Recovered coherent publication %s after %d interrupted commits",
                revision,
                attempt,
            )
        logger.info(
            "Validated prior publication %s (%d occasions)", revision, len(result)
        )
        return result
    raise ValueError("Publication recovery exhausted")


def _refresh(programme: Record, today: date, now: datetime) -> None:
    summary = _object(programme["occasion"])
    start, end = _date(summary["startDate"]), _date(summary["endDate"])
    summary["status"] = occasion_status_on(start, end, today)
    if "occurrences" in summary and today <= end:
        summary["occurrences"] = [
            item
            for item in _rows(summary["occurrences"])
            if today
            <= _date(item["date"])
            <= today + timedelta(days=OCCASION_LOOKAHEAD_DAYS)
        ]
    items = _events(programme["programme"])
    upcoming = [
        item
        for item in items
        if item.get("dateISO") is not None
        and (
            _date(item["dateISO"]) > today
            or (
                _date(item["dateISO"]) == today
                and (
                    not item.get("time") or _text(item, "time") >= now.strftime("%H:%M")
                )
            )
        )
    ]
    summary["programmeCount"] = len(items)
    summary["locationCount"] = len(
        {_text(item, "venue") for item in items if item["venue"]}
    )
    summary["preview"] = (upcoming or items)[:3]
    summary.pop("imageUrl", None)
    for item in [*items, *_events(summary["preview"])]:
        item.pop("imageUrl", None)


def _refines_unknown_schedule(previous: Record, definition: OccasionDefinition) -> bool:
    """An unchanged source schedule may acquire narrower confirmed dates."""
    if (
        previous.get("scheduleConfidence") != "unknown"
        or definition.schedule_confidence not in ("continuous", "discrete")
        or not definition.hours_text
    ):
        return False
    return (
        previous.get("hoursText")
        == sanitize_text(definition.hours_text, len(definition.hours_text))
        and _date(previous["startDate"]) <= definition.start_date
        and definition.end_date <= _date(previous["endDate"])
    )


def _retains_sparse_appointments(previous: Record, fresh: Record, today: date) -> bool:
    if (
        previous.get("scheduleConfidence") != "discrete"
        or fresh.get("scheduleConfidence") != "discrete"
    ):
        return False
    old_dates = {
        _text(item, "date")
        for item in _rows(previous.get("occurrences", []))
        if _date(item["date"]) >= today
    }
    return bool(
        old_dates
        & {_text(item, "date") for item in _rows(fresh.get("occurrences", []))}
    )


def _event_key(item: Record) -> tuple[str, ...]:
    return tuple(
        _text(item, key) if item.get(key) is not None else ""
        for key in ("title", "dateISO", "time", "venue", "url")
    )


def _partition_carried_programmes(
    manifest: Record,
    programmes: dict[str, Record],
    carried: set[str],
    events: Sequence[Event],
    now: datetime,
) -> None:
    radar = _events(manifest["concerts"])
    year = _object(manifest["meta"]).get("year")
    if type(year) is not int:
        raise ValueError("Invalid export year for programme classification")
    for event in events:
        row = _format_web_event(event, year)
        if row not in radar:
            continue
        explicit_id = event.metadata.get("occasion_id")
        explicit_id = explicit_id.strip() if isinstance(explicit_id, str) else ""
        matches = []
        for identity in carried:
            summary = _object(programmes[identity]["occasion"])
            if (
                not _date(summary["startDate"])
                <= event.date.date()
                <= _date(summary["endDate"])
            ):
                continue
            name = _identity_key(_text(summary, "name"))
            if explicit_id == identity or (
                not explicit_id
                and len(name) >= 7
                and name in _identity_key(event.title)
            ):
                matches.append(identity)
        if len(matches) != 1:
            continue
        programme = programmes[matches[0]]
        items = _events(programme["programme"])
        fresh = _occasion_programme_item(event, year)
        key = _event_key(fresh)
        prior = next((item for item in items if _event_key(item) == key), None)
        if (
            prior is not None
            and "status" not in event.metadata
            and prior.get("status")
            in (
                "cancelled",
                "canceled",
                "postponed",
                "rescheduled",
            )
        ):
            fresh["status"] = prior["status"]
        programme["programme"] = [item for item in items if _event_key(item) != key] + [
            fresh
        ]
        radar.remove(row)
    manifest["concerts"] = radar
    for identity in carried:
        programme = programmes[identity]
        items = _events(programme["programme"])
        items.sort(
            key=lambda item: (
                _text(item, "dateISO")
                if item.get("dateISO") is not None
                else "9999-12-31",
                _text(item, "time") if item.get("time") else "",
                _text(item, "title"),
            )
        )
        programme["programme"] = items
        _refresh(programme, now.date(), now)


def reconcile_occasions(
    output_dir: str | Path,
    prior: dict[str, Record],
    *,
    definitions: Sequence[OccasionDefinition],
    now: datetime,
    events: Sequence[Event] = (),
) -> int:
    """Merge validated prior web records without reconstructing lost source metadata."""
    root = Path(output_dir)
    manifest = _object(json.loads((root / "web_events.json").read_bytes()))
    current = _programmes(
        manifest, lambda path: _object(json.loads((root / path).read_bytes()))
    )
    current_definitions = collect_occasion_definitions(definitions)
    today = now.astimezone(BERLIN_TZ).date()
    carried: set[str] = set()
    for identity, old in prior.items():
        previous = _object(old["occasion"])
        for other_id, other in current.items():
            candidate = _object(other["occasion"])
            if identity != other_id and (
                candidate["slug"] == previous["slug"]
                or candidate["sourceUrl"] == previous["sourceUrl"]
            ):
                raise ValueError("Current and prior occasion identities conflict")
        if identity in current_definitions:
            definition = current_definitions[identity]
            if (
                definition.slug != previous["slug"]
                or definition.source_url != previous["sourceUrl"]
            ):
                raise ValueError(
                    "An existing occasion changed its slug or source identity"
                )
            if identity not in current:
                continue
            fresh = _object(current[identity]["occasion"])
            retained_evidence = False
            old_start, new_start = (
                _date(previous["startDate"]),
                _date(fresh["startDate"]),
            )
            if (
                new_start > old_start
                and fresh.get("sourceStatus") != "rescheduled"
                and not _refines_unknown_schedule(previous, definition)
            ):
                if (
                    new_start == today and fresh["endDate"] == previous["endDate"]
                ) or _retains_sparse_appointments(previous, fresh, today):
                    fresh["startDate"] = previous["startDate"]
                    retained_evidence = True
                elif fresh.get("sourceStatus") not in ("cancelled", "postponed"):
                    raise ValueError(
                        "Conflicting occasion start dates need explicit rescheduling evidence"
                    )
            if "sourceStatus" not in fresh and "sourceStatus" in previous:
                fresh["sourceStatus"] = previous["sourceStatus"]
                retained_evidence = True
            if (
                fresh.get("sourceStatus") == "rescheduled"
                and "previousStartDate" not in fresh
            ):
                fresh["previousStartDate"] = previous.get(
                    "previousStartDate", previous["startDate"]
                )
                retained_evidence = True
            if retained_evidence:
                current[identity]["meta"] = deepcopy(old["meta"])
            if today > _date(fresh["endDate"]) and not current[identity]["programme"]:
                # An empty fresh fetch does not erase the retained programme.
                current[identity]["programme"] = [
                    deepcopy(item)
                    for item in _events(old["programme"])
                    if item.get("dateISO") is not None
                    and _date(fresh["startDate"])
                    <= _date(item["dateISO"])
                    <= _date(fresh["endDate"])
                ]
            _refresh(current[identity], today, now.astimezone(BERLIN_TZ))
            continue
        if identity in current:
            raise ValueError("Current occasion has no matching source definition")
        start, end = _date(previous["startDate"]), _date(previous["endDate"])
        if today > end + timedelta(
            days=OCCASION_RETENTION_DAYS
        ) or start > today + timedelta(days=OCCASION_LOOKAHEAD_DAYS):
            continue
        if (
            today <= end
            and previous.get("scheduleConfidence") == "discrete"
            and not any(
                today
                <= _date(item["date"])
                <= today + timedelta(days=OCCASION_LOOKAHEAD_DAYS)
                for item in _rows(previous.get("occurrences", []))
            )
        ):
            continue
        current[identity] = deepcopy(old)
        _refresh(current[identity], today, now.astimezone(BERLIN_TZ))
        carried.add(identity)
    if len(current) > _MAX_OCCASIONS:
        raise ValueError("Reconciled occasion inventory exceeds read budget")
    _partition_carried_programmes(
        manifest, current, carried, events, now.astimezone(BERLIN_TZ)
    )
    summaries = []
    for programme in current.values():
        summary = _object(programme["occasion"])
        _summary(summary)
        summaries.append(summary)
    summaries.sort(key=lambda item: (_text(item, "startDate"), _text(item, "name")))
    # Validate the whole reconciliation before replacing any candidate file.
    manifest["occasions"] = summaries
    sizes = [
        len(json.dumps(value, indent=2, ensure_ascii=False).encode())
        for value in [manifest, *current.values()]
    ]
    if max(sizes) > _MAX_FILE_BYTES or sum(sizes) > _MAX_PUBLICATION_BYTES:
        raise ValueError("Reconciled publication exceeds read budget")
    for programme in current.values():
        path = _text(_object(programme["occasion"]), "programmePath")
        _write_json_atomic(root / path, programme)
    _write_json_atomic(root / "web_events.json", manifest)
    logger.info(
        "Carried forward %d known occasions; original fact timestamps retained",
        len(carried),
    )
    return len(carried)
