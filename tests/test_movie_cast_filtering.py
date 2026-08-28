"""Cast metadata is untyped upstream; grouping must not trust its shape."""

from __future__ import annotations

from datetime import datetime

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.output import group_movies_by_film


def _movie(cast: object) -> Event:
    return Event(
        title="Die Odyssee",
        date=datetime(2026, 8, 28, 20, 0, tzinfo=BERLIN_TZ),
        venue="Astor Grand Cinema",
        url="https://example.invalid/die-odyssee",
        category="movie",
        metadata={"cast": cast},
    )


def test_structured_cast_entries_are_preserved() -> None:
    members = [{"name": "A. Actor", "role": "Odysseus"}, {"name": "B. Actor"}]

    grouped = group_movies_by_film([_movie(members)])

    assert grouped[0].cast == members


def test_bare_name_strings_are_dropped_rather_than_passed_through() -> None:
    """A source emitting plain names must not leak a list[str] into the export.

    GroupedMovie.cast is declared list[dict[str, str]] and is serialised into
    the published JSON, so a malformed entry would either break consumers or
    silently change the shape of the contract.
    """
    grouped = group_movies_by_film([_movie(["A. Actor", {"name": "B. Actor"}])])

    assert grouped[0].cast == [{"name": "B. Actor"}]
    assert all(isinstance(member, dict) for member in grouped[0].cast)


def test_non_list_cast_yields_an_empty_list() -> None:
    for value in ("A. Actor", None, 42, {"name": "A. Actor"}):
        grouped = group_movies_by_film([_movie(value)])
        assert grouped[0].cast == []
