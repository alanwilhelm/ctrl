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
        "Announcement Protocol",
    ):
        assert required in content
    assert "ctrl admit" not in content
    assert "ctrl stop" not in content
    assert "ctrl verify" not in content
    assert "ctrl announce" not in content
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


def test_operating_model_canonically_defines_live_announcement_rules() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    operating_model = (
        SKILL.parent / "references/operating-model.md"
    ).read_text(encoding="utf-8")
    requirements = (
        "primary operator view",
        "end of every coordinator turn",
        "worker blockers escalate to the coordinator",
        "independently verify a blocker that names a human",
        "ALL-CLEAR` exactly once",
        "blockers.json` is current live state only",
        "plandoc owns durable blocker history",
    )
    for requirement in requirements:
        assert requirement in operating_model
        assert requirement not in skill
    assert "references/operating-model.md#announcement-protocol" in skill

    rules = operating_model.split("The operating rules are:\n\n", 1)[1].split(
        "\n\n", 1
    )[0]
    assert [line[:2] for line in rules.splitlines()] == ["1.", "2.", "3.", "4.", "5."]
    assert "blockers.json" not in rules
    assert (
        "CTRL 0.1.0 directly represents thread creation, turn delivery, and current "
        "live announcement state."
    ) in operating_model
    assert "represents only thread creation and turn delivery" not in operating_model
