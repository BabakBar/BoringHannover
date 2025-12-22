from __future__ import annotations

import json
from datetime import datetime

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.notifier import save_to_file


def test_save_to_file_writes_json_serializable_events(tmp_path):
    event = Event(
        title="Inception",
        date=datetime(2025, 12, 22, 19, 30, tzinfo=BERLIN_TZ),
        venue="Astor Grand Cinema",
        url="https://example.com/event/inception",
        category="movie",
        metadata={"duration": 148, "language": "OV", "tags": ["thriller"]},
    )

    save_to_file(
        message="hello",
        events_data={"movies_this_week": [event], "big_events_radar": []},
        output_dir=tmp_path,
    )

    payload = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))

    assert "movies_this_week" in payload
    assert payload["movies_this_week"][0]["title"] == "Inception"
    assert payload["movies_this_week"][0]["metadata"]["duration"] == 148
    assert payload["movies_this_week"][0]["metadata"]["language"] == "OV"
    assert payload["movies_this_week"][0]["metadata"]["tags"] == ["thriller"]
