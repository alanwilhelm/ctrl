from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ctrl.operations import (
    VALID_REASONING_EFFORTS,
    build_thread_start_params,
    normalize_lane,
)


def test_worker_thread_start_sets_sol_xhigh_explicitly(tmp_path: Path) -> None:
    params = build_thread_start_params(
        tmp_path,
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
    )

    assert params == {
        "cwd": str(tmp_path.resolve()),
        "model": "gpt-5.6-sol",
        "config": {"model_reasoning_effort": "xhigh"},
    }


def test_thread_start_omits_optional_overrides(tmp_path: Path) -> None:
    assert build_thread_start_params(tmp_path) == {"cwd": str(tmp_path.resolve())}


def test_invalid_reasoning_effort_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid reasoning effort"):
        build_thread_start_params(tmp_path, reasoning_effort="extreme")


def test_reasoning_efforts_match_codex_0146_catalog() -> None:
    assert VALID_REASONING_EFFORTS == (
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
        "ultra",
    )


def test_lane_names_are_stored_with_one_prefix() -> None:
    assert normalize_lane("worker-355") == "lane-worker-355"
    assert normalize_lane("lane-worker-355") == "lane-worker-355"


def test_cli_help_uses_ctrl_brand() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ctrl.cli", "--help"],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(Path.cwd() / "src")},
    )

    assert result.returncode == 0
    assert result.stdout.startswith("usage: ctrl")
    assert "codex-app-server-control" not in result.stdout
    for command in (
        "doctor",
        "list",
        "status",
        "read",
        "spawn",
        "send",
        "block",
        "clear",
        "blockers",
    ):
        assert command in result.stdout
    assert "return compact thread state" in result.stdout
    assert "return full thread payload" in result.stdout


def test_spawn_help_exposes_model_and_reasoning_policy() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ctrl.cli", "spawn", "--help"],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(Path.cwd() / "src")},
    )

    assert result.returncode == 0
    assert "--model" in result.stdout
    assert "--reasoning-effort" in result.stdout
    assert "xhigh" in result.stdout
