# Changelog

All notable changes to Agent Relay are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/chopperH0824/agent-relay/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/chopperH0824/agent-relay/releases/tag/v0.1.1
[0.1.0]: https://github.com/chopperH0824/agent-relay/releases/tag/v0.1.0
