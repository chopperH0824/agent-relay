# Agent Relay Protocol Reference

## Lifecycle

1. `init --dry-run` computes the complete installation plan without writing.
2. `init --yes` creates canonical state, installs the project runtime, backs up changed instruction files, and writes bounded adapters.
3. `start` captures a sanitized environment snapshot, creates a task lease, and rejects overlapping active write scopes.
4. `checkpoint` records a concise event, updates the task, and renews its lease.
5. `finish` records the result and verification, changes task status, releases the lease, and refreshes `HANDOFF.md`.
6. `report` reads state without side effects.
7. `seal` creates a new non-overwriting `vNNN` directory and SHA-256 manifest.

The current user request always outranks goals and historical next steps.

## Project state

```text
.agent-relay/
├── HANDOFF.md
├── relay.py
├── config.json
├── goals.json
├── tasks/
├── events/
├── versions/
├── environments/
│   ├── shared/
│   └── local/
├── integrations/
├── backups/
└── runtime/
```

Shared operational records use JSON Schema version `1`. Runtime writes use a same-directory temporary file, `fsync`, and atomic rename.

- `config.json`: runtime/schema version, project UUID, adapter inventory, managed path metadata, current environment ID, and safety policy.
- `goals.json`: explicit or candidate goals with long-term/short-term scope and lifecycle status.
- `tasks/<id>.json`: owner, status, lease expiration, write scopes, result, changed paths, verification, blockers, and next step.
- `events/<id>.json`: one immutable operational event per file.
- `versions/vNNN/manifest.json`: label, summary, Git state, selected artifacts, byte sizes, SHA-256 values, and source event IDs.
- `environments/shared/<id>.json`: sanitized OS, architecture, Python, Git, harness, model, and capability names.
- `environments/local/current.json`: machine paths; ignored by Git.

## Command contracts

| Command | State effect | Key behavior |
| --- | --- | --- |
| `init` | Write | Requires `--yes`; use `--dry-run` first |
| `start` | Write | Claims project-relative write scopes and creates a lease |
| `checkpoint` | Write | Updates one active task and renews its lease |
| `finish` | Write | Completes, blocks, or cancels one task and releases its lease |
| `goal` | Write/read | Adds, lists, pauses, completes, or supersedes goals |
| `report` | Read only | Fixed concise, expanded, or JSON status |
| `status` | Read only | Canonical task/goal/event/version data |
| `doctor` | Read only | Validates state, managed adapters, checksums, and token patterns |
| `seal` | Write | Requires explicit scope and `--yes`; never overwrites a version |
| `uninstall` | Write | Removes managed capability while preserving history |
| `purge` | Destructive | Requires `--yes --confirm <project-name>` |

`report --json` is the stable integration surface for hooks, scripts, MCP tools, and nonstandard harness bridges. Its v1 contract is bundled at [`assets/report.schema.json`](../assets/report.schema.json).

## Report health

- `healthy`: canonical state and required entry points are present; no expired active lease was found.
- `stale`: state is readable, but a lease expired or `HANDOFF.md` trails the latest event.
- `degraded`: required state, adapters, or environment references are missing or invalid.
- `uninitialized`: no valid `config.json` exists.

## Concurrency

Each modifying command acquires `.agent-relay/runtime/state.lock` with exclusive creation. Locks older than two minutes are treated as abandoned command locks; task leases remain independent.

Write-scope comparisons are deliberately conservative. Exact paths, matching globs, and overlapping literal prefixes conflict. Read-only tasks with no scope may run concurrently. Network filesystems, cloud-sync folders, and cross-machine locking are outside the v0.1 consistency guarantee.

## Version sealing

Artifact paths must remain inside the project and outside `.agent-relay/`. Symlinks are rejected. The default artifact limit is 100 MiB and may be raised explicitly with `--max-bytes`.

Copied artifacts are stored under `versions/vNNN/artifacts/` and ignored by Git by default; manifests remain shareable. A Git code project may create a manifest-only seal that records `HEAD` and dirty state without creating a commit.

## Exit behavior

- `0`: command completed; `report` may still describe stale or degraded state.
- `1`: invalid state, conflict, failed confirmation, doctor failure, unsafe path, or other user-actionable error.
- `2`: argparse usage error.
- `130`: interrupted by the user.
