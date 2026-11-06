"""Discover the city's selected Hannover Christmas outings (#77)."""

from __future__ import annotations

from typing import ClassVar
from urllib.parse import unquote, urlparse

from boringhannover.sources.base import register_source
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)


_CITY_CHRISTMAS_PATH = (
    "/Kultur-Freizeit/Freizeit-Sport/Feste-Saisonales/"
    "Weihnachten-in-der-Region-Hannover/Weihnachtsmärkte-in-der-Stadt-Hannover"
)


@register_source("hannover_christmas_calendar")
class HannoverChristmasCalendarSource(HannoverFestivalCalendarSource):
    """Reuse the same official cards, pagination, detail facts and failure gate."""

    source_name: ClassVar[str] = "Hannover Christmas Calendar"
    CALENDAR_URL: ClassVar[str] = f"https://www.hannover.de{_CITY_CHRISTMAS_PATH}"

    @staticmethod
    def _is_official_url(url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in {"hannover.de", "www.hannover.de"}
            and unquote(parsed.path).startswith(f"{_CITY_CHRISTMAS_PATH}/")
        )
