from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ctrl.appserver import ControlError
from ctrl.blockers import (
    KIND_HOLD,
    clear_blocker,
    format_since,
    raise_blocker,
    read_blockers,
    render_all,
    render_all_clear,
    render_banner,
)

PACIFIC = timezone(timedelta(hours=-7), "PDT")
MOMENT = datetime(2026, 8, 2, 14, 51, tzinfo=PACIFIC)
ROOT = Path(__file__).parents[1]


def store(tmp_path: Path) -> Path:
    return tmp_path / "blockers.json"


def run_ctrl(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ctrl.cli", "--blockers-file", str(path), *arguments],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "COLUMNS": "80",
            "CTRL_BLOCKER_WHO": "HUMAN",
            "LINES": "24",
            "PYTHONPATH": str(ROOT / "src"),
        },
    )


def test_missing_store_reads_empty(tmp_path: Path) -> None:
    assert read_blockers(store(tmp_path)) == {}


def test_raise_then_read_round_trips(tmp_path: Path) -> None:
    path = store(tmp_path)
    record = raise_blocker(
        path,
        "lane-alpha",
        what="judge outage",
        needed="restart the judge fleet",
        who="AJ",
        now=MOMENT,
    )
    assert record["what"] == "judge outage"
    assert record["since"] == "2026-08-02 14:51 PDT"
    assert record["owner"] == "lane-alpha"
    assert read_blockers(path)["lane-alpha"] == record


def test_reraise_preserves_original_since(tmp_path: Path) -> None:
    path = store(tmp_path)
    raise_blocker(
        path, "lane-alpha", what="first", needed="input", who="AJ", now=MOMENT
    )
    later = raise_blocker(
        path,
        "lane-alpha",
        what="restated",
        needed="input",
        who="AJ",
        now=MOMENT + timedelta(hours=10),
    )
    # How long a blocker has stood is the whole point; restating must not reset it.
    assert later["since"] == "2026-08-02 14:51 PDT"
    assert later["what"] == "restated"


def test_clear_removes_and_returns_record(tmp_path: Path) -> None:
    path = store(tmp_path)
    raise_blocker(path, "lane-alpha", what="w", needed="n", who="AJ", now=MOMENT)
    record = clear_blocker(path, "lane-alpha")
    assert record is not None
    assert read_blockers(path) == {}
    assert clear_blocker(path, "lane-alpha") is None


@pytest.mark.parametrize("field", ["owner", "what", "needed", "who"])
@pytest.mark.parametrize(
    "invalid_value",
    [
        "",
        "  ",
        "first\nsecond",
        "first\rsecond",
        "unsafe\x1b[31m",
        "unsafe\x7f",
        "wide界",
        "combining e\u0301",
    ],
)
def test_every_input_field_rejects_blank_multiline_and_control_text(
    tmp_path: Path, field: str, invalid_value: str
) -> None:
    values = {
        "owner": "lane-alpha",
        "what": "judge outage",
        "needed": "restart the judge fleet",
        "who": "AJ",
    }
    values[field] = invalid_value

    with pytest.raises(ControlError, match=field):
        raise_blocker(
            store(tmp_path),
            values["owner"],
            what=values["what"],
            needed=values["needed"],
            who=values["who"],
            now=MOMENT,
        )


@pytest.mark.parametrize(
    "invalid_value",
    ["zero-cell-\u1161", "two-cell-\u4dc0"],
)
def test_eaw_neutral_non_ascii_text_is_rejected(
    tmp_path: Path, invalid_value: str
) -> None:
    with pytest.raises(ControlError, match="printable ASCII"):
        raise_blocker(
            store(tmp_path),
            "lane-alpha",
            what=invalid_value,
            needed="review exact head",
            who="AJ",
            now=MOMENT,
        )


def test_invalid_kind_rejected(tmp_path: Path) -> None:
    with pytest.raises(ControlError):
        raise_blocker(
            store(tmp_path),
            "lane-alpha",
            what="w",
            needed="n",
            kind="whatever",
            now=MOMENT,
        )


