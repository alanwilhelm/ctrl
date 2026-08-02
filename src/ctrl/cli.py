from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ctrl import __version__
from ctrl.appserver import AppServerClient, ControlError
from ctrl.blockers import (
    KIND_BLOCKER,
    VALID_KINDS,
    announcement_payload,
    clear_blocker,
    raise_blocker,
    read_blockers,
    render_all,
    render_all_clear,
    render_banner,
    validate_single_line,
)
from ctrl.operations import (
    VALID_REASONING_EFFORTS,
    list_thread_summaries,
    normalize_lane,
    read_thread,
    resolve_thread,
    send_message,
    spawn_thread,
    thread_status,
)
from ctrl.redaction import redact_value

DEFAULT_SOCKET = Path("~/.codex/app-server-control/app-server-control.sock").expanduser()
DEFAULT_REGISTRY = Path("~/.local/state/ctrl/threads.json").expanduser()
DEFAULT_BLOCKERS = Path("~/.local/state/ctrl/blockers.json").expanduser()

BLOCKERS_PRESENT = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctrl",
        description="Control persistent Codex App Server threads.",
    )
    parser.add_argument("--version", action="version", version=f"ctrl {__version__}")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--blockers-file", type=Path, default=DEFAULT_BLOCKERS)
    parser.add_argument("--timeout", type=float, default=15.0)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="read local CTRL and App Server health")

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

    block = commands.add_parser("block", help="raise an attention banner for a lane")
    block.add_argument("lane", help="CTRL lane the blocker belongs to")
    block.add_argument("--what", required=True, help="one line: what is wrong")
    block.add_argument("--needed", required=True, help="the exact input or decision")
    block.add_argument(
        "--kind",
        choices=VALID_KINDS,
        default=KIND_BLOCKER,
        help="blocker needs a human; hold is stopped but self-driving",
    )
    block.add_argument(
        "--who",
        help="BLOCKER attention target (stored only for hold compatibility)",
    )
    block.add_argument("--json", action="store_true", help="emit JSON")

    clear = commands.add_parser("clear", help="resolve a lane's blocker")
    clear.add_argument("lane", help="CTRL lane to clear")
    clear.add_argument("--note", help="what resolved it")
    clear.add_argument("--json", action="store_true", help="emit JSON")

    blockers = commands.add_parser(
        "blockers",
        help="show open blockers; exit 2 if any are open",
    )
    blockers.add_argument("--json", action="store_true", help="emit JSON")
    blockers.add_argument(
        "--quiet",
        action="store_true",
        help="print nothing; use the exit code only",
    )
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


def _attention(args: argparse.Namespace, blockers_path: Path) -> int:
    """Local attention state; never touches the App Server."""
    if args.command == "block":
        owner = normalize_lane(validate_single_line("owner", args.lane))
        record = raise_blocker(
            blockers_path,
            owner,
            what=args.what,
            needed=args.needed,
            kind=args.kind,
            who=args.who,
            now=datetime.now().astimezone(),
        )
        if args.json:
            print(json.dumps(announcement_payload(owner, record), indent=2, sort_keys=True))
        else:
            width = shutil.get_terminal_size(fallback=(80, 24)).columns
            print(render_banner(owner, record, width=width))
        return 0

    if args.command == "clear":
        lane = normalize_lane(validate_single_line("owner", args.lane))
        note = None if args.note is None else validate_single_line("note", args.note)
        record = clear_blocker(blockers_path, lane)
        if record is None:
            raise ControlError(f"no open blocker for lane: {lane}")
        if args.json:
            payload = announcement_payload(
                lane, record, all_clear=True, note=note
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(render_all_clear(lane, record, note))
        return 0

    open_blockers = read_blockers(blockers_path)
    if args.json:
        payloads = {
            owner: announcement_payload(owner, record)
            for owner, record in open_blockers.items()
        }
        print(json.dumps(payloads, indent=2, sort_keys=True))
    elif not args.quiet:
        width = shutil.get_terminal_size(fallback=(80, 24)).columns
        print(render_all(open_blockers, width=width))
    return BLOCKERS_PRESENT if open_blockers else 0


def main() -> int:
    args = build_parser().parse_args()
    socket_path = args.socket.expanduser()
    registry_path = args.registry.expanduser()
    blockers_path = args.blockers_file.expanduser()
    try:
        if args.command in ("block", "clear", "blockers"):
            return _attention(args, blockers_path)
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
