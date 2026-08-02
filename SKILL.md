---
name: ctrl
description: "Use when operating persistent Codex App Server threads or surfacing live blocker and gate state through CTRL, including announcements, health checks, discovery, lane registration, safe worker spawning, status inspection, reads, and bounded message delivery."
version: 0.1.0
author: CTRL contributors
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [codex, app-server, orchestration, threads, workers, control]
    related_skills: [hermes-codex-coordination, dragonslayer]
---

# CTRL

## Overview

CTRL is the local operator interface for persistent Codex App Server threads and live blocker or gate surfacing. Its thread commands connect directly to the managed App Server Unix socket and map memorable lane names to persistent Codex thread IDs. `ctrl announce` is a local, human-first command that does not use the socket or registry.

The current release is deliberately narrow. It provides live announcements, health discovery, thread listing, compact status, full thread reads, persistent thread creation, and start-or-steer message delivery. It does not provide durable announcement storage, work-item admission, leases, heartbeats, interruption, verification records, or automated completion handling. Never infer those capabilities from the broader architecture direction.

CTRL is a client, not another App Server daemon. Installing or invoking it does not replace, restart, stop, or reconfigure the managed daemon. Read-only commands can be safely tested against a working daemon. Commands that create a thread or deliver a message change App Server state and must follow the ownership and worktree rules in this skill.

Canonical naming:

```text
Repository:      ctrl
Python package:  ctrl
CLI command:     ctrl
Skill:           ctrl
```

## When to Use

Use this skill when:

- surfacing a live `BLOCKER`, `GATE-HOLD`, or `ALL-CLEAR` in the primary operator view;
- checking whether the local managed Codex App Server is healthy;
- discovering persisted or currently loaded threads;
- inspecting the exact state of a known worker;
- creating a persistent worker in an isolated repository or worktree;
- assigning an explicit lane alias to a thread;
- sending a new turn to an idle worker;
- steering the currently active turn of an owned worker;
- validating the intended Sol model and reasoning tier on newly created workers;
- coordinating Dragonslayer-approved implementation work without making Dragonslayer execute it;
- debugging socket, registry, thread-loading, or message-delivery behavior.

Do not use CTRL:

- as the durable record of a blocker or gate decision;
- as a replacement for `codex app-server daemon` lifecycle commands;
- to send speculative work into a thread you do not own;
- to steer a thread concurrently with another controller or human operator;
- to create workers directly from unresolved Dragonslayer decisions;
- to bypass worktree isolation, branch ownership, review, publication, or deployment gates;
- as evidence of completion merely because a message was accepted;
- to claim leases, idempotency, durable work items, automatic recovery, or verification features that are not implemented in the current release.

## Required Mental Model

Keep the layers distinct:

```text
Dragonslayer
  resolves decisions and produces an approved implementation specification
        ↓ explicit human/coordinator admission
CTRL operator/coordinator
  chooses worktree, lane, model, reasoning, controller, and bounded instruction
        ↓
Codex App Server
  owns persistent threads, turns, events, and rollout history
        ↓
Codex worker
  performs work inside its assigned repository or worktree
```

Dragonslayer does not call CTRL directly in the current release. CTRL does not parse a decision map or decide whether synthesis is complete. The coordinator reads the approved artifact, chooses a bounded implementation unit, verifies that the worktree is safe, then explicitly creates or messages the worker.

The core concurrency rule is **one controller per thread**. Multiple observers can inspect a thread, and a Codex TUI can attach for human visibility, but only one controller may issue `ctrl send` operations at a time. Human takeover requires an explicit handoff; attaching a TUI does not silently transfer ownership.

## Installation Layout

Canonical source checkout:

```text
/path/to/ctrl
```

Runtime paths:

```text
Executable:       ctrl
App Server socket ~/.codex/app-server-control/app-server-control.sock
CTRL registry:    ~/.local/state/ctrl/threads.json
CTRL config root: ~/.config/ctrl/
```

