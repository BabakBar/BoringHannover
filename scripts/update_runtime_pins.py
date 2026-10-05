"""Keep shared runtime patch versions synchronized before dependency refresh."""

import argparse
import re
from pathlib import Path


def patch_update(current: str, latest: str) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+", latest):
        return current
    old = tuple(map(int, current.split(".")))
    new = tuple(map(int, latest.split(".")))
    if new > old and new[:2] != old[:2]:
        print(f"::warning::Runtime release requires review: {current} -> {latest}")
    return latest if new[:2] == old[:2] and new > old else current


def update_trivy_pin(root: Path, version: str, digest: str) -> None:
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("Invalid Trivy image digest")
    paths = [
        root / f".github/workflows/{name}.yml" for name in ("ci", "deploy", "security")
    ]
    updates: dict[Path, str] = {}
    old_ref: str | None = None
    for path in paths:
        content = path.read_text()
        matches = re.findall(
            r"aquasec/trivy:(\d+\.\d+\.\d+)@sha256:[a-f0-9]{64}", content
        )
        if len(matches) != 1:
            raise ValueError(f"Expected one Trivy pin in {path.name}")
        match = re.search(r"aquasec/trivy:[\d.]+@sha256:[a-f0-9]{64}", content)
        if match is None or (old_ref is not None and match[0] != old_ref):
            raise ValueError("Trivy pins disagree")
        old_ref = match[0]
        if patch_update(matches[0], version) == matches[0]:
            return
        updates[path] = content.replace(old_ref, f"aquasec/trivy:{version}@{digest}")
    for path, content in updates.items():
        path.write_text(content)


def update_pins(root: Path, *, bun: str, uv: str, zizmor: str) -> None:
    ci = (root / ".github/workflows/ci.yml").read_text()
    old_bun = (root / "web/.bun-version").read_text().strip()
    uv_match = re.search(r'UV_VERSION: "([\d.]+)"', ci)
    zizmor_match = re.search(r'ZIZMOR_VERSION: "([\d.]+)"', ci)
    if uv_match is None or zizmor_match is None:
        raise ValueError("CI runtime version pins are missing")
    old_uv, old_zizmor = uv_match[1], zizmor_match[1]
    new_bun = patch_update(old_bun, bun)
    new_uv = patch_update(old_uv, uv)
    new_zizmor = patch_update(old_zizmor, zizmor)
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
        "MAINTENANCE.md": [
            (f"| uv | {old_uv} |", f"| uv | {new_uv} |"),
            (f"| Bun | {old_bun} |", f"| Bun | {new_bun} |"),
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bun", required=True)
    parser.add_argument("--uv", required=True)
    parser.add_argument("--zizmor", required=True)
    parser.add_argument("--trivy-version", required=True)
    parser.add_argument("--trivy-digest", required=True)
    args = parser.parse_args()
    update_pins(
        Path(__file__).resolve().parents[1],
        bun=args.bun,
        uv=args.uv,
        zizmor=args.zizmor,
    )
    update_trivy_pin(
        Path(__file__).resolve().parents[1], args.trivy_version, args.trivy_digest
    )
