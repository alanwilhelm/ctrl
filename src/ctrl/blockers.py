from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Mapping

from ctrl.appserver import ControlError

BANNER_WIDTH = 80

KIND_BLOCKER = "blocker"
KIND_HOLD = "hold"
VALID_KINDS = (KIND_BLOCKER, KIND_HOLD)

DEFAULT_WHO = "HUMAN"
RECORD_FIELDS = frozenset({"kind", "owner", "what", "needed", "since", "who"})
REQUIRED_RECORD_FIELDS = RECORD_FIELDS - {"owner"}


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ControlError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def validate_single_line(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ControlError(f"{field} must be nonblank single-line text")
    if any(not 0x20 <= ord(character) <= 0x7E for character in value):
        raise ControlError(
            f"{field} must contain only printable ASCII (U+0020 through U+007E)"
        )
    return value.strip()


def _validate_owner(value: object) -> str:
    owner = validate_single_line("owner", value)
    if value != owner or not owner.startswith("lane-") or owner == "lane-":
        raise ControlError(f"owner {value!r} must be a canonical lane identity")
    return owner


def default_who() -> str:
    """Whose attention a blocker demands on this host."""
    value = os.environ.get("CTRL_BLOCKER_WHO")
    if value is None or not value.strip():
        return DEFAULT_WHO
    return validate_single_line("who", value)


def _validate_record(owner: object, value: object) -> tuple[str, dict[str, str]]:
    validated_owner = _validate_owner(owner)
    if not isinstance(value, dict):
        raise ControlError(f"record for {validated_owner!r} is not an object")

    fields = set(value)
    missing = REQUIRED_RECORD_FIELDS - fields
    unexpected = fields - RECORD_FIELDS
    if missing:
        raise ControlError(
            f"record for {validated_owner!r} is missing fields: {', '.join(sorted(missing))}"
        )
    if unexpected:
        raise ControlError(
            f"record for {validated_owner!r} has unexpected fields: "
            f"{', '.join(repr(field) for field in sorted(unexpected))}"
        )

    kind = value["kind"]
    if not isinstance(kind, str) or kind not in VALID_KINDS:
        choices = ", ".join(VALID_KINDS)
        raise ControlError(f"invalid kind {kind!r}; choose one of: {choices}")

    record_owner = _validate_owner(value.get("owner", validated_owner))
    if record_owner != validated_owner:
        raise ControlError(
            f"owner {record_owner!r} does not match store key {validated_owner!r}"
        )
    return validated_owner, {
        "kind": kind,
        "owner": record_owner,
        "what": validate_single_line("what", value["what"]),
        "needed": validate_single_line("needed", value["needed"]),
        "since": validate_single_line("since", value["since"]),
        "who": validate_single_line("who", value["who"]),
    }


def _validate_store(value: object, path: Path) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        raise ControlError(f"blocker store is not an object: {path}")
    validated: dict[str, dict[str, str]] = {}
    try:
        for owner, record in value.items():
            validated_owner, validated_record = _validate_record(owner, record)
            if validated_owner in validated:
                raise ControlError(f"duplicate owner identity {validated_owner!r}")
            validated[validated_owner] = validated_record
    except ControlError as exc:
        raise ControlError(f"invalid blocker store {path}: {exc}") from exc
    return validated


def read_blockers(path: Path, *, required: bool = False) -> dict[str, dict[str, str]]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object
        )
    except FileNotFoundError as exc:
        if required:
            raise ControlError(f"blocker store not found: {path}") from exc
        return {}
    except json.JSONDecodeError as exc:
        raise ControlError(f"invalid blocker store {path}: {exc}") from exc
    except ControlError as exc:
        raise ControlError(f"invalid blocker store {path}: {exc}") from exc
    return _validate_store(value, path)


def write_blockers(path: Path, blockers: dict[str, dict[str, str]]) -> None:
    blockers = _validate_store(blockers, path)
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
    owner = _validate_owner(lane)
    validated_what = validate_single_line("what", what)
    validated_needed = validate_single_line("needed", needed)
    if who is not None:
        attention_target = validate_single_line("who", who)
    elif kind == KIND_BLOCKER:
        attention_target = default_who()
    else:
        attention_target = DEFAULT_WHO

    blockers = read_blockers(path)
    existing = blockers.get(owner)
    record = {
        "kind": kind,
        "owner": owner,
        "what": validated_what,
        "needed": validated_needed,
        "who": attention_target,
        # Re-raising an open blocker preserves how long it has stood.
        "since": (
            existing["since"]
            if existing
            else validate_single_line("since", format_since(now))
        ),
    }
    blockers[owner] = record
    write_blockers(path, blockers)
    return record


def clear_blocker(path: Path, lane: str) -> dict[str, str] | None:
    owner = _validate_owner(lane)
    blockers = read_blockers(path)
    record = blockers.pop(owner, None)
    if record is None:
        return None
    write_blockers(path, blockers)
    return record


def announcement_payload(
    owner: str,
    record: Mapping[str, object],
    *,
    all_clear: bool = False,
    note: str | None = None,
) -> dict[str, str]:
    validated_owner, validated_record = _validate_record(owner, dict(record))
    if all_clear:
        announcement_type = "ALL-CLEAR"
    elif validated_record["kind"] == KIND_HOLD:
        announcement_type = "GATE-HOLD"
    else:
        announcement_type = "BLOCKER"
    payload = {
        "type": announcement_type,
        "what": validated_record["what"],
        "needed": validated_record["needed"],
        "since": validated_record["since"],
        "owner": validated_owner,
    }
    if announcement_type == "BLOCKER":
        payload["who"] = validated_record["who"]
    if note is not None:
        payload["note"] = validate_single_line("note", note)
    return payload


def _banner_row(text: str, width: int) -> str:
    return f"| {text:<{width - 4}} |"


def _banner_rows(text: str, width: int) -> tuple[str, ...]:
    content_width = width - 4
    return tuple(
        _banner_row(text[offset : offset + content_width], width)
        for offset in range(0, len(text), content_width)
    )


def render_banner(
    lane: str, record: Mapping[str, object], *, width: int = BANNER_WIDTH
) -> str:
    payload = announcement_payload(lane, record)
    if payload["type"] == "GATE-HOLD":
        headline = "GATE-HOLD"
    else:
        headline = f"BLOCKER - NEEDS {payload['who']}"
    fields = (
        headline,
        f"WHAT: {payload['what']}",
        f"NEEDED: {payload['needed']}",
        f"SINCE: {payload['since']}",
        f"OWNER: {payload['owner']}",
    )
    banner_width = max(width, 20)
    border = "=" * banner_width
    return "\n".join(
        (
            border,
            *(row for field in fields for row in _banner_rows(field, banner_width)),
            border,
        )
    )


def render_all_clear(
    lane: str, record: Mapping[str, object], note: str | None = None
) -> str:
    payload = announcement_payload(lane, record, all_clear=True, note=note)
    fields = (
        payload["type"],
        f"WHAT: {payload['what']}",
        f"NEEDED: {payload['needed']}",
        f"SINCE: {payload['since']}",
        f"OWNER: {payload['owner']}",
    )
    if "note" in payload:
        fields = (*fields, f"NOTE: {payload['note']}")
    return " | ".join(fields)


def render_all(
    blockers: Mapping[str, Mapping[str, object]], *, width: int = BANNER_WIDTH
) -> str:
    if not blockers:
        return "no open blockers"
    return "\n".join(
        render_banner(lane, record, width=width)
        for lane, record in sorted(blockers.items())
    )
