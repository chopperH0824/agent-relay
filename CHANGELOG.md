# Changelog

All notable changes to Agent Relay are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Made a single one-line request for the agent to install and enable Agent Relay the primary Quick Start, with the manual `npx` command immediately after it.
- Updated Skill discovery and continuation rules so an agent that just installed the Skill proceeds into project setup without asking the user to repeat the request.
- Reframed initialization, daily work, status, goals, coordination, sealing, and health checks as natural-language requests; CLI details now live in an Agent/automation reference.
- Added natural-language safe uninstall and complete project-restore flows, including history deletion, installer-Skill removal, modified-adapter preservation, and scope warnings.

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

[Unreleased]: https://github.com/chopperH0824/agent-relay/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/chopperH0824/agent-relay/releases/tag/v0.1.0
