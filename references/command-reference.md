# CTRL Command Reference

## Installation

Install the canonical checkout as an editable user tool:

```bash
uv tool install --editable /path/to/ctrl
```

If a previous editable installation exists:

```bash
uv tool install --editable --force /path/to/ctrl
```

Verify resolution and source:

```bash
command -v ctrl
ctrl --version
python3 - <<'PY'
import ctrl
print(ctrl.__file__)
PY
```

The CLI executable may live under `~/.local/bin/ctrl`; ensure that directory is on `PATH`. An editable installation points package imports at the canonical checkout, so updates do not create copied runtime drift.

## Global Options

```text
--socket PATH        App Server Unix socket
--registry PATH      lane-to-thread JSON registry
--blockers-file PATH open-blocker JSON store
--timeout SECONDS    socket request timeout
--version            CTRL release
```

Defaults:

```text
--socket   ~/.codex/app-server-control/app-server-control.sock
--registry ~/.local/state/ctrl/threads.json
--blockers-file ~/.local/state/ctrl/blockers.json
--timeout  15
```

Global options precede the subcommand:

```bash
ctrl --timeout 30 list --limit 20
ctrl --registry /tmp/test-ctrl-registry.json status lane-test
```

## `ctrl doctor`

Read-only local health report:

```bash
ctrl doctor
```

Fields:

- `ctrlVersion`: installed CTRL package version;
- `socket`: selected socket path;
- `socketReady`: path exists as a Unix socket;
- `registry`: selected lane registry;
- `registryExists`: registry file currently exists;
- `appServer`: output of `codex app-server daemon version`.

`registryExists: false` is normal before the first successful spawn. `socketReady: false` blocks all App Server commands.

## `ctrl list`

```bash
ctrl list
ctrl list --limit 50
ctrl list --cwd /absolute/path
ctrl list --cwd /path/a --cwd /path/b --limit 100
```

This queries the App Server state database and correlates results with loaded threads. It does not create, resume, or message a thread.

## `ctrl status`

```bash
ctrl status 019f...
ctrl status lane-issue-123
ctrl status issue-123
```

Compact fields:

- `threadId`
- `status`
- `canAcceptDirectInput`
- `turnCount`
- `latestTurn.id`
- `latestTurn.status`
- `latestTurn.itemCount`

Lane resolution consults the selected registry. Raw thread IDs bypass lane lookup.

## `ctrl read`

```bash
ctrl read issue-123
```

Returns the full `thread/read` payload with turns included, then recursively redacts credential-shaped values. Use it for diagnostics and completion review; prefer `status` for loops or dashboards.

## `ctrl spawn`

```bash
ctrl spawn REPO_DIR --lane NAME \
  [--model MODEL] \
  [--reasoning-effort low|medium|high|xhigh|max|ultra]
```

Defaults:

```text
model:            gpt-5.6-sol
reasoning effort: xhigh
```

The target must already be a directory. CTRL sends `thread/start`, extracts the returned thread ID, and atomically updates the registry. It does not begin a turn.

Worker example:

```bash
ctrl spawn /path/to/worktrees/issue-123 \
  --lane issue-123 \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh
```

Coordinator example:

```bash
ctrl spawn /path/to/project-workspace \
  --lane project-coordinator \
  --model gpt-5.6-sol \
  --reasoning-effort max
```

## `ctrl send`

Argument form:

```bash
ctrl send issue-123 "Run the accepted task and report proof"
```

Stdin form:

```bash
ctrl send issue-123 <<'EOF'
Implement only the accepted scope.
Do not merge, publish, deploy, or modify unrelated files.
Run targeted and full tests.
EOF
```

The command reads current thread state first. It resumes an unloaded thread, steers the exact in-progress turn, or starts a new turn when idle. New turns use `approvalPolicy: never` and `sandboxPolicy.type: dangerFullAccess`.

Output:

```json
{
  "delivery": "started",
  "threadId": "019f...",
  "turnId": "..."
}
```

or:

```json
{
  "delivery": "steered",
  "threadId": "019f...",
  "turnId": "..."
}
```

## Attention Banners

`block`, `clear`, and `blockers` implement the ANNOUNCE protocol through one current
live-state file. They never open the App Server socket or read the lane registry. The
state survives session restarts, but it is not durable history; plandoc owns that.

All owner/lane, `what`, `needed`, `since`, `who`, and resolution-note text is
validated as nonblank, single-line, printable, and unambiguously one terminal cell
per character. Wide, ambiguous-width, combining, and control characters are rejected
before persistence or rendering. Loaded records receive the same validation, and a
corrupt store fails closed. Long accepted banner fields wrap inside the terminal-width
border instead of relying on terminal auto-wrap.

### `ctrl block`

```bash
ctrl block LANE --what TEXT --needed TEXT [--who TEXT] [--json]
ctrl block LANE --kind hold --what TEXT --needed TEXT [--who TEXT] [--json]
```

`--kind blocker` (default) maps to `BLOCKER`. `--kind hold` maps to `GATE-HOLD`.
The normalized lane is the `owner`; `--who` is only the attention target and defaults
to `$CTRL_BLOCKER_WHO` or `HUMAN`. Both kinds carry `what`, `needed`, the original
`since`, and `owner` in human and JSON output.

Re-raising an open lane updates `what` and `needed` but preserves the original
`since`. How long a blocker has stood is the number that matters.

Default output is a full-terminal-width banner. `--json` emits one machine-readable
announcement object with `type`, `what`, `needed`, `since`, `owner`, and `who`.

### `ctrl clear`

```bash
ctrl clear LANE [--note TEXT] [--json]
```

Emits one `ALL-CLEAR` line carrying `what`, `needed`, `since`, and `owner`, plus the
optional resolution note, then removes the current live state. `--json` emits the same
fields as an object.

### `ctrl blockers`

```bash
ctrl blockers          # render every open banner
ctrl blockers --json   # machine-readable
ctrl blockers --quiet  # exit code only
```

Exit codes: `0` no open blockers, `2` at least one open, `1` error. The `2` is what
makes blockers visible outside an agent — a shell prompt, status bar, or health check
can surface them without any agent cooperating:

```bash
ctrl blockers --quiet || notify-send "agent needs you"
```

JSON output maps each owner to its current announcement object and uses exact protocol
types: `BLOCKER` or `GATE-HOLD`. See the [operating model](operating-model.md#announcement-protocol)
for repetition, escalation, verification, exactly-once clear, and plandoc ownership.

## JSON Scripting

Extract a spawned thread ID:

```bash
thread_id=$(ctrl spawn /absolute/worktree --lane smoke \
  --model gpt-5.6-sol --reasoning-effort xhigh | jq -r .threadId)
printf '%s\n' "$thread_id"
```

List IDs for one cwd:

```bash
ctrl list --cwd /absolute/worktree | jq -r '.threads[].threadId'
```

Require daemon readiness:

```bash
ctrl doctor | jq -e '.socketReady == true and .appServer.status == "running"'
```

Avoid loops that repeatedly call `send`. Poll only read-only status, use bounded intervals, and stop when state is ambiguous.

## Source Invocation

Before installation or while repairing it:

```bash
cd /path/to/ctrl
PYTHONPATH=src python3 -m ctrl.cli --help
PYTHONPATH=src python3 -m ctrl.cli doctor
```

## Development Verification

```bash
cd /path/to/ctrl
pytest -q
python3 -m compileall -q src tests
```

Do not run stateful smoke commands against valuable worktrees. A future disposable live-spawn test should use a dedicated temporary Git repository and unique registry path.
