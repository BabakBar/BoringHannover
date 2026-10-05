"""Require review for Python major, prerelease, or downgrade updates."""

import re
import sys
import tomllib
from pathlib import Path


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
        if not all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in (previous, version)):
            return True
        start = tuple(map(int, previous.split(".")))
        end = tuple(map(int, version.split(".")))
        if end < start or end[0] != start[0]:
            return True
        if start[0] == 0 and end[1] != start[1]:
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
