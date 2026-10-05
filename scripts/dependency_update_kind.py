"""Require review for Python major, prerelease, or downgrade updates."""

import sys
import tomllib
from pathlib import Path

from packaging.version import InvalidVersion, Version


def requires_review(before: str, after: str) -> bool:
    old: dict[str, set[str]] = {}
    for package in tomllib.loads(before).get("package", []):
        if "version" in package:
            old.setdefault(package["name"], set()).add(package["version"])
    for package in tomllib.loads(after).get("package", []):
        name, version = package["name"], package.get("version")
        if name not in old or version in old[name]:
            continue
        if len(old[name]) != 1 or not isinstance(version, str):
            return True
        previous = next(iter(old[name]))
        try:
            start, end = Version(previous), Version(version)
        except InvalidVersion:
            return True
        if end.is_prerelease or end.is_devrelease:
            return True
        if end < start or end.epoch != start.epoch or end.major != start.major:
            return True
        if start.major == 0 and end.minor != start.minor:
            return True
    return False


if __name__ == "__main__":
    print(
        str(
            requires_review(
                Path(sys.argv[1]).read_text(), Path(sys.argv[2]).read_text()
            )
        ).lower()
    )
