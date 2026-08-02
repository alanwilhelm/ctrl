from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refreshtoken",
    "refresh_token",
    "authorization",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "database_url",
    "connection_string",
    "credentials",
    "private_key",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;\"']+"),
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|"
        r"client[_-]?secret|database[_-]?url|connection[_-]?string)\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
    ),
    re.compile(r"\b(?:sk|ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^:/\s]+:)[^@/\s]+(@)"),
]


def redact_text(value: str) -> str:
    for pattern in SECRET_PATTERNS:
        def replacement(match: re.Match[str]) -> str:
            if match.lastindex == 2:
                return f"{match.group(1)}[REDACTED]{match.group(2)}"
            if match.lastindex == 1:
                return f"{match.group(1)}[REDACTED]"
            return "[REDACTED]"

        value = pattern.sub(replacement, value)
    return value


def redact_value(value: Any, key: str | None = None) -> Any:
    normalized_key = key.lower().replace("-", "_") if key else None
    if normalized_key in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(item_key): redact_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    return value
