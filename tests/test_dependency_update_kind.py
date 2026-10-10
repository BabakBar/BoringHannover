import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dependency_update_kind import requires_review  # noqa: E402


def lock(version: str) -> str:
    return f'[[package]]\nname = "example"\nversion = "{version}"\n'


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("1.2.3", "1.3.0", False),
        ("1.2.3", "2.0.0", True),
        ("0.12.1", "0.12.2", False),
        ("0.12.1", "0.13.0", True),
        ("1.2.3", "1.3.0rc1", True),
        ("1.2.3", "1.2.2", True),
        ("3.19", "3.20", False),
        ("2.9.2", "2.10", False),
        ("2026.3", "2026.5", False),
        ("2.9.0.post0", "2.9.0.post1", False),
        ("26.3", "26.4", False),
        ("1.2", "1.3.dev1", True),
        ("1.2", "invalid", True),
        ("1.2", "1!1.3", True),
    ],
)
def test_classifies_python_updates(before: str, after: str, expected: bool) -> None:
    assert requires_review(lock(before), lock(after)) is expected


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        # A new transitive dependency is routine.
        ("", lock("2.0.0"), False),
        # Two versions of one package cannot be classified safely.
        (lock("1.2.3"), lock("1.2.4") + lock("2.0.0"), True),
    ],
)
def test_classifies_lockfile_shape_changes(
    before: str, after: str, expected: bool
) -> None:
    assert requires_review(before, after) is expected
