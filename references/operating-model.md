# CTRL Operating Model

## Roles

### Human

Owns authorization, priorities, publication, deployment, destructive actions, and explicit takeover decisions.

### Dragonslayer

Maps decisions and synthesizes implementation intent. It neither controls App Server nor owns execution state.

### Coordinator

Selects admitted work, checks repository state, creates isolated worktrees, assigns one controller, chooses worker model/reasoning, sends bounded instructions, and verifies outcomes.

### CTRL

Provides the deterministic local interface to App Server and owns live announcement surfacing. It translates operator commands into protocol calls, records ergonomic lane aliases, and keeps restart-safe current blocker state. It does not supply judgment or authorization.

### Codex App Server

Owns persistent threads and turns. One daemon can host many threads. Thread persistence and loaded state are different concepts.

### Worker

Implements one bounded unit in one owned worktree. It cannot expand scope, merge, publish, or deploy without separate authority.

## Lifecycle

```text
proposed
  → decision-resolved
  → synthesis-complete
  → admitted
  → worktree-ready
  → thread-created
  → turn-started
  → active
  → worker-reported
  → independently-verified
  → human-controlled integration/release
```

CTRL 0.1.0 directly represents only thread creation and turn delivery. The coordinator must maintain the surrounding lifecycle explicitly.

## Ownership Invariants

1. One controller per thread.
2. One primary work item per worker thread.
3. One worker owns a worktree during an active mutation window.
4. No overlapping file ownership across concurrent workers unless coordination is explicit.
5. A TUI attachment does not imply control transfer.
6. Message acceptance does not imply successful execution.
7. Worker completion prose does not imply verification.
8. Merge, publish, deploy, outbound communication, and destructive operations remain separate authority gates.

## Model Policy

Use Sol for meaningful reasoning roles:

```text
coordination/planning  gpt-5.6-sol max
implementation worker gpt-5.6-sol xhigh
high-stakes review    gpt-5.6-sol max
```

Apply policy when creating new threads. Existing threads retain their original effective configuration unless changed through a separately supported and verified operation.

## Lane Naming

Good lane aliases communicate stable ownership:

```text
issue-123
parser-migration
release-audit
project-coordinator
```

Avoid aliases tied to a person, transient pane number, or vague status:

```text
worker
codex2
test
new
```

CTRL stores aliases with one `lane-` prefix. Both `issue-123` and `lane-issue-123` resolve the same way at the command line.

## Announcement Protocol

`ctrl block`, `ctrl clear`, and `ctrl blockers` implement the ANNOUNCE primitive. A `blocker` record renders as `BLOCKER`, a `hold` record renders as `GATE-HOLD`, and clearing either emits `ALL-CLEAR`. Every announcement carries `what`, `needed`, `since`, and `owner`; the normalized lane is the owner identity, while `who` is only the attention target.

The operating rules are:

1. The coordinator renders every active `BLOCKER` or `GATE-HOLD` in the primary operator view and repeats it at the end of every coordinator turn until clear.
2. All worker blockers escalate to the coordinator; worker-thread visibility is not live surfacing.
3. Before amplification, independently verify a blocker that names a human.
4. Emit `ALL-CLEAR` exactly once when the corresponding current state is cleared.
5. `blockers.json` is current live state only; plandoc owns durable blocker history.

The live-state file exists so blockers survive session restarts and remain queryable. It is not a historical ledger: cleared entries are removed, and durable evidence or decision history belongs in plandoc. Attention commands do not use the App Server socket, thread registry, callbacks, plandoc writers, or tmux automation.

## Coordinator Loop

1. Inspect accepted planning artifact and live repository state.
2. Select one smallest independently verifiable unit.
3. Establish a dedicated branch/worktree.
4. Confirm no existing thread should be reused.
5. Spawn a worker with explicit model and reasoning.
6. Verify returned cwd/model/reasoning/thread ID.
7. Send one bounded instruction.
8. Observe through read-only status/read operations.
9. Accept one completion report.
10. Independently inspect diffs, tests, branch, and commit state.
11. Escalate merge/release decisions to their owner.
12. Keep the thread for continuation when the work stream remains active.

## Observer Versus Controller

Several clients may inspect one App Server daemon. This does not make concurrent steering safe. Track control as an explicit social and eventually durable software lease:

```text
controller: coordinator-A
thread: 019f...
work item: issue-123
worktree: /.../issue-123
acquired: timestamp
handoff: none
```

Until CTRL implements leases, store this in the coordinator's authoritative work ledger and check it before every send.

## Failure Containment

CTRL intentionally leaves the existing managed daemon untouched. A client crash closes its socket connection but should not terminate App Server or other threads. A bad spawn can create an unwanted persistent thread, and a bad send can execute broad work with full filesystem access; these are the primary current hazards.

Use separate state roots during experiments:

```bash
ctrl --registry /tmp/ctrl-smoke-registry.json doctor
ctrl --registry /tmp/ctrl-smoke-registry.json list --limit 5
```

A custom registry does not isolate App Server itself. Any spawn still creates a real server thread.

## Future Boundary

The coherent future system can add these inside CTRL without changing Dragonslayer:

- SQLite work items and operations;
- controller leases and heartbeats;
- idempotency keys for stateful operations;
- event-driven completion tracking;
- bounded retry and recovery;
- verification evidence;
- fleet revision and hash readback;
- optional Dragonslayer artifact import after explicit admission.

Those additions belong behind the same `ctrl` interface. They must be introduced with migrations, tests, and real daemon proof. Until shipped, current commands remain the complete authority surface.
