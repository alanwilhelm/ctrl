from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal, cast

AnnouncementType = Literal["BLOCKER", "GATE-HOLD", "ALL-CLEAR"]
VALID_ANNOUNCEMENT_TYPES: tuple[AnnouncementType, ...] = (
    "BLOCKER",
    "GATE-HOLD",
    "ALL-CLEAR",
)


@dataclass(frozen=True)
class Announcement:
    kind: AnnouncementType
    what: str
    needed: str
    since: str
    owner: str

    def as_dict(self) -> dict[str, str]:
        return {
            "type": self.kind,
            "what": self.what,
            "needed": self.needed,
            "since": self.since,
            "owner": self.owner,
        }


def _validate_field(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank single-line text")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in value
    ):
        raise ValueError(
            f"{name} must be nonblank single-line text without control characters"
        )
    return value


def validate_announcement(
    kind: str,
    *,
    what: str,
    needed: str,
    since: str,
    owner: str,
) -> Announcement:
    if kind not in VALID_ANNOUNCEMENT_TYPES:
        choices = ", ".join(VALID_ANNOUNCEMENT_TYPES)
        raise ValueError(f"invalid announcement type {kind!r}; choose one of: {choices}")
    return Announcement(
        kind=cast(AnnouncementType, kind),
        what=_validate_field("what", what),
        needed=_validate_field("needed", needed),
        since=_validate_field("since", since),
        owner=_validate_field("owner", owner),
    )


def _banner_row(text: str, width: int) -> str:
    return f"| {text:<{width - 4}} |"


def format_announcement(announcement: Announcement, *, width: int = 80) -> str:
    fields = (
        f"WHAT: {announcement.what}",
        f"NEEDED: {announcement.needed}",
        f"SINCE: {announcement.since}",
        f"OWNER: {announcement.owner}",
    )
    if announcement.kind == "ALL-CLEAR":
        return " | ".join((announcement.kind, *fields))

    banner_width = max(
        width,
        len(announcement.kind) + 4,
        *(len(field) + 4 for field in fields),
    )
    border = "=" * banner_width
    rows = (
        _banner_row(announcement.kind, banner_width),
        *(_banner_row(field, banner_width) for field in fields),
    )
    return "\n".join((border, *rows, border))
