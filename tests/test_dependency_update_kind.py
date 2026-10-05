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
    ],
)
def test_classifies_python_updates(before: str, after: str, expected: bool) -> None:
    assert requires_review(lock(before), lock(after)) is expected


def test_new_transitive_dependency_is_allowed() -> None:
    assert not requires_review("", lock("2.0.0"))


def test_multiple_versions_of_one_package_require_review() -> None:
    assert requires_review(lock("1.2.3"), lock("1.2.4") + lock("2.0.0"))
