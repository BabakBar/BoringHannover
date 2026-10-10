"""Move shared runtime pins to their latest stable release.

Prints "true" when a change needs review (a minor or major runtime release),
"false" otherwise, for the dependency-refresh workflow.
"""

import argparse
import re
from pathlib import Path


TRIVY_SCRIPT = "scripts/trivy-scan.sh"


def runtime_update(current: str, latest: str) -> tuple[str, bool]:
    """Return the version to pin and whether the move needs review.

    Only stable x.y.z releases newer than the current pin are taken.
    """
    if not re.fullmatch(r"\d+\.\d+\.\d+", latest):
        return current, False
    old = tuple(map(int, current.split(".")))
    new = tuple(map(int, latest.split(".")))
    if new <= old:
        return current, False
    return latest, new[:2] != old[:2]


def update_trivy_pin(root: Path, version: str, digest: str) -> bool:
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("Invalid Trivy image digest")
    path = root / TRIVY_SCRIPT
    content = path.read_text()
    matches = re.findall(r"aquasec/trivy:(\d+\.\d+\.\d+)@sha256:[a-f0-9]{64}", content)
    if len(matches) != 1:
        raise ValueError(f"Expected one Trivy pin in {TRIVY_SCRIPT}")
    new_version, review = runtime_update(matches[0], version)
    if new_version != matches[0]:
        path.write_text(
            re.sub(
                r"aquasec/trivy:[\d.]+@sha256:[a-f0-9]{64}",
                f"aquasec/trivy:{version}@{digest}",
                content,
            )
        )
    return review


def update_pins(root: Path, *, bun: str, uv: str, zizmor: str) -> bool:
    ci = (root / ".github/workflows/ci.yml").read_text()
    old_bun = (root / "web/.bun-version").read_text().strip()
    uv_match = re.search(r'UV_VERSION: "([\d.]+)"', ci)
    zizmor_match = re.search(r'ZIZMOR_VERSION: "([\d.]+)"', ci)
    if uv_match is None or zizmor_match is None:
        raise ValueError("CI runtime version pins are missing")
    old_uv, old_zizmor = uv_match[1], zizmor_match[1]
    new_bun, bun_review = runtime_update(old_bun, bun)
    new_uv, uv_review = runtime_update(old_uv, uv)
    new_zizmor, zizmor_review = runtime_update(old_zizmor, zizmor)
    replacements = {
        "web/.bun-version": [(old_bun, new_bun)],
        "Dockerfile.web": [(f"oven/bun:{old_bun}", f"oven/bun:{new_bun}")],
        "docker-compose.yml": [(f"oven/bun:{old_bun}", f"oven/bun:{new_bun}")],
        "Dockerfile": [(f"astral-sh/uv:{old_uv}", f"astral-sh/uv:{new_uv}")],
        ".github/workflows/ci.yml": [
            (f'UV_VERSION: "{old_uv}"', f'UV_VERSION: "{new_uv}"'),
            (f'ZIZMOR_VERSION: "{old_zizmor}"', f'ZIZMOR_VERSION: "{new_zizmor}"'),
        ],
        ".github/workflows/dependency-refresh.yml": [
            (f'version: "{old_uv}"', f'version: "{new_uv}"'),
        ],
    }
    for name in ("security", "traffic-analytics"):
        replacements[f".github/workflows/{name}.yml"] = [
            (f'UV_VERSION: "{old_uv}"', f'UV_VERSION: "{new_uv}"'),
        ]
    updates: dict[Path, str] = {}
    for name, pairs in replacements.items():
        path = root / name
        content = path.read_text()
        for old, new in pairs:
            if content.count(old) != 1:
                raise ValueError(f"Expected exactly one {old!r} pin in {name}")
            content = content.replace(old, new)
        updates[path] = content
    for path, content in updates.items():
        path.write_text(content)
    return bun_review or uv_review or zizmor_review


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bun", required=True)
    parser.add_argument("--uv", required=True)
    parser.add_argument("--zizmor", required=True)
    parser.add_argument("--trivy-version", required=True)
    parser.add_argument("--trivy-digest", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    pins_review = update_pins(root, bun=args.bun, uv=args.uv, zizmor=args.zizmor)
    trivy_review = update_trivy_pin(root, args.trivy_version, args.trivy_digest)
    print(str(pins_review or trivy_review).lower())
