from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctrl.appserver import AppServerClient, ControlError
from ctrl.operations import (
    list_thread_summaries,
    read_registry,
    send_message,
    spawn_thread,
    thread_status,
)


class FakeClient:
    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def request(self, method: str, params: dict) -> dict:
        self.calls.append((method, params))
        response = self.responses[method]
        return json.loads(json.dumps(response))


def test_missing_socket_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ControlError, match="app-server socket not found"):
        AppServerClient(tmp_path / "missing.sock", 0.1).connect()


def test_spawn_records_lane_and_explicit_reasoning(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    registry = tmp_path / "state" / "threads.json"
    client = FakeClient(
        {
            "thread/start": {
                "thread": {"id": "019abc-test"},
                "model": "gpt-5.6-sol",
                "reasoningEffort": "xhigh",
            }
        }
    )

    result = spawn_thread(
        client,
        repo,
        lane="worker-1",
        registry_path=registry,
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
    )

    assert client.calls == [
        (
            "thread/start",
            {
                "cwd": str(repo.resolve()),
                "model": "gpt-5.6-sol",
                "config": {"model_reasoning_effort": "xhigh"},
            },
        )
    ]
    assert read_registry(registry) == {"lane-worker-1": "019abc-test"}
    assert result == {
        "threadId": "019abc-test",
        "lane": "lane-worker-1",
        "cwd": str(repo.resolve()),
        "model": "gpt-5.6-sol",
        "reasoningEffort": "xhigh",
    }


def test_spawn_refuses_missing_directory(tmp_path: Path) -> None:
    client = FakeClient({})
    with pytest.raises(ControlError, match="repo directory not found"):
        spawn_thread(
            client,
            tmp_path / "missing",
            lane="worker-1",
            registry_path=tmp_path / "threads.json",
        )
    assert client.calls == []


def test_send_starts_first_turn_when_fresh_thread_cannot_include_turns() -> None:
    class FreshThreadClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def request(self, method: str, params: dict) -> dict:
            self.calls.append((method, params))
            if method == "thread/read":
                raise ControlError(
                    "thread/read failed: includeTurns is unavailable before first user message"
                )
            if method == "turn/start":
                return {"turn": {"id": "turn-first"}}
            raise AssertionError(f"unexpected method: {method}")

    client = FreshThreadClient()

    result = send_message(client, "019abc-fresh", "Run the first bounded task")

    assert [method for method, _ in client.calls] == ["thread/read", "turn/start"]
    assert result == {
        "threadId": "019abc-fresh",
        "delivery": "started",
        "turnId": "turn-first",
    }


def test_send_resumes_unloaded_thread_then_starts_turn() -> None:
    client = FakeClient(
        {
            "thread/read": {"thread": {"id": "019abc-test", "status": {"type": "notLoaded"}, "turns": []}},
            "thread/resume": {"thread": {"id": "019abc-test", "status": {"type": "idle"}, "turns": []}},
            "turn/start": {"turn": {"id": "turn-1"}},
        }
    )

    result = send_message(client, "019abc-test", "Do the bounded task")

    assert [method for method, _ in client.calls] == ["thread/read", "thread/resume", "turn/start"]
    assert client.calls[-1][1] == {
        "threadId": "019abc-test",
        "input": [{"type": "text", "text": "Do the bounded task"}],
        "approvalPolicy": "never",
        "sandboxPolicy": {"type": "dangerFullAccess"},
    }
    assert result == {"threadId": "019abc-test", "delivery": "started", "turnId": "turn-1"}


def test_send_steers_exact_active_turn() -> None:
    client = FakeClient(
        {
            "thread/read": {
                "thread": {
                    "id": "019abc-test",
                    "status": {"type": "active"},
                    "turns": [{"id": "turn-active", "status": "inProgress"}],
                }
            },
            "turn/steer": {"turnId": "turn-active"},
        }
    )

    result = send_message(client, "019abc-test", "Narrow the scope")

    assert client.calls[-1] == (
        "turn/steer",
        {
            "threadId": "019abc-test",
            "expectedTurnId": "turn-active",
            "input": [{"type": "text", "text": "Narrow the scope"}],
        },
    )
    assert result["delivery"] == "steered"


def test_list_summarizes_loaded_state() -> None:
    client = FakeClient(
        {
            "thread/list": {
                "data": [
                    {
                        "id": "019abc-test",
                        "cwd": "/tmp/repo",
                        "name": "worker",
                        "status": {"type": "idle"},
                    }
                ],
                "nextCursor": None,
            },
            "thread/loaded/list": {"data": ["019abc-test"], "nextCursor": None},
        }
    )

    assert list_thread_summaries(client, limit=10) == [
        {
            "threadId": "019abc-test",
            "loaded": True,
            "cwd": "/tmp/repo",
            "name": "worker",
            "status": {"type": "idle"},
        }
    ]


def test_status_is_compact() -> None:
    client = FakeClient(
        {
            "thread/read": {
                "thread": {
                    "id": "019abc-test",
                    "status": {"type": "idle"},
                    "canAcceptDirectInput": True,
                    "turns": [{"id": "turn-1", "status": "completed", "items": [1, 2]}],
                }
            }
        }
    )

    assert thread_status(client, "019abc-test") == {
        "threadId": "019abc-test",
        "status": {"type": "idle"},
        "canAcceptDirectInput": True,
        "turnCount": 1,
        "latestTurn": {"id": "turn-1", "status": "completed", "itemCount": 2},
    }
