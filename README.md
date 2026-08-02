# CTRL

**A small, scriptable control plane for persistent Codex App Server threads.**

CTRL gives humans and coordinating agents one consistent command-line interface for discovering, inspecting, creating, and messaging persistent Codex workers. It talks directly to the local managed Codex App Server over its Unix socket and returns structured JSON.

```bash
ctrl doctor
ctrl list --limit 10
ctrl status issue-123
ctrl spawn /path/to/worktree --lane issue-123
ctrl send issue-123 "Implement the accepted scope and report proof"
```

> **Project status:** early and operational. Version 0.1.0 supports the six commands documented below and has been exercised against Codex App Server 0.146.0 on Linux. The current release is intentionally smaller than the intended control plane; see [Current scope](#current-scope) before building automation around it.

## What CTRL is

Codex App Server can keep many independent threads alive in one managed daemon. That is useful for coordinating long-lived workers, but raw thread UUIDs and one-off JSON-RPC scripts make the operating model hard to see and easy to misuse.

CTRL provides:

- one command for App Server health and version discovery;
- persisted and loaded thread discovery;
- compact status and complete thread reads;
- memorable lane aliases for newly created threads;
- explicit model and reasoning selection at thread creation;
- safe state-aware delivery: resume, start, or steer;
- JSON output for both humans and automation;
- recursive redaction of credential-shaped output;
- a detailed operating skill for Hermes and Codex agents.

CTRL is a client. It does not replace, supervise, restart, or reconfigure Codex App Server.

### The problem in one picture

```text
Without CTRL

coordinator ── custom WebSocket code ──┐
operator ───── copied control script ──┼── Codex App Server
shell job ──── raw thread UUIDs ───────┘

With CTRL

coordinator ──┐
operator ─────┼── ctrl ── Codex App Server ── persistent worker threads
shell job ────┘
```

The goal is one narrow interface with visible semantics, not another agent framework.

## Who it is for

CTRL is for people running several persistent Codex workers across isolated repositories or Git worktrees. It is especially useful when:

- one coordinator manages many worker threads;
- workers must survive client restarts;
- worktree and branch ownership matter;
- automation needs JSON rather than terminal rendering;
- a human wants to attach the official Codex TUI without making tmux the source of truth;
- planning and execution are deliberately separate.

If you only run one short-lived interactive Codex session, the normal Codex CLI is probably enough.

## Requirements

- Linux
- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) for the recommended tool installation
- Codex CLI with the managed App Server daemon
- a Unix control socket, normally:

```text
~/.codex/app-server-control/app-server-control.sock
```

The current release has been tested with:

```text
CTRL:             0.1.0
Codex CLI:        0.146.0
Codex App Server: 0.146.0
```

## Installation

Clone or download this repository, then install the checkout as an editable user tool:

```bash
cd /path/to/ctrl
uv tool install --editable .
```

Verify the executable and daemon connection:

```bash
command -v ctrl
ctrl --version
ctrl doctor
```

An editable installation keeps the executable pointed at the canonical checkout rather than copying source into an unrelated runtime directory.

To reinstall after package metadata changes:

```bash
uv tool install --editable --force /path/to/ctrl
```

### Agent skill installation

The repository root is also a complete agent skill. Symlink it rather than copying it so the CLI documentation and operating rules cannot drift apart.

For Hermes Agent:

```bash
mkdir -p ~/.hermes/skills
ln -s /path/to/ctrl ~/.hermes/skills/ctrl
```

For Codex:

```bash
mkdir -p ~/.codex/skills
ln -s /path/to/ctrl ~/.codex/skills/ctrl
```

The detailed skill is [`SKILL.md`](SKILL.md). Supporting references cover the [command surface](references/command-reference.md), [operating model](references/operating-model.md), and [troubleshooting](references/troubleshooting.md).

## Quick start

Start read-only. These commands do not create threads or execute agent work.

### 1. Check CTRL and App Server

```bash
ctrl doctor
```

Example shape:

```json
{
  "appServer": {
    "appServerVersion": "0.146.0",
    "status": "running"
  },
  "ctrlVersion": "0.1.0",
  "registry": "/home/user/.local/state/ctrl/threads.json",
  "registryExists": false,
  "socket": "/home/user/.codex/app-server-control/app-server-control.sock",
  "socketReady": true
}
```

A missing registry is normal before the first CTRL-created thread. A missing socket is not.

### 2. Discover existing threads

```bash
ctrl list --limit 10
```

Filter by exact working directory:

```bash
ctrl list --cwd /absolute/path/to/worktree --limit 20
```

`loaded: false` means a persisted thread is not currently materialized in the daemon. It does not mean the thread is dead.

### 3. Inspect one thread

Compact status:

