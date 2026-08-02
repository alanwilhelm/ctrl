from __future__ import annotations

import re
from pathlib import Path

SKILL = Path(__file__).parents[1] / "SKILL.md"


def test_skill_is_detailed_and_valid() -> None:
    content = SKILL.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "\n---\n" in content[4:]
    assert re.search(r"^name: ctrl$", content, re.MULTILINE)
    description = re.search(r'^description: "([^"]+)"$', content, re.MULTILINE)
    assert description is not None
    assert description.group(1).startswith("Use when ")
    assert len(description.group(1)) <= 1024
    assert 10_000 <= len(content) <= 100_000


def test_skill_documents_the_real_surface_and_safety_contract() -> None:
    content = SKILL.read_text(encoding="utf-8")
    for command in (
        "ctrl doctor",
        "ctrl announce",
        "ctrl list",
        "ctrl status",
        "ctrl read",
        "ctrl spawn",
        "ctrl send",
    ):
        assert command in content
    for required in (
        "one controller per thread",
        "dangerFullAccess",
        "gpt-5.6-sol",
        "xhigh",
        "max",
        "~/.local/state/ctrl/threads.json",
        "Codex App Server",
        "Dragonslayer",
        "Verification Checklist",
        "Common Pitfalls",
        "Announcement Workflow",
    ):
        assert required in content
    assert "ctrl admit" not in content
    assert "ctrl stop" not in content
    assert "ctrl verify" not in content
    assert "codex-ctrl" not in content
    assert "ctrl-protocol" not in content


def test_skill_links_detailed_references() -> None:
    content = SKILL.read_text(encoding="utf-8")
    for reference in (
        "references/command-reference.md",
        "references/operating-model.md",
        "references/troubleshooting.md",
    ):
        assert reference in content
        assert (SKILL.parent / reference).is_file()


def test_operating_model_defines_announcement_contract() -> None:
    content = (SKILL.parent / "references/operating-model.md").read_text(
        encoding="utf-8"
    )
    for requirement in (
        "every coordinator turn end",
        "worker escalates its blockers to the coordinator",
        "independently verify any blocker that names a human",
        "ALL-CLEAR` exactly once",
        "CTRL owns live surfacing while plandoc owns durable records",
    ):
        assert requirement in content
