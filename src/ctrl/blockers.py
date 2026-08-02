from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ctrl.appserver import ControlError

BANNER_WIDTH = 40
BANNER_RULE = "█" * BANNER_WIDTH
BANNER_PREFIX = "██  "

KIND_BLOCKER = "blocker"
KIND_HOLD = "hold"
VALID_KINDS = (KIND_BLOCKER, KIND_HOLD)

DEFAULT_WHO = "HUMAN"


def default_who() -> str:
    """Whose attention a blocker demands on this host."""
    return os.environ.get("CTRL_BLOCKER_WHO", DEFAULT_WHO).strip() or DEFAULT_WHO


def read_blockers(path: Path, *, required: bool = False) -> dict[str, dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if required:
            raise ControlError(f"blocker store not found: {path}") from exc
        return {}
    except json.JSONDecodeError as exc:
        raise ControlError(f"invalid blocker store {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ControlError(f"blocker store is not an object: {path}")
    return {
        str(lane): record
        for lane, record in value.items()
        if isinstance(record, dict) and record.get("what")
    }


def write_blockers(path: Path, blockers: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(blockers, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def format_since(moment: datetime) -> str:
    """Local wall time plus zone, e.g. '2026-08-02 14:51 PDT'."""
    zone = moment.strftime("%Z")
    stamp = moment.strftime("%Y-%m-%d %H:%M")
    return f"{stamp} {zone}".strip()


def raise_blocker(
    path: Path,
    lane: str,
    *,
    what: str,
    needed: str,
    kind: str = KIND_BLOCKER,
    who: str | None = None,
    now: datetime,
) -> dict[str, str]:
    if kind not in VALID_KINDS:
        choices = ", ".join(VALID_KINDS)
        raise ControlError(f"invalid kind {kind!r}; choose one of: {choices}")
    if not what.strip():
        raise ControlError("what is required")
    if not needed.strip():
        raise ControlError("needed is required")

    blockers = read_blockers(path)
    existing = blockers.get(lane)
    record = {
        "kind": kind,
        "what": what.strip(),
        "needed": needed.strip(),
        "who": (who or default_who()).strip(),
        # Re-raising an open blocker preserves how long it has stood.
        "since": existing["since"] if existing else format_since(now),
    }
    blockers[lane] = record
    write_blockers(path, blockers)
    return record


def clear_blocker(path: Path, lane: str) -> dict[str, str] | None:
    blockers = read_blockers(path)
    record = blockers.pop(lane, None)
    if record is None:
        return None
    write_blockers(path, blockers)
    return record


def _banner_line(text: str) -> str:
    return f"{BANNER_PREFIX}{text}".rstrip()


def render_banner(lane: str, record: dict[str, str]) -> str:
    if record.get("kind") == KIND_HOLD:
        headline = "RED-GATE HOLD"
    else:
        headline = f"BLOCKER — NEEDS {record.get('who', DEFAULT_WHO)}"
    lines = [
        BANNER_RULE,
        _banner_line(headline),
        _banner_line(f"lane: {lane}"),
        _banner_line(f"what: {record.get('what', '')}"),
        _banner_line(f"needed: {record.get('needed', '')}"),
        _banner_line(f"since: {record.get('since', '')}"),
        BANNER_RULE,
    ]
    return "\n".join(lines)


def render_all_clear(lane: str, record: dict[str, str], note: str | None = None) -> str:
    detail = f" — {note.strip()}" if note and note.strip() else ""
    return f"ALL-CLEAR  {lane}: {record.get('what', '')}{detail}"


def render_all(blockers: dict[str, dict[str, Any]]) -> str:
    if not blockers:
        return "no open blockers"
    return "\n".join(
        render_banner(lane, record) for lane, record in sorted(blockers.items())
    )
