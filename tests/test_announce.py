from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ctrl.announce import format_announcement, validate_announcement


ROOT = Path(__file__).parents[1]
BASE_FIELDS = {
    "what": "Deploy proof is missing",
    "needed": "Verify the immutable digest",
    "since": "2026-08-02T14:30:00-07:00",
    "owner": "release coordinator",
}


def run_ctrl(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ctrl.cli", *arguments],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "COLUMNS": "80",
            "LINES": "24",
            "PYTHONPATH": str(ROOT / "src"),
        },
    )


def announce_arguments(kind: str = "BLOCKER") -> list[str]:
    return [
        "announce",
        kind,
        "--what",
        BASE_FIELDS["what"],
        "--needed",
        BASE_FIELDS["needed"],
        "--since",
        BASE_FIELDS["since"],
        "--owner",
        BASE_FIELDS["owner"],
    ]


@pytest.mark.parametrize("kind", ["BLOCKER", "GATE-HOLD"])
def test_blocking_types_render_as_full_width_banners(kind: str) -> None:
    announcement = validate_announcement(kind, **BASE_FIELDS)

    output = format_announcement(announcement, width=80)

    lines = output.splitlines()
    assert len(lines) == 7
    assert all(len(line) == 80 for line in lines)
    assert lines[0] == "=" * 80
    assert lines[-1] == "=" * 80
    assert f"| {kind}" in lines[1]
    for label, value in BASE_FIELDS.items():
        assert f"{label.upper()}: {value}" in output


def test_all_clear_renders_one_loud_line_with_every_field() -> None:
    announcement = validate_announcement("ALL-CLEAR", **BASE_FIELDS)

    output = format_announcement(announcement, width=20)

    assert output == (
        "ALL-CLEAR | WHAT: Deploy proof is missing"
        " | NEEDED: Verify the immutable digest"
        " | SINCE: 2026-08-02T14:30:00-07:00"
        " | OWNER: release coordinator"
    )
    assert "\n" not in output


@pytest.mark.parametrize("field", ["what", "needed", "since", "owner"])
def test_cli_requires_each_announcement_field(field: str) -> None:
    arguments = announce_arguments()
    option_index = arguments.index(f"--{field}")
    del arguments[option_index : option_index + 2]

    result = run_ctrl(*arguments)

    assert result.returncode == 2
    assert f"--{field}" in result.stderr


def test_cli_rejects_invalid_announcement_type() -> None:
    result = run_ctrl(*announce_arguments("WARNING"))

    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert "WARNING" in result.stderr


def test_announce_help_exposes_exact_fields_and_json_option() -> None:
    result = run_ctrl("announce", "--help")

    assert result.returncode == 0
    for value in ("BLOCKER", "GATE-HOLD", "ALL-CLEAR"):
        assert value in result.stdout
    for option in ("--what", "--needed", "--since", "--owner", "--json"):
        assert option in result.stdout


def test_cli_rejects_unknown_announcement_field() -> None:
    result = run_ctrl(*announce_arguments(), "--details", "extra")

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


@pytest.mark.parametrize("field", ["what", "needed", "since", "owner"])
@pytest.mark.parametrize(
    "invalid_value",
    ["", "   \t", "first\nsecond", "first\rsecond", "unsafe\x1b[31m", "unsafe\x7f"],
)
def test_validator_rejects_blank_multiline_and_control_fields(
    field: str, invalid_value: str
) -> None:
    fields = {**BASE_FIELDS, field: invalid_value}

    with pytest.raises(ValueError, match=field):
        validate_announcement("BLOCKER", **fields)


def test_validator_rejects_invalid_type() -> None:
    with pytest.raises(ValueError, match="announcement type"):
        validate_announcement("WARNING", **BASE_FIELDS)


@pytest.mark.parametrize(
    "invalid_value", ["first\nsecond", "unsafe\x1b[31m", "unsafe\u2028line"]
)
def test_cli_rejects_unsafe_text_without_echoing_it(invalid_value: str) -> None:
    arguments = announce_arguments()
    arguments[arguments.index("--what") + 1] = invalid_value

    result = run_ctrl(*arguments)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("ctrl: what must be")
    assert result.stderr.count("\n") == 1


def test_cli_human_output_is_not_json_wrapped() -> None:
    result = run_ctrl(*announce_arguments("BLOCKER"))

    assert result.returncode == 0
    assert result.stderr == ""
    assert not result.stdout.startswith("{")
    assert result.stdout.splitlines()[0] == "=" * 80
    assert "| BLOCKER" in result.stdout


def test_cli_json_output_is_explicit_and_machine_readable() -> None:
    result = run_ctrl(*announce_arguments("GATE-HOLD"), "--json")

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"type": "GATE-HOLD", **BASE_FIELDS}


def test_announce_does_not_require_socket_or_touch_registry(tmp_path: Path) -> None:
    missing_socket = tmp_path / "missing.sock"
    registry = tmp_path / "threads.json"

    result = run_ctrl(
        "--socket",
        str(missing_socket),
        "--registry",
        str(registry),
        *announce_arguments("ALL-CLEAR"),
    )

    assert result.returncode == 0
    assert "ALL-CLEAR" in result.stdout
    assert not missing_socket.exists()
    assert not registry.exists()
