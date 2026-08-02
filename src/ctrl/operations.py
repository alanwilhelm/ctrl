from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from ctrl.appserver import ControlError

VALID_REASONING_EFFORTS = (
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
)


def normalize_lane(value: str) -> str:
    return value if value.startswith("lane-") else f"lane-{value}"


def build_thread_start_params(
    repo_dir: Path,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if reasoning_effort is not None and reasoning_effort not in VALID_REASONING_EFFORTS:
        choices = ", ".join(VALID_REASONING_EFFORTS)
        raise ValueError(f"invalid reasoning effort {reasoning_effort!r}; choose one of: {choices}")

    params: dict[str, Any] = {"cwd": str(repo_dir.expanduser().resolve())}
    if model:
        params["model"] = model
    if reasoning_effort:
        params["config"] = {"model_reasoning_effort": reasoning_effort}
    return params


class Client(Protocol):
    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...


def read_registry(path: Path, *, required: bool = True) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if required:
            raise ControlError(f"thread registry not found: {path}") from exc
        return {}
    except json.JSONDecodeError as exc:
        raise ControlError(f"invalid thread registry {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ControlError(f"thread registry is not an object: {path}")
    return {
        str(alias): thread_id
        for alias, thread_id in value.items()
        if isinstance(thread_id, str) and thread_id
    }


def write_registry(path: Path, registry: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def resolve_thread(value: str, registry_path: Path) -> str:
    if value.startswith("019") and "-" in value:
        return value
    alias = normalize_lane(value)
    thread_id = read_registry(registry_path).get(alias)
    if not thread_id:
        raise ControlError(f"lane not found in {registry_path}: {alias}")
    return thread_id


def read_thread(client: Client, thread_id: str) -> dict[str, Any]:
    result = client.request(
        "thread/read", {"threadId": thread_id, "includeTurns": True}
    )
    thread = result.get("thread")
    if not isinstance(thread, dict):
        raise ControlError("thread/read response is missing thread")
    return thread


def active_turn_id(thread: dict[str, Any]) -> str | None:
    turns = thread.get("turns", [])
    if not isinstance(turns, list):
        return None
    for turn in reversed(turns):
        if isinstance(turn, dict) and turn.get("status") == "inProgress":
            turn_id = turn.get("id")
            return turn_id if isinstance(turn_id, str) else None
    return None


def list_thread_summaries(
    client: Client, *, limit: int = 200, cwd: list[str] | None = None
) -> list[dict[str, Any]]:
    result = client.request(
        "thread/list",
        {
            "limit": limit,
            "sortKey": "recency_at",
            "sortDirection": "desc",
            "useStateDbOnly": True,
            **({"cwd": cwd} if cwd else {}),
        },
    )
    threads = result.get("data")
    if not isinstance(threads, list):
        raise ControlError("thread/list response is missing data")
    loaded_result = client.request("thread/loaded/list", {"limit": 100})
    loaded_values = loaded_result.get("data")
    loaded = set(loaded_values) if isinstance(loaded_values, list) else set()
    summaries = []
    for thread in threads:
        if not isinstance(thread, dict):
            continue
        thread_id = thread.get("id")
        summaries.append(
            {
                "threadId": thread_id,
                "loaded": thread_id in loaded,
                "cwd": thread.get("cwd"),
                "name": thread.get("name"),
                "status": thread.get("status"),
            }
        )
    return summaries


def thread_status(client: Client, thread_id: str) -> dict[str, Any]:
    thread = read_thread(client, thread_id)
    turns = thread.get("turns", [])
    latest = turns[-1] if isinstance(turns, list) and turns else None
    return {
        "threadId": thread.get("id"),
        "status": thread.get("status"),
        "canAcceptDirectInput": thread.get("canAcceptDirectInput"),
        "turnCount": len(turns) if isinstance(turns, list) else None,
        "latestTurn": (
            {
                "id": latest.get("id"),
                "status": latest.get("status"),
                "itemCount": len(latest.get("items", [])),
            }
            if isinstance(latest, dict)
            else None
        ),
    }


def spawn_thread(
    client: Client,
    repo_dir: Path,
    *,
    lane: str,
    registry_path: Path,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    resolved_repo = repo_dir.expanduser().resolve()
    if not resolved_repo.is_dir():
        raise ControlError(f"repo directory not found: {resolved_repo}")
    params = build_thread_start_params(
        resolved_repo, model=model, reasoning_effort=reasoning_effort
    )
    result = client.request("thread/start", params)
    thread = result.get("thread")
    thread_id = thread.get("id") if isinstance(thread, dict) else None
    if not isinstance(thread_id, str) or not thread_id:
        raise ControlError("thread/start response is missing thread id")

    alias = normalize_lane(lane)
    registry = read_registry(registry_path, required=False)
    registry[alias] = thread_id
    write_registry(registry_path, registry)
    return {
        "threadId": thread_id,
        "lane": alias,
        "cwd": str(resolved_repo),
        "model": result.get("model"),
        "reasoningEffort": result.get("reasoningEffort"),
    }


def send_message(client: Client, thread_id: str, message: str) -> dict[str, Any]:
    if not message.strip():
        raise ControlError("message is empty")
    thread = read_thread(client, thread_id)
    status = thread.get("status")
    status_type = status.get("type") if isinstance(status, dict) else None
    if status_type == "notLoaded":
        resumed = client.request("thread/resume", {"threadId": thread_id})
        resumed_thread = resumed.get("thread")
        if not isinstance(resumed_thread, dict):
            raise ControlError("thread/resume response is missing thread")
        thread = resumed_thread

    turn_id = active_turn_id(thread)
    text_input = [{"type": "text", "text": message}]
    if turn_id is not None:
        result = client.request(
            "turn/steer",
            {
                "threadId": thread_id,
                "expectedTurnId": turn_id,
                "input": text_input,
            },
        )
        delivery = "steered"
    else:
        result = client.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": text_input,
                "approvalPolicy": "never",
                "sandboxPolicy": {"type": "dangerFullAccess"},
            },
        )
        delivery = "started"
    turn = result.get("turn")
    returned_turn_id = turn.get("id") if isinstance(turn, dict) else result.get("turnId")
    return {
        "threadId": thread_id,
        "delivery": delivery,
        "turnId": returned_turn_id,
    }
