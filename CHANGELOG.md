# Changelog

All notable changes to Agent Relay are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-09

### Added

- Previewable Schema `1` → `2` migration via `migrate --dry-run` / `migrate --yes`. Read-only commands keep working on schema `1` and mark `migration_required`; writes require the migration. Migration backs up `config.json` and `HANDOFF.md`, sets only the schema markers in `config.json` and `goals.json`, records a `migrations` entry and a `schema-migrated` event, and is idempotent.
- Opt-in lifecycle hooks (`hooks status|enable|disable`, `hook <event>`) for `before-write`, `checkpoint`, `task-finish`, `session-start`, and `session-end`. Hooks are disabled by default, never edit harness configuration, accept only documented fields from bounded JSON on stdin (64 KiB cap), and are rejected before any write otherwise.
- Opt-in cross-worktree coordination (`worktree status|enable|disable`). The registry lives in the common Git directory (`agent-relay/coordination.json` plus a sibling lock) so Git worktree cleanup cannot discard live claims; each worktree must enable it separately.
- Report fields `state_schema_version`, `migration_required`, `hooks_enabled`, and a `coordination` summary of mode, registered worktrees, and active claims; `doctor` adds a coordination check.
- Regression tests for migration, hook validation, worktree conflicts, registry tampering, and read-only behavior while coordinated.

### Changed

- `start` and `checkpoint` pre-register shared claims before the local write; `finish` releases the local lease before the shared claim so interruption only over-reserves.
- Config state now carries `hooks`, `coordination`, and a migration log; a future schema is refused rather than interpreted.
- Uninstall leaves worktree coordination first and refuses to proceed when active claims would leak to other worktrees.

### Fixed

- State locks record an identity, are removed only by their owner, and are reclaimed after the two-minute staleness window only when the recorded PID is no longer running; an unexpected symlink lock is refused.
- `init` on schema `1` no longer ignores the migration flag before it is computed, and no longer silently replaces a missing `goals.json` during a refresh.
- Task file paths and working-tree member paths are validated through symlink-checked resolution.
- CLI errors redact secret-looking substrings and report filesystem errors as user-actionable failures instead of tracebacks.

## [0.1.1] - 2026-11-09

### Fixed

- Blocked and cancelled tasks no longer appear as the last completed result; reports and handoffs retain blocked work and completion caveats.
- Goal summaries select the most recently updated active explicit goal, with stable insertion-order ties and no implicit promotion of candidates.
- Doctor warns about expired active leases and unrecorded or edited runtimes.
- Reinitialization refreshes unchanged owned bridges, preserves ownership metadata, and refuses unknown runtime edits before writing.
- Safe uninstall preserves locally edited runtimes as well as adapters.

### Added

- Latest-seal artifact comparison for Git and non-Git projects, with explicit coverage, bounded reads, and separate missing/unsafe/unknown results.
- Runtime SHA-256 ownership tracking and pre-upgrade backups of the runtime, config, handoff, and changed adapters.
- A read-only fleet helper for approved project paths and immediate-child discovery, using trusted installer code without executing project-local scripts.
- Regression tests for reporting semantics, upgrade protection, symlink containment, and fleet immutability.

### Changed

- Made a single one-line request for the agent to install and enable Agent Relay the primary Quick Start, with the manual `npx` command immediately after it.
- Updated Skill discovery and continuation rules so an agent that just installed the Skill proceeds into project setup without asking the user to repeat the request.
- Reframed initialization, daily work, status, goals, coordination, sealing, and health checks as natural-language requests; CLI details now live in an Agent/automation reference.
- Added natural-language safe uninstall and complete project-restore flows, including history deletion, installer-Skill removal, modified-adapter preservation, and scope warnings.
- Clarified project opt-outs, referenced decision/freeze evidence, expired-task replacement, and the difference between Relay health and verified delivery.
- Kept Schema 1 with additive report fields; existing histories need no migration and project runtimes require an explicit refresh.

## [0.1.0] - 2026-08-28

### Added

- Agent Skills-compliant installer at `skills/agent-relay/SKILL.md`.
- Dependency-free Python 3.9+ project runtime.
- Idempotent initialization with dry-run, bounded managed blocks, backups, atomic writes, and three adapter modes.
- Durable goals, one-file-per-task leases, conservative write-scope conflict detection, checkpoints, finish records, and generated handoff summaries.
- Side-effect-free concise, full, and JSON status reports with a bundled JSON Schema.
- Sanitized shared/local environment snapshots and common secret redaction.
- Non-overwriting `vNNN` version sealing with artifact copies, Git metadata, SHA-256 manifests, and tamper checks.
- Doctor, safe uninstall, and explicitly confirmed purge commands.
- Direct project adapters for standard Agent Skills hosts plus Claude, Gemini, Cursor, Copilot, Qoder, TRAE, CodeBuddy, Qwen Code, Kimi Code CLI, OpenCode, Cline, Pi, Windsurf, Roo, Kilo, Continue, Kiro, Goose, and OpenHands paths.
- Manual WorkBuddy bridge guidance without inventing an undocumented `skill.yml` schema.
- MIT license, CI matrix, unit/integration tests, bilingual documentation, demo, and social preview assets.

[Unreleased]: https://github.com/chopperH0824/agent-relay/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/chopperH0824/agent-relay/releases/tag/v0.2.0
[0.1.1]: https://github.com/chopperH0824/agent-relay/releases/tag/v0.1.1
[0.1.0]: https://github.com/chopperH0824/agent-relay/releases/tag/v0.1.0