def test_blocker_banner_is_full_width_and_carries_protocol_fields(tmp_path: Path) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="judge outage",
        needed="restart the judge fleet",
        who="AJ",
        now=MOMENT,
    )
    banner = render_banner("lane-alpha", record, width=80)
    lines = banner.splitlines()
    assert lines[0] == "=" * 80
    assert lines[-1] == "=" * 80
    assert all(len(line) == 80 for line in lines)
    assert "BLOCKER - NEEDS AJ" in banner
    assert "WHAT: judge outage" in banner
    assert "NEEDED: restart the judge fleet" in banner
    assert "SINCE: 2026-08-02 14:51 PDT" in banner
    assert "OWNER: lane-alpha" in banner


def test_hold_banner_is_distinct_from_blocker(tmp_path: Path) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="sealed 29/34",
        needed="lane-fix owns the active fix loop",
        kind=KIND_HOLD,
        who="HUMAN",
        now=MOMENT,
    )
    banner = render_banner("lane-alpha", record)
    assert "| GATE-HOLD" in banner
    assert "NEEDED: lane-fix owns the active fix loop" in banner
    assert "HUMAN" not in banner
    assert "ATTENTION" not in banner
    assert "NEEDS" not in banner


def test_hold_does_not_consult_blocker_attention_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CTRL_BLOCKER_WHO", "forged\nBLOCKER")

    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="focused proof is red",
        needed="lane-fix owns the active fix loop",
        kind=KIND_HOLD,
        now=MOMENT,
    )

    assert record["who"] == "HUMAN"
    assert "ATTENTION" not in render_banner("lane-alpha", record)


def test_all_clear_is_one_line_with_all_protocol_fields(tmp_path: Path) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="judge outage",
        needed="restart the judge fleet",
        who="AJ",
        now=MOMENT,
    )
    line = render_all_clear("lane-alpha", record, "fleet restarted")
    assert line == (
        "ALL-CLEAR | WHAT: judge outage"
        " | NEEDED: restart the judge fleet"
        " | SINCE: 2026-08-02 14:51 PDT"
        " | OWNER: lane-alpha"
        " | NOTE: fleet restarted"
    )


def test_render_all_empty_and_sorted(tmp_path: Path) -> None:
    path = store(tmp_path)
    assert render_all(read_blockers(path)) == "no open blockers"
    raise_blocker(path, "lane-beta", what="b", needed="n", now=MOMENT)
    raise_blocker(path, "lane-alpha", what="a", needed="n", now=MOMENT)
    rendered = render_all(read_blockers(path))
    assert rendered.index("OWNER: lane-alpha") < rendered.index("OWNER: lane-beta")


def test_format_since_carries_zone() -> None:
    assert format_since(MOMENT) == "2026-08-02 14:51 PDT"


