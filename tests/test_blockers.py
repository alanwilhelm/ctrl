from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ctrl.appserver import ControlError
from ctrl.blockers import (
    BANNER_RULE,
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


def store(tmp_path: Path) -> Path:
    return tmp_path / "blockers.json"


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


def test_blank_fields_rejected(tmp_path: Path) -> None:
    path = store(tmp_path)
    with pytest.raises(ControlError):
        raise_blocker(path, "lane-alpha", what="  ", needed="n", who="AJ", now=MOMENT)
    with pytest.raises(ControlError):
        raise_blocker(path, "lane-alpha", what="w", needed="", who="AJ", now=MOMENT)


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


def test_banner_names_the_human_and_all_fields(tmp_path: Path) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="judge outage",
        needed="restart the judge fleet",
        who="AJ",
        now=MOMENT,
    )
    banner = render_banner("lane-alpha", record)
    lines = banner.splitlines()
    assert lines[0] == BANNER_RULE
    assert lines[-1] == BANNER_RULE
    assert "BLOCKER — NEEDS AJ" in banner
    assert "what: judge outage" in banner
    assert "needed: restart the judge fleet" in banner
    assert "since: 2026-08-02 14:51 PDT" in banner
    assert "lane: lane-alpha" in banner


def test_hold_banner_is_distinct_from_blocker(tmp_path: Path) -> None:
    record = raise_blocker(
        store(tmp_path),
        "lane-alpha",
        what="sealed 29/34",
        needed="no AJ input; fixes are being driven",
        kind=KIND_HOLD,
        who="AJ",
        now=MOMENT,
    )
    banner = render_banner("lane-alpha", record)
    assert "RED-GATE HOLD" in banner
    assert "NEEDS" not in banner


def test_all_clear_line(tmp_path: Path) -> None:
    record = raise_blocker(
        store(tmp_path), "lane-alpha", what="judge outage", needed="n", now=MOMENT
    )
    line = render_all_clear("lane-alpha", record, "fleet restarted")
    assert line.startswith("ALL-CLEAR")
    assert "judge outage" in line
    assert "fleet restarted" in line
    assert "\n" not in line


def test_render_all_empty_and_sorted(tmp_path: Path) -> None:
    path = store(tmp_path)
    assert render_all(read_blockers(path)) == "no open blockers"
    raise_blocker(path, "lane-beta", what="b", needed="n", now=MOMENT)
    raise_blocker(path, "lane-alpha", what="a", needed="n", now=MOMENT)
    rendered = render_all(read_blockers(path))
    assert rendered.index("lane: lane-alpha") < rendered.index("lane: lane-beta")


def test_format_since_carries_zone() -> None:
    assert format_since(MOMENT) == "2026-08-02 14:51 PDT"