```bash
ctrl status 019f...
```

Full thread and turns:

```bash
ctrl read 019f...
```

After CTRL registers a lane, either form works:

```bash
ctrl status issue-123
ctrl status lane-issue-123
```

### 4. Create an isolated worker

`spawn` creates a real persistent App Server thread, so inspect the worktree and existing threads first.

```bash
ctrl spawn /absolute/path/to/issue-123 \
  --lane issue-123 \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh
```

Example response:

```json
{
  "cwd": "/absolute/path/to/issue-123",
  "lane": "lane-issue-123",
  "model": "gpt-5.6-sol",
  "reasoningEffort": "xhigh",
  "threadId": "019f..."
}
```

Spawning creates the thread and records the alias. It does not start a turn.

### 5. Send one bounded instruction

```bash
ctrl send issue-123 \
  "Implement only the accepted scope. Preserve unrelated work. Run the required tests. Do not merge or publish."
```

Long instructions can come from stdin:

```bash
ctrl send issue-123 <<'EOF'
Implement the accepted issue scope.

Constraints:
- Work only in the assigned worktree.
- Preserve unrelated changes.
- Do not merge, publish, or deploy.

Proof:
- Run targeted tests.
- Run the repository-required full suite.
- Report changed paths and exact command results.
EOF
```

CTRL reads current state before delivery:

- unloaded thread → `thread/resume`, then delivery;
- active thread with an in-progress turn → `turn/steer` against that exact turn;
- idle thread → `turn/start`.

The result reports `started` or `steered` and the turn ID. That proves receipt, not completion.

## Commands

| Command | Purpose | App Server mutation | Executes work |
|---|---|---:|---:|
| `ctrl doctor` | Read local CTRL and daemon health | no | no |
| `ctrl list` | List persisted threads and loaded state | no | no |
| `ctrl status THREAD` | Return compact thread state | no | no |
| `ctrl read THREAD` | Return the full thread payload | no | no |
| `ctrl spawn REPO --lane NAME` | Create and register a persistent thread | yes | no |
| `ctrl send THREAD MESSAGE` | Resume/start/steer a turn | yes | yes |

Global options precede the command:

```text
--socket PATH      App Server Unix socket
--registry PATH    lane-to-thread JSON registry
--timeout SECONDS  request timeout
--version          CTRL version
```

Defaults:

```text
socket:   ~/.codex/app-server-control/app-server-control.sock
registry: ~/.local/state/ctrl/threads.json
timeout:  15 seconds
```

Run `ctrl --help` or see the [complete command reference](references/command-reference.md).

## Model and reasoning policy

CTRL accepts the reasoning levels exposed by the tested App Server:

```text
low, medium, high, xhigh, max, ultra
```

The default spawn configuration is designed for implementation workers:

```text
model:            gpt-5.6-sol
reasoning effort: xhigh
```

A coordinator should be created explicitly:

```bash
ctrl spawn /absolute/coordinator/workspace \
  --lane coordinator \
  --model gpt-5.6-sol \
  --reasoning-effort max
```

CTRL sends reasoning as thread configuration:

```json
{
  "config": {
    "model_reasoning_effort": "xhigh"
  }
}
```

Always verify the returned `model` and `reasoningEffort`. Request parameters alone are not proof of the daemon's effective configuration.

## Safety model

CTRL intentionally exposes powerful App Server operations. The CLI is small so the boundary stays obvious.

### One controller

Use **one controller per thread**. Several clients may observe the same daemon, but a human TUI and an automated coordinator should not steer the same active thread concurrently.

### Isolated worktrees

New workers should run in dedicated Git worktrees with non-overlapping ownership. Before spawning:

```bash
git -C /absolute/worktree status --short --branch
git -C /absolute/worktree rev-parse --show-toplevel
git -C /absolute/worktree branch --show-current
ctrl list --cwd /absolute/worktree --limit 20
```

Prefer reusing an owned persisted thread over creating a duplicate.

### Full-access turns

New turns currently use:

```json
{
  "approvalPolicy": "never",
  "sandboxPolicy": {
    "type": "dangerFullAccess"
  }
}
```

That policy is intentional for trusted workers in isolated worktrees. It also means an open-ended or misdirected instruction can cause real damage. CTRL does not replace repository isolation, scope locks, code review, or separate merge and publication authority.

### No automatic completion claims

An accepted message, idle thread, or worker final response does not prove that code is correct. Inspect the repository and rerun required checks independently.

### Redaction

CTRL recursively redacts credential-shaped keys and text before printing JSON. Redaction is defense in depth, not a reason to publish complete private transcripts.

## Architecture