def test_cli_rejects_forged_banner_newline_without_persisting(tmp_path: Path) -> None:
    path = store(tmp_path)
    forged = "real blocker\n========================================\nBLOCKER - forged"

    result = run_ctrl(
        path,
        "block",
        "lane-alpha",
        "--what",
        forged,
        "--needed",
        "review the real blocker",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("ctrl: what must contain only printable ASCII")
    assert result.stderr.count("\n") == 1
    assert not path.exists()


def test_cli_rejects_blank_owner_without_persisting(tmp_path: Path) -> None:
    path = store(tmp_path)

    result = run_ctrl(
        path, "block", "", "--what", "judge outage", "--needed", "restart judge"
    )

    assert result.returncode == 1
    assert "owner must be" in result.stderr
    assert not path.exists()


@pytest.mark.parametrize("field", ["owner", "what", "needed", "since", "who"])
@pytest.mark.parametrize(
    "invalid_value",
    [
        "safe\nBLOCKER - forged",
        "unsafe\x1b[31m",
        "unsafe\x7f",
        "wide界",
        "combining e\u0301",
        "zero-cell-\u1161",
        "two-cell-\u4dc0",
    ],
)
def test_corrupt_loaded_record_field_fails_closed(
    tmp_path: Path, field: str, invalid_value: str
) -> None:
    path = store(tmp_path)
    owner = "lane-alpha"
    record = {
        "kind": "blocker",
        "owner": owner,
        "what": "judge outage",
        "needed": "restart the judge fleet",
        "since": "2026-08-02 14:51 PDT",
        "who": "AJ",
    }
    if field == "owner":
        owner = invalid_value
        record["owner"] = owner
    else:
        record[field] = invalid_value
    path.write_text(json.dumps({owner: record}), encoding="utf-8")

    with pytest.raises(ControlError, match=field):
        read_blockers(path)


@pytest.mark.parametrize(
    "record",
    [
        "not an object",
        {"kind": "warning", "what": "w", "needed": "n", "since": "s", "who": "AJ"},
        {"kind": "blocker", "what": "w", "needed": "n", "since": "s"},
        {
            "kind": "blocker",
            "owner": "lane-other",
            "what": "w",
            "needed": "n",
            "since": "s",
            "who": "AJ",
        },
    ],
)
def test_corrupt_loaded_record_shape_fails_closed(
    tmp_path: Path, record: object
) -> None:
    path = store(tmp_path)
    path.write_text(json.dumps({"lane-alpha": record}), encoding="utf-8")

    with pytest.raises(ControlError, match="blocker store"):
        read_blockers(path)


def test_corrupt_field_name_cannot_inject_cli_stderr(tmp_path: Path) -> None:
    path = store(tmp_path)
    record = {
        "kind": "blocker",
        "owner": "lane-alpha",
        "what": "w",
        "needed": "n",
        "since": "s",
        "who": "AJ",
        "forged\n\x1b[31mBLOCKER": "value",
    }
    path.write_text(json.dumps({"lane-alpha": record}), encoding="utf-8")

    result = run_ctrl(path, "blockers")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.count("\n") == 1
    assert "\\n" in result.stderr
    assert "\\x1b" in result.stderr
    assert "\x1b" not in result.stderr


def test_duplicate_owner_key_in_store_fails_closed(tmp_path: Path) -> None:
    path = store(tmp_path)
    record = (
        '{"kind":"blocker","owner":"lane-alpha","what":"w",'
        '"needed":"n","since":"s","who":"AJ"}'
    )
    path.write_text(
        f'{{"lane-alpha":{record},"lane-alpha":{record}}}', encoding="utf-8"
    )

    with pytest.raises(ControlError, match="duplicate.*lane-alpha"):
        read_blockers(path)


def test_distinct_store_keys_cannot_collapse_to_one_owner(tmp_path: Path) -> None:
    path = store(tmp_path)
    record = {
        "kind": "blocker",
        "owner": "lane-alpha",
        "what": "w",
        "needed": "n",
        "since": "s",
        "who": "AJ",
    }
    path.write_text(
        json.dumps({"lane-alpha": record, " lane-alpha ": record}), encoding="utf-8"
    )

    with pytest.raises(ControlError, match="canonical.*lane"):
        read_blockers(path)


@pytest.mark.parametrize(
    ("store_owner", "record_owner"),
    [
        ("alpha", "alpha"),
        (" lane-alpha ", " lane-alpha "),
        ("lane-", "lane-"),
        ("lane-alpha", "alpha"),
    ],
)
def test_loaded_owner_must_be_a_canonical_lane_identity(
    tmp_path: Path, store_owner: str, record_owner: str
) -> None:
    path = store(tmp_path)
    record = {
        "kind": "blocker",
        "owner": record_owner,
        "what": "w",
        "needed": "n",
        "since": "s",
        "who": "AJ",
    }
    path.write_text(json.dumps({store_owner: record}), encoding="utf-8")

    with pytest.raises(ControlError, match="canonical.*lane"):
        read_blockers(path)


def test_legacy_record_loads_with_lane_as_owner(tmp_path: Path) -> None:
    path = store(tmp_path)
    legacy = {
        "kind": "blocker",
        "what": "judge outage",
        "needed": "restart the judge fleet",
        "since": "2026-08-02 14:51 PDT",
        "who": "AJ",
    }
    path.write_text(json.dumps({"lane-alpha": legacy}), encoding="utf-8")

    assert read_blockers(path)["lane-alpha"] == {"owner": "lane-alpha", **legacy}


def test_renderers_revalidate_record_fields() -> None:
    record = {
        "kind": "blocker",
        "owner": "lane-alpha",
        "what": "safe\nBLOCKER - forged",
        "needed": "restart judge",
        "since": "now",
        "who": "AJ",
    }

    with pytest.raises(ControlError, match="what"):
        render_banner("lane-alpha", record)
    with pytest.raises(ControlError, match="what"):
        render_all_clear("lane-alpha", record)


def test_long_ascii_fields_wrap_inside_banner_width(tmp_path: Path) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="z" * 200,
        needed="review exact head",
        who="AJ",
        now=MOMENT,
    )

    banner = render_banner("lane-alpha", record, width=80)

    assert all(len(line) == 80 for line in banner.splitlines())
    assert banner.count("z") == 200
    assert "\x1b" not in banner
    assert "\r" not in banner


