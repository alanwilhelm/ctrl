# CTRL Troubleshooting

## Start With Read-Only Evidence

```bash
command -v ctrl
ctrl --version
ctrl doctor
codex app-server daemon version
```

Keep the exact stderr and exit status. Do not restart the daemon before discovering whether the failure is package resolution, socket state, protocol compatibility, registry data, or thread state.

## `ctrl: app-server socket not found`

Check the doctor output and official daemon state:

```bash
ctrl doctor
codex app-server daemon version
```

Expected socket:

```text
~/.codex/app-server-control/app-server-control.sock
```

If the managed daemon is stopped, start it through the official manager:

```bash
codex app-server daemon start
```

Do not launch a second ad hoc `codex app-server` process against an arbitrary socket while the managed service is intended to be authoritative.

## WebSocket Upgrade or Initialization Failure

Possible causes:

- wrong socket path;
- non-App-Server process at the path;
- client/server protocol drift;
- daemon restarting during connection;
- stale socket after a crashed unmanaged process.

Collect:

```bash
ctrl doctor
codex app-server daemon version
ctrl --timeout 30 list --limit 1
```

Compare CTRL's supported environment with the running Codex version. Do not delete sockets belonging to a running daemon.

## Registry Not Found

The registry appears only after a successful CTRL spawn. Raw thread IDs remain usable. Discover by cwd:

```bash
ctrl list --cwd /absolute/worktree --limit 50
ctrl status 019f...
```

If an older tool used another registry, do not silently copy it. Validate every alias-to-thread mapping against cwd and status before migration.

## Lane Not Found

Confirm spelling and normalized prefix:

```bash
ctrl status issue-123
ctrl status lane-issue-123
```

Inspect the registry locally without publishing it:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path.home()/'.local/state/ctrl/threads.json'
print(json.dumps(json.loads(p.read_text()), indent=2, sort_keys=True))
PY
```

A missing alias is not evidence that the thread does not exist.

## Stale Lane

Symptoms:

- lane resolves but thread read fails;
- cwd no longer exists;
- thread belongs to a different work item;
- duplicate aliases point to one thread.

Use `ctrl list`, raw thread reads, and repository state to establish truth. Back up the registry before a manual repair. CTRL has no registry-edit command yet.

## Thread Is `notLoaded`

This is a persisted but unmaterialized thread. `ctrl send` resumes it automatically. For read-only diagnosis, try status/read first. Do not spawn a duplicate merely to get `loaded: true`.

## Active Thread Has No In-Progress Turn

This may be a transitional state or evidence of another controller. Do not retry send in a loop. Capture:

```bash
ctrl status THREAD
ctrl read THREAD
```

Wait briefly only when a known state transition is occurring. Otherwise resolve ownership and client activity.

## Message Appears Undelivered

A successful CTRL response includes `delivery` and `turnId`. Verify with one subsequent status/read call. Never resend solely because the worker has not produced text yet.

Possible states:

- `started`: a new turn was accepted;
- `steered`: input was added to the exact active turn;
- command error: no successful receipt proof.

If the command timed out after App Server may have accepted the request, inspect thread history before retrying. Current CTRL does not provide idempotency keys.

## Wrong Model or Reasoning Effort

The spawn response is authoritative for the newly created thread:

```json
{
  "model": "gpt-5.6-sol",
  "reasoningEffort": "xhigh"
}
```

If either differs:

1. do not send implementation work;
2. retain the response and thread ID;
3. check daemon/client versions;
4. inspect whether provider fallback occurred;
5. create a replacement only after deciding what to do with the first thread.

Do not infer effective reasoning from the CLI invocation alone.

## Duplicate Threads for One Worktree

Stop stateful commands. List exact cwd and compare IDs, timestamps, names, status, and turns. Choose one owner thread. Do not send cancellation or deletion calls through invented commands; current CTRL does not expose them.

## Duplicate Work Delivery

Stop all controllers. Read the active thread and identify whether duplicate instructions became separate turns or repeated steering input. Preserve evidence, assign one controller, and continue with one explicit correction only if needed.

## CLI Not Found After Installation

Check user executable path:

```bash
python3 -m site --user-base
printf '%s\n' "$PATH"
```

With uv, the executable is commonly under `~/.local/bin`. Reinstall from canonical source rather than copying a generated script:

```bash
uv tool install --editable --force /path/to/ctrl
```

## Editable Installation Points at Wrong Checkout

Inspect import resolution in the tool environment or run the source module directly. Remove the divergent installation and reinstall from `/path/to/ctrl`. Avoid multiple active checkouts with identical package names.

## Test Failures

```bash
cd /path/to/ctrl
pytest -q
python3 -m compileall -q src tests
```

A live App Server check is separate from unit tests:

```bash
PYTHONPATH=src python3 -m ctrl.cli doctor
PYTHONPATH=src python3 -m ctrl.cli list --limit 3
```

Both live checks are read-only.

## Information to Capture for a Bug

- CTRL version and resolved executable;
- Codex CLI and App Server versions;
- selected socket and registry paths;
- exact command with secrets removed;
- exit status and redacted stderr;
- whether the operation was read-only, spawn, or send;
- raw thread ID and cwd when relevant;
- before/after thread status;
- whether another controller or TUI was attached;
- repository and worktree Git state.

Never include access tokens, API keys, cookies, private keys, connection strings, or raw credential-bearing transcripts.
