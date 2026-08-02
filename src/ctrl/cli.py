from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ctrl import __version__
from ctrl.announce import (
    VALID_ANNOUNCEMENT_TYPES,
    format_announcement,
    validate_announcement,
)
from ctrl.appserver import AppServerClient, ControlError
from ctrl.operations import (
    VALID_REASONING_EFFORTS,
    list_thread_summaries,
    read_thread,
    resolve_thread,
    send_message,
    spawn_thread,
    thread_status,
)
from ctrl.redaction import redact_value

DEFAULT_SOCKET = Path("~/.codex/app-server-control/app-server-control.sock").expanduser()
DEFAULT_REGISTRY = Path("~/.local/state/ctrl/threads.json").expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctrl",
        description="Control persistent Codex App Server threads.",
    )
    parser.add_argument("--version", action="version", version=f"ctrl {__version__}")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--timeout", type=float, default=15.0)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="read local CTRL and App Server health")

    announce = commands.add_parser(
        "announce", help="surface a blocker, gate hold, or all-clear"
    )
    announce.add_argument("kind", choices=VALID_ANNOUNCEMENT_TYPES)
    announce.add_argument("--what", required=True)
    announce.add_argument("--needed", required=True)
    announce.add_argument("--since", required=True)
    announce.add_argument("--owner", required=True)
    announce.add_argument("--json", action="store_true", dest="json_output")

    list_command = commands.add_parser("list", help="list persisted App Server threads")
    list_command.add_argument("--limit", type=int, default=200)
    list_command.add_argument("--cwd", action="append")

    status = commands.add_parser("status", help="return compact thread state")
    status.add_argument("thread", help="thread UUID or CTRL lane")
    read = commands.add_parser("read", help="return full thread payload")
    read.add_argument("thread", help="thread UUID or CTRL lane")

    spawn = commands.add_parser("spawn", help="create and register a persistent thread")
    spawn.add_argument("repo_dir", type=Path)
    spawn.add_argument("--lane", required=True)
    spawn.add_argument("--model", default="gpt-5.6-sol")
    spawn.add_argument(
        "--reasoning-effort",
        choices=VALID_REASONING_EFFORTS,
        default="xhigh",
    )

    send = commands.add_parser("send", help="start or steer a thread turn")
    send.add_argument("thread", help="thread UUID or CTRL lane")
    send.add_argument("message", nargs="?")
    return parser


def _message(value: str | None) -> str:
    if value is not None:
        return value
    if sys.stdin.isatty():
        raise ControlError("message required as an argument or on stdin")
    message = sys.stdin.read()
    if not message.strip():
        raise ControlError("message is empty")
    return message


def _doctor(socket_path: Path, registry_path: Path) -> dict[str, object]:
    result = subprocess.run(
        ["codex", "app-server", "daemon", "version"],
        text=True,
        capture_output=True,
        check=False,
    )
    daemon: object
    try:
        daemon = json.loads(result.stdout) if result.stdout else None
    except json.JSONDecodeError:
        daemon = {"error": result.stderr.strip() or result.stdout.strip()}
    return {
        "ctrlVersion": __version__,
        "socket": str(socket_path),
        "socketReady": socket_path.is_socket(),
        "registry": str(registry_path),
        "registryExists": registry_path.is_file(),
        "appServer": daemon,
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "announce":
            announcement = validate_announcement(
                args.kind,
                what=args.what,
                needed=args.needed,
                since=args.since,
                owner=args.owner,
            )
            if args.json_output:
                print(json.dumps(announcement.as_dict(), indent=2, sort_keys=True))
            else:
                width = shutil.get_terminal_size(fallback=(80, 24)).columns
                print(format_announcement(announcement, width=width))
            return 0

        socket_path = args.socket.expanduser()
        registry_path = args.registry.expanduser()
        if args.command == "doctor":
            output = _doctor(socket_path, registry_path)
        else:
            with AppServerClient(socket_path, args.timeout) as client:
                if args.command == "list":
                    output = {
                        "threads": list_thread_summaries(
                            client, limit=args.limit, cwd=args.cwd
                        )
                    }
                elif args.command == "spawn":
                    output = spawn_thread(
                        client,
                        args.repo_dir,
                        lane=args.lane,
                        registry_path=registry_path,
                        model=args.model,
                        reasoning_effort=args.reasoning_effort,
                    )
                else:
                    thread_id = resolve_thread(args.thread, registry_path)
                    if args.command == "status":
                        output = thread_status(client, thread_id)
                    elif args.command == "read":
                        output = {"thread": read_thread(client, thread_id)}
                    else:
                        output = send_message(client, thread_id, _message(args.message))
        print(json.dumps(redact_value(output), indent=2, sort_keys=True))
        return 0
    except (ControlError, OSError, TimeoutError, ValueError) as exc:
        print(f"ctrl: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