```text
┌──────────────────────────────────────────────────────────┐
│ Human or coordinator                                     │
│ selects admitted work, worktree, ownership, and policy   │
└──────────────────────────┬───────────────────────────────┘
                           │ stable CLI + JSON
┌──────────────────────────▼───────────────────────────────┐
│ CTRL                                                     │
│                                                          │
│ cli.py        command parsing and output                  │
│ operations.py thread/lane/start/steer behavior            │
│ appserver.py  Unix socket + WebSocket JSON-RPC            │
│ redaction.py  output sanitization                         │
└──────────────────────────┬───────────────────────────────┘
                           │ Codex App Server protocol
┌──────────────────────────▼───────────────────────────────┐
│ Managed Codex App Server                                 │
│ one daemon, many persistent independent threads          │
└───────────────┬────────────────────┬─────────────────────┘
                │                    │
        coordinator/max       workers/xhigh
                              isolated worktrees
```

The local lane registry contains only alias-to-thread mappings:

```json
{
  "lane-issue-123": "019f..."
}
```

It is not the authoritative thread database. Codex App Server remains authoritative.

## Planning integration

CTRL deliberately does not decide what work should happen. A planning system such as Dragonslayer can resolve decisions and produce an implementation specification; a human or authorized coordinator must still admit a bounded unit before CTRL creates or messages a worker.

```text
planning and synthesis
        ↓ explicit admission
CTRL coordination
        ↓
Codex App Server execution
        ↓
independent verification
```

Version 0.1.0 does not parse planning artifacts or provide an admission command.

## Human visibility

The official Codex TUI can attach to an existing App Server thread:

```bash
codex --remote unix://$HOME/.codex/app-server-control/app-server-control.sock \
  resume 019f...
```

The attached TUI is interactive, not a passive dashboard. Decide whether CTRL or the human owns control before submitting input.

## Current scope

### Implemented in 0.1.0

- managed Unix socket connection;
- WebSocket JSON-RPC initialization and requests;
- App Server health/version readback;
- persisted thread discovery;
- loaded-state correlation;
- compact and full thread reads;
- lane alias creation and resolution;
- explicit model and reasoning configuration;
- automatic resume during message delivery;
- active-turn steering and idle-turn start;
- recursive credential-shaped redaction;
- structured JSON output;
- Hermes and Codex operating skill.

### Not implemented yet

- durable work-item database;
- planning artifact ingestion or admission;
- controller leases and heartbeats;
- idempotency keys for stateful operations;
- retry and backoff policy;
- event subscription service;
- automatic completion detection;
- interrupt or stop command;
- verification evidence records;
- registry editing commands;
- fleet revision manifest;
- destructive thread deletion.

The absence of a feature here is intentional documentation, not an invitation to assume an equivalent hidden command exists.

## Recovery basics

Check the official daemon before changing anything:

```bash
ctrl doctor
codex app-server daemon version
```

If the managed daemon is stopped:

```bash
codex app-server daemon start
ctrl doctor
```

If a lane is missing, discover by cwd and use the raw thread ID:

```bash
ctrl list --cwd /absolute/worktree --limit 50
ctrl status 019f...
```

If a stateful command times out, inspect the thread before retrying. CTRL 0.1.0 does not yet attach idempotency keys to operations.

See [troubleshooting](references/troubleshooting.md) for the complete diagnostic paths.

## Development

Create an environment however you prefer; the project itself has no runtime dependencies beyond Python's standard library.

Run the complete suite:

```bash
pytest -q
```

Compile-check source and tests:

```bash
python3 -m compileall -q src tests
```

Exercise the source checkout without installing:

```bash
PYTHONPATH=src python3 -m ctrl.cli doctor
PYTHONPATH=src python3 -m ctrl.cli list --limit 3
```

Those live checks are read-only. Do not use `spawn` as a smoke test against a valuable daemon or worktree.

Repository layout:

```text
ctrl/
├── README.md
├── SKILL.md
├── pyproject.toml
├── references/
│   ├── command-reference.md
│   ├── operating-model.md
│   └── troubleshooting.md
├── src/ctrl/
│   ├── appserver.py
│   ├── cli.py
│   ├── operations.py
│   └── redaction.py
└── tests/
```

Changes to command behavior should update the CLI, tests, README, skill, and command reference together.

## Design principles

1. **One interface.** Humans and agents use the same command surface.
2. **Protocol truth.** App Server thread and turn state outrank terminal rendering.
3. **Read before write.** Discovery precedes spawn or delivery.
4. **Explicit ownership.** One controller, one isolated worktree, bounded scope.
5. **Honest capability boundaries.** Documentation names what is absent.
6. **No copied runtime scripts.** Install from one canonical checkout.
7. **Proof after execution.** Worker output is a report, not verification.

## License

CTRL is available under the [MIT License](LICENSE).