The registry is a local alias map, not the authoritative App Server database. App Server thread IDs remain authoritative. Removing an alias does not delete a thread. Deleting a thread elsewhere can leave a stale alias.

Check installation before doing anything stateful:

```bash
command -v ctrl
ctrl --version
ctrl doctor
```

Expected health indicators include:

```json
{
  "ctrlVersion": "0.1.0",
  "socketReady": true,
  "appServer": {
    "status": "running"
  }
}
```

If `ctrl` is not on `PATH`, do not invent another implementation. Use the canonical checkout for diagnosis:

```bash
cd /path/to/ctrl
PYTHONPATH=src python3 -m ctrl.cli doctor
```

For complete installation and update commands, read [`references/command-reference.md`](references/command-reference.md).

## Command Safety Matrix

| Command | Mutates CTRL registry | Mutates App Server state | Starts/steers execution | Safe first probe |
|---|---:|---:|---:|---:|
| `ctrl doctor` | no | no | no | yes |
| `ctrl announce TYPE ...` | no | no | no | yes |
| `ctrl list` | no | no | no | yes |
| `ctrl status THREAD` | no | no | no | yes |
| `ctrl read THREAD` | no | no | no | yes, but output can be large |
| `ctrl spawn ...` | yes | yes, creates persistent thread | no turn by itself | no |
| `ctrl send ...` | no | yes | yes | no |

Treat `ctrl spawn` as state creation and `ctrl send` as execution authority. Neither command should be run merely to see whether CTRL works; use `doctor`, `list`, and `status` for non-disruptive validation.

## Live Announcement Workflow

Use exactly one supported type and all four fields:

```bash
ctrl announce BLOCKER \
  --what "Deploy proof is missing" \
  --needed "Verify the immutable digest" \
  --since "2026-08-02T14:30:00-07:00" \
  --owner "release coordinator"
```

Each field must be nonblank, single-line text without control characters. `BLOCKER` and `GATE-HOLD` use the default full-width banner; `ALL-CLEAR` uses one loud line. Use `--json` only for explicit machine consumption. The command never connects to App Server or reads or writes the lane registry, thread state, plandoc, callbacks, or tmux.

