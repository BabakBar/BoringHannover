import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from update_runtime_pins import patch_update, update_pins, update_trivy_pin  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def test_updates_all_shared_runtime_pins_in_a_real_checkout(tmp_path: Path) -> None:
    paths = [
        "Dockerfile",
        "Dockerfile.web",
        "docker-compose.yml",
        "web/.bun-version",
        ".github/workflows/ci.yml",
        ".github/workflows/security.yml",
        ".github/workflows/traffic-analytics.yml",
        ".github/workflows/dependency-refresh.yml",
        "MAINTENANCE.md",
    ]
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        versions = {
            (ROOT / "web/.bun-version").read_text().strip(): "1.4.0",
            re.search(r'UV_VERSION: "([\d.]+)"', ci)[1]: "0.12.0",
            re.search(r'ZIZMOR_VERSION: "([\d.]+)"', ci)[1]: "1.30.0",
        }
        content = (ROOT / name).read_text()
        for current, baseline in versions.items():
            content = content.replace(current, baseline)
        target.write_text(content)
    update_pins(tmp_path, bun="1.4.99", uv="0.12.99", zizmor="1.30.99")
    assert (tmp_path / "web/.bun-version").read_text().strip() == "1.4.99"
    assert "oven/bun:1.4.99-alpine" in (tmp_path / "Dockerfile.web").read_text()
    assert "oven/bun:1.4.99-alpine" in (tmp_path / "docker-compose.yml").read_text()
    assert "astral-sh/uv:0.12.99" in (tmp_path / "Dockerfile").read_text()
    for name in paths[4:8]:
        assert "0.12.99" in (tmp_path / name).read_text()
    assert 'ZIZMOR_VERSION: "1.30.99"' in (tmp_path / paths[4]).read_text()


@pytest.mark.parametrize(
    ("current", "latest", "expected"),
    [
        ("1.4.0", "1.4.1", "1.4.1"),
        ("1.4.0", "2.0.0", "1.4.0"),
        ("1.4.0", "1.5.0", "1.4.0"),
        ("1.4.0", "1.4.0-beta.1", "1.4.0"),
        ("1.4.0", "invalid", "1.4.0"),
        ("1.4.2", "1.4.1", "1.4.2"),
    ],
)
def test_runtime_refresh_takes_only_stable_patch_upgrades(
    current: str, latest: str, expected: str
) -> None:
    assert patch_update(current, latest) == expected


def test_runtime_minor_release_emits_review_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert patch_update("1.4.2", "1.5.0") == "1.4.2"
    assert (
        "::warning::Runtime release requires review: 1.4.2 -> 1.5.0"
        in capsys.readouterr().out
    )


def test_updates_trivy_digest_in_all_scanning_workflows(tmp_path: Path) -> None:
    for name in ("ci", "deploy", "security"):
        path = tmp_path / f".github/workflows/{name}.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"aquasec/trivy:0.75.0@sha256:{'a' * 64}\n")
    update_trivy_pin(tmp_path, "0.75.1", "sha256:" + "b" * 64)
    for name in ("ci", "deploy", "security"):
        assert (
            "0.75.1@sha256:" + "b" * 64
            in (tmp_path / f".github/workflows/{name}.yml").read_text()
        )


def test_trivy_update_rejects_invalid_digest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="digest"):
        update_trivy_pin(tmp_path, "0.75.1", "invalid")
