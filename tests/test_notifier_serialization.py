from __future__ import annotations

from boringhannover.notifier import save_to_file


def test_save_to_file_writes_message(tmp_path):
    save_to_file(
        message="hello",
        output_dir=tmp_path,
    )

    payload = (tmp_path / "latest_message.txt").read_text(encoding="utf-8")

    assert payload == "hello"