Follow the repetition, worker escalation, human-name verification, exactly-once all-clear, and record-ownership rules in [`references/operating-model.md`](references/operating-model.md#announcement-surfacing). Announcements make live state visible; they do not create durable state.

## Preflight Before Any Stateful Command

Complete every item:

1. Identify the exact accepted work unit or bounded operational question.
2. Confirm that execution is authorized now, rather than merely proposed or drafted.
3. Inspect the target repository and worktree with live Git state.
4. Verify that unrelated uncommitted work will not be absorbed.
5. Confirm no other worker owns the same files, branch, issue, or worktree.
6. Select one controller for the thread.
7. Decide whether this is a coordinator thread (`max`) or worker thread (`xhigh`).
8. Run `ctrl doctor` and require `socketReady: true` plus a running App Server.
9. Run `ctrl list --cwd /absolute/worktree/path` to detect an existing reusable thread.
10. Prefer resuming or messaging the owned existing thread over creating a duplicate.

Git discovery is prerequisite evidence, not bureaucracy:

```bash
git -C /absolute/worktree status --short --branch
git -C /absolute/worktree rev-parse --show-toplevel
git -C /absolute/worktree branch --show-current
```

If ownership is ambiguous, stop. CTRL currently has no durable lease service to settle the race for you.

## Read-Only Discovery Workflow

Start with the broadest cheap health check:

```bash
ctrl doctor
```

Then list recent threads:

```bash
ctrl list --limit 20
```

Filter by exact working directory when locating a worker for a known worktree:

```bash
ctrl list --cwd /path/to/example-worktrees/issue-123 --limit 20
```

List output includes:

- `threadId`: authoritative App Server identity;
- `loaded`: whether the thread is currently materialized in the daemon;
- `cwd`: configured working directory;
- `name`: server-side thread name when available;
- `status`: current compact App Server status.

A thread with `loaded: false` is not necessarily dead. Persisted threads can be unloaded and resumed later. Do not create a duplicate solely because the existing thread is not loaded.

Inspect one thread compactly:

```bash
ctrl status 019f...
```

Use a lane alias after CTRL has registered one:

```bash
ctrl status lane-worker-123
ctrl status worker-123
```

Both lane forms resolve to the same registry key because CTRL normalizes a single `lane-` prefix.

Use a full read only when compact status is insufficient:

```bash
ctrl read worker-123
```

`ctrl read` can return a large thread payload. Capture it to a restricted local file if another program must inspect it:

```bash
umask 077
ctrl read worker-123 > /tmp/ctrl-worker-123.json
```

CTRL recursively redacts credential-shaped fields and strings before printing. Redaction is defense in depth, not permission to distribute arbitrary transcripts.

## Model and Reasoning Policy

The standing policy is:

```text
Coordinator: gpt-5.6-sol / max
Worker:      gpt-5.6-sol / xhigh
Reviewer:    gpt-5.6-sol / max when the review warrants it
```

`ctrl spawn` currently defaults to `gpt-5.6-sol` and `xhigh`, making the safe common path a worker. Create a worker explicitly anyway so logs and operator intent are unambiguous:

```bash
ctrl spawn /absolute/worktree \
  --lane worker-123 \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh
```

Create a coordinator only with an explicit `max` override:

```bash
ctrl spawn /absolute/coordinator-workspace \
  --lane coordinator \
  --model gpt-5.6-sol \
  --reasoning-effort max
```

CTRL sends reasoning through the supported App Server thread configuration:

```json
{
  "config": {
    "model_reasoning_effort": "xhigh"
  }
}
```

The `thread/start` response reports `model` and `reasoningEffort`. Check those fields immediately. A command-line default or request payload alone is not proof that the daemon accepted the intended tier.

Changing the policy for a new thread does not retroactively change existing threads. Never claim an existing Max thread became XHigh because a later spawn used the new default.

## Safe Worker Creation

Only spawn into an existing directory. Prefer a dedicated issue worktree, never the broad workspace when the task is supposed to be isolated.

```bash
ctrl spawn /path/to/example-worktrees/issue-123 \
  --lane issue-123 \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh
```

A successful response resembles:

```json
{
  "cwd": "/path/to/example-worktrees/issue-123",
  "lane": "lane-issue-123",
  "model": "gpt-5.6-sol",
  "reasoningEffort": "xhigh",
  "threadId": "019f..."
}
```

Record all five fields. The thread ID is needed for independent App Server inspection; the lane is the ergonomic operator handle.

Spawning does not start a turn. This separation is intentional: creation can be inspected before execution. Run:

```bash
ctrl status issue-123
```

Then deliver one bounded instruction only after the model, effort, cwd, lane, and ownership are correct.

If `spawn` succeeds in App Server but registry persistence fails, the thread may exist without its alias. Re-run `ctrl list --cwd ...` and recover the thread ID. Do not blindly repeat `spawn`, because that creates a second persistent thread.

## Sending and Steering Work

Deliver a short message directly:

```bash
ctrl send issue-123 "Implement only the accepted parser change. Preserve unrelated work. Run the targeted and full tests. Do not merge or publish."
```

For a longer instruction, use stdin to avoid shell quoting damage:

```bash
printf '%s\n' 'Implement the accepted issue scope.

Constraints:
- Work only in the assigned worktree.
- Preserve unrelated changes.
- Do not merge, publish, deploy, or create follow-up issues.

Proof:
- Run targeted tests.
- Run the repository-required full suite.
- Report changed paths and exact command results.' | ctrl send issue-123
```

Delivery behavior is state-dependent:

- unloaded thread: CTRL calls `thread/resume`, then continues;
- active thread with an in-progress turn: CTRL calls `turn/steer` with the exact expected turn ID;
- idle thread: CTRL calls `turn/start`.

The command output tells you whether delivery was `started` or `steered` and reports the turn ID. This is receipt proof, not completion proof.

Every new turn currently uses:

```json
{
  "approvalPolicy": "never",
  "sandboxPolicy": {
    "type": "dangerFullAccess"
  }
}
```

That is the `dangerFullAccess` policy. Worktree isolation, scope locks, one-controller ownership, independent review, and publication gates are therefore mandatory. Do not use CTRL to send untrusted or open-ended instructions into a valuable checkout.

Never send the same instruction twice because the worker appears quiet. Inspect `ctrl status` or `ctrl read` first. Duplicate sends can start duplicate turns or steer the same active turn with repeated work.

## Dragonslayer Handoff

Dragonslayer remains planning-only. A safe handoff has four boundaries:

1. **Decision completion:** unresolved decisions are closed or explicitly deferred.
2. **Synthesis:** the implementation specification is coherent and names constraints and acceptance.
3. **Admission:** a human or authorized coordinator chooses one implementation unit for execution.
4. **Execution:** CTRL starts or messages the corresponding worker.

Do not translate an entire decision map into one giant worker prompt. Select the smallest independently verifiable implementation unit. Preserve decision IDs or ticket IDs in the instruction so the worker can trace scope back to the approved artifact.

CTRL 0.1.0 has no artifact parser and no admission command. Admission is an explicit coordinator action outside the CLI. The skill must never pretend otherwise.

## Thread Ownership and Human Visibility

A TUI attached to the same App Server thread is an interactive controller, not a passive dashboard. Use the official remote-resume form for deliberate visibility or takeover:

```bash
codex --remote unix://$HOME/.codex/app-server-control/app-server-control.sock resume 019f...
```

Before attaching, decide who controls the thread:

- **CTRL-controlled:** TUI observes; human does not submit input.
- **Human-controlled:** coordinator stops sending through CTRL until control is returned.

Do not allow CTRL and a human TUI to steer one live turn concurrently. App Server supports multiple clients and multiple threads; co-control semantics for one active thread can still race.

## Completion and Verification

CTRL currently reports transport and App Server state. It does not verify repository claims automatically.

After the worker reports completion:

1. Read the thread status and final response.
2. Inspect the assigned worktree directly.
3. Verify the changed paths match scope.
4. Run required tests independently when practical.
5. Check Git status, branch, and commits.
6. Confirm no merge, publication, deployment, or issue mutation occurred without authority.
7. Treat worker callbacks and prose as self-reports until artifacts prove them.

Useful readback:

```bash
ctrl status issue-123
ctrl read issue-123 > /tmp/issue-123-thread.json
git -C /absolute/worktree status --short --branch
git -C /absolute/worktree diff --stat
git -C /absolute/worktree log -1 --oneline
```

Do not declare a task complete from `delivery: started`, `delivery: steered`, an idle status, or a final agent message alone.

## Recovery Rules

### Socket missing

Run:

```bash
ctrl doctor
codex app-server daemon version
```

If the managed daemon is stopped, use its official lifecycle command rather than starting an ad hoc foreground server:

```bash
codex app-server daemon start
ctrl doctor
```

### Lane missing

The default registry is `~/.local/state/ctrl/threads.json`. Search App Server by cwd:

```bash
ctrl list --cwd /absolute/worktree --limit 50
```

Use the raw thread ID for immediate inspection. Repair aliases deliberately; do not overwrite one lane with an unrelated thread.

### Persisted thread is unloaded

Unloaded is normal. `ctrl send` automatically resumes before starting a turn. For read-only inspection, first try `ctrl status` or `ctrl read`; do not create a replacement thread merely to materialize it.

### Active but no steerable turn

Stop and inspect the full thread. Do not force a second message or create a duplicate worker. The daemon may be between status transitions, or another client may control the thread.

### Reasoning tier is wrong

Do not change an existing worker in place unless the protocol and policy explicitly support it. Stop assigning new work, retain the thread for diagnosis, and create a correctly configured replacement only after confirming that duplication is safe.

See [`references/troubleshooting.md`](references/troubleshooting.md) for detailed failure paths.

## Current Capability Boundary

Implemented now:

- managed socket connection and WebSocket JSON-RPC;
- daemon health readback;
- persisted thread listing;
- compact and full thread reads;
- local lane aliases;
- worker/coordinator model and reasoning selection at thread creation;
- unloaded-thread resume during delivery;
- active-turn steering versus idle-turn start;
- recursive credential-shaped redaction;
- JSON output suitable for scripts.

Not implemented now:

- Dragonslayer artifact ingestion;
- work-item database;
- controller leases or heartbeats;
- operation idempotency keys;
- retry/backoff policy;
- event subscription daemon;
- automated completion detection;
- interrupt/stop command;
- verification evidence records;
- fleet deployment manifest;
- destructive thread deletion.

When a requested operation needs a missing capability, say so. Use the official Codex interface or a bounded manual procedure rather than fabricating a CTRL command.

## Common Pitfalls

1. **Using `spawn` as a health test.** It creates persistent state. Use `ctrl doctor` and `ctrl list`.
2. **Assuming aliases are global truth.** They are local registry entries; thread IDs are authoritative.
3. **Creating a duplicate for an unloaded thread.** Unloaded threads are resumable.
4. **Sending before worktree inspection.** `dangerFullAccess` makes isolation essential.
5. **Two controllers steering one thread.** Assign one controller and make takeover explicit.
6. **Treating message receipt as completion.** Verify the repository and tests independently.
7. **Assuming worker defaults apply to coordinators.** Coordinators require explicit `max`.
8. **Changing existing threads by changing spawn defaults.** Defaults affect only new threads.
9. **Using unresolved Dragonslayer output as execution scope.** Require synthesis and explicit admission.
10. **Starting a second App Server.** CTRL talks to the managed daemon; use official daemon lifecycle commands.
11. **Publishing full thread payloads.** Redaction reduces risk but does not make transcripts public.
12. **Inventing future commands.** Check `ctrl --help`; the current interface is intentionally small.

## Verification Checklist

Before read-only inspection:

- [ ] `command -v ctrl` resolves to the expected installation
- [ ] `ctrl --version` reports the expected release
- [ ] `ctrl doctor` reports a running App Server and ready socket
- [ ] requested output is kept local and handled as potentially sensitive

Before spawning:

- [ ] execution is explicitly authorized
- [ ] target repository/worktree exists
- [ ] Git status and branch were inspected
- [ ] work ownership does not overlap another lane
- [ ] no reusable thread already exists for the cwd
- [ ] lane name is unique and meaningful
- [ ] model is `gpt-5.6-sol`
- [ ] worker uses `xhigh`, coordinator uses `max`
- [ ] one controller is named for the thread

After spawning:

- [ ] response contains thread ID, lane, cwd, model, and reasoning effort
- [ ] returned model and effort match the request
- [ ] `ctrl status LANE` resolves successfully
- [ ] no message has been sent before inspection

Before sending:

- [ ] instruction is bounded and references accepted scope
- [ ] non-goals and authority limits are explicit
- [ ] full-access execution is appropriate for this worktree
- [ ] another controller or TUI is not actively steering the thread
- [ ] duplicate delivery has been ruled out

After completion:

- [ ] status and full read were inspected
- [ ] changed files and Git state were independently checked
- [ ] required tests were rerun or their exact evidence verified
- [ ] completion claims match artifacts
- [ ] no unauthorized merge, publish, deploy, or issue mutation occurred

## References

- [`references/command-reference.md`](references/command-reference.md) — installation, global options, exact commands, JSON fields, and scripting patterns
- [`references/operating-model.md`](references/operating-model.md) — coordinator/worker topology, ownership, Dragonslayer handoff, lifecycle, and future boundary
- [`references/troubleshooting.md`](references/troubleshooting.md) — socket, registry, unloaded-thread, duplicate-delivery, reasoning, and recovery diagnosis