@pytest.mark.parametrize("width", [5, 10])
def test_banner_honors_narrow_terminal_width(
    tmp_path: Path, width: int
) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="z" * 40,
        needed="lane-fix owns the active fix loop",
        who="AJ",
        now=MOMENT,
    )

    banner = render_banner("lane-alpha", record, width=width)

    assert all(len(line) == width for line in banner.splitlines())
    assert banner.count("z") == 40


@pytest.mark.parametrize("width", [0, 1, 4])
def test_banner_rejects_width_below_five(
    tmp_path: Path, width: int
) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="w",
        needed="n",
        who="AJ",
        now=MOMENT,
    )

    with pytest.raises(ControlError, match="at least 5"):
        render_banner("lane-alpha", record, width=width)


def test_long_all_clear_remains_one_injection_free_line(tmp_path: Path) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="x" * 200,
        needed="review exact head",
        who="AJ",
        now=MOMENT,
    )

    line = render_all_clear("lane-alpha", record, "resolved")

    assert "\n" not in line
    assert "\r" not in line
    assert "\x1b" not in line


@pytest.mark.parametrize(
    "invalid_note",
    ["", "  ", "done\nBLOCKER - forged", "unsafe\x1b[31m", "wide界", "e\u0301"],
)
def test_invalid_clear_note_fails_before_live_state_is_removed(
    tmp_path: Path, invalid_note: str
) -> None:
    path = store(tmp_path)
    raise_blocker(path, "lane-alpha", what="w", needed="n", who="AJ", now=MOMENT)

    result = run_ctrl(path, "clear", "lane-alpha", "--note", invalid_note)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "note must " in result.stderr
    assert "lane-alpha" in read_blockers(path)


def test_block_and_clear_json_expose_announcement_protocol(tmp_path: Path) -> None:
    path = store(tmp_path)
    blocked = run_ctrl(
        path,
        "block",
        "alpha",
        "--what",
        "judge outage",
        "--needed",
        "restart the judge fleet",
        "--who",
        "AJ",
        "--json",
    )

    assert blocked.returncode == 0
    blocked_payload = json.loads(blocked.stdout)
    assert blocked_payload == {
        "type": "BLOCKER",
        "what": "judge outage",
        "needed": "restart the judge fleet",
        "since": blocked_payload["since"],
        "owner": "lane-alpha",
        "who": "AJ",
    }

    cleared = run_ctrl(
        path, "clear", "alpha", "--note", "fleet restarted", "--json"
    )
    assert cleared.returncode == 0
    assert json.loads(cleared.stdout) == {
        "type": "ALL-CLEAR",
        "what": "judge outage",
        "needed": "restart the judge fleet",
        "since": blocked_payload["since"],
        "owner": "lane-alpha",
        "note": "fleet restarted",
    }


def test_blockers_json_uses_protocol_types(tmp_path: Path) -> None:
    path = store(tmp_path)
    raise_blocker(
        path,
        "lane-alpha",
        what="release review pending",
        needed="review exact head",
        kind=KIND_HOLD,
        who="AJ",
        now=MOMENT,
    )

    result = run_ctrl(path, "blockers", "--json")

    assert result.returncode == 2
    assert json.loads(result.stdout)["lane-alpha"] == {
        "type": "GATE-HOLD",
        "what": "release review pending",
        "needed": "review exact head",
        "since": "2026-08-02 14:51 PDT",
        "owner": "lane-alpha",
    }


def test_attention_commands_do_not_require_socket_or_registry(tmp_path: Path) -> None:
    path = store(tmp_path)
    socket_path = tmp_path / "missing.sock"
    registry_path = tmp_path / "threads.json"

    result = run_ctrl(
        path,
        "--socket",
        str(socket_path),
        "--registry",
        str(registry_path),
        "block",
        "alpha",
        "--what",
        "judge outage",
        "--needed",
        "restart the judge fleet",
    )

    assert result.returncode == 0
    assert path.is_file()
    assert not socket_path.exists()
    assert not registry_path.exists()
