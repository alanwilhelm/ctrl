from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
README = ROOT / "README.md"


def test_public_readme_has_clear_product_and_safety_sections() -> None:
    content = README.read_text(encoding="utf-8")
    for heading in (
        "# CTRL",
        "## What CTRL is",
        "## Quick start",
        "## Commands",
        "## Safety model",
        "## Architecture",
        "## Current scope",
        "## Development",
        "## License",
    ):
        assert heading in content
    assert "persistent Codex App Server threads" in content
    assert "one controller per thread" in content
    assert "dangerFullAccess" in content


def test_readme_documents_only_current_commands() -> None:
    command_reference = ROOT / "references/command-reference.md"
    content = README.read_text(encoding="utf-8")
    for command in (
        "ctrl doctor",
        "ctrl list",
        "ctrl status",
        "ctrl read",
        "ctrl spawn",
        "ctrl send",
        "ctrl block",
        "ctrl clear",
        "ctrl blockers",
    ):
        assert command in content
    for unsupported in ("ctrl admit", "ctrl announce", "ctrl stop", "ctrl verify"):
        assert unsupported not in content
    for path in (README, command_reference):
        documentation = path.read_text(encoding="utf-8")
        assert "notify-send" not in documentation
        assert "blockers --quiet ||" not in documentation


def test_package_metadata_points_at_public_docs_and_license() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["readme"] == "README.md"
    assert project["license"] == {"file": "LICENSE"}
    assert (ROOT / "LICENSE").is_file()
