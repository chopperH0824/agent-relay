# Harness Adapter Reference

Agent Relay keeps all mutable state in `.agent-relay/`. Harness files are thin entry points and never hold independent goals, tasks, or history.

## Adapter modes

| Mode | Installed surface |
| --- | --- |
| `minimal` | `AGENTS.md`, `.agents/skills/agent-relay/SKILL.md`, managed `.gitignore` entries |
| `auto` | Minimal plus adapters whose harness directory or instruction file already exists |
| `all` | Minimal plus every direct adapter listed below |

## Direct v0.1 adapters

| Harness family | Project entry |
| --- | --- |
| Codex, Cursor, Copilot, Gemini CLI, Amp, Kimi Code CLI and other shared hosts | `.agents/skills/agent-relay/SKILL.md` and `AGENTS.md` |
| Claude Code | managed `CLAUDE.md` import plus the universal bridge |
| Gemini CLI | managed `GEMINI.md` import plus the universal bridge |
| Cursor | `.cursor/rules/agent-relay.mdc` plus standard entries |
| GitHub Copilot | managed `.github/copilot-instructions.md` plus standard entries |
| Qoder / Qoder CN | `.qoder/skills/agent-relay/SKILL.md` and `AGENTS.md` |
| TRAE Code / Trae CN / TraeWork | `.trae/skills/agent-relay/SKILL.md` and `AGENTS.md` |
| CodeBuddy | managed `CODEBUDDY.md` and `.codebuddy/skills/agent-relay/SKILL.md` |
| Qwen Code | `.qwen/skills/agent-relay/SKILL.md` |
| Kimi Code CLI | `.kimi/skills/agent-relay/SKILL.md` plus universal bridge |
| OpenCode | `.opencode/skills/agent-relay/SKILL.md` plus `AGENTS.md` |
| Cline | `.cline/skills/agent-relay/SKILL.md` plus `AGENTS.md` |
| Pi | `.pi/skills/agent-relay/SKILL.md` plus universal bridge |
| Windsurf | `.windsurf/skills/agent-relay/SKILL.md` plus `AGENTS.md` |
| Roo Code | `.roo/skills/agent-relay/SKILL.md` plus `AGENTS.md` |
| Kilo Code | `.kilocode/skills/agent-relay/SKILL.md` plus `AGENTS.md` |
| Continue | `.continue/skills/agent-relay/SKILL.md` |
| Kiro CLI | `.kiro/skills/agent-relay/SKILL.md` |
| Goose | `.goose/skills/agent-relay/SKILL.md` |
| OpenHands | `.openhands/skills/agent-relay/SKILL.md` |

An installed path proves only that the adapter was generated. `doctor` verifies local file integrity; it cannot prove that a closed-source harness loaded the file in a live session.

## WorkBuddy bridge

Tencent WorkBuddy documents a custom Skill package built around `skill.yml`, implementation files, and a README. Its public guide does not provide a stable field-level `skill.yml` schema. Agent Relay v0.1 therefore does not generate an unverified package.

Use this safe manual bridge pattern instead:

1. Authorize only the intended project folder in WorkBuddy.
2. Ask WorkBuddy to create a custom Skill that invokes `python3 .agent-relay/relay.py report --json` read-only.
3. Keep task mutation and version sealing behind explicit user confirmation.
4. Record whether the task runs locally or in a cloud environment; cloud execution may not have the project runtime or authorized folder.
5. Never expose project-external personal folders or credential files.

## Manual-only products

For harnesses without a verified project instruction or Agent Skills entry, provide this handoff prompt without claiming automatic activation:

```text
Before working, read <project>/.agent-relay/HANDOFF.md and run
python3 <project>/.agent-relay/relay.py report.
The current user request has priority. Use start before writes and finish afterward.
Do not store secrets, full conversations, or hidden reasoning.
```

Baidu Comate, CodeGeeX, CodeArts Snap, Fitten Code, and iFlyCode remain manual-only until a stable official loading interface is verified.

## Installation ecosystems

The repository layout `skills/agent-relay/SKILL.md` is discoverable by:

```bash
npx skills add chopperH0824/agent-relay --skill agent-relay
gh skill install chopperH0824/agent-relay agent-relay
```

`gh skill` requires GitHub CLI 2.90.0 or newer and is currently a preview feature. Installation support from a third-party CLI does not itself prove runtime behavior in every harness.

## Compatibility sources

Evidence reviewed for v0.1.0:

- [Agent Skills Specification](https://agentskills.io/specification)
- [GitHub CLI `gh skill`](https://cli.github.com/manual/gh_skill) and [`gh skill install`](https://cli.github.com/manual/gh_skill_install)
- [`npx skills`](https://github.com/vercel-labs/skills)
- [Qoder Rules](https://docs.qoder.com/user-guide/rules), [Qoder Skills](https://docs.qoder.com/extensions/skills), and [Qoder CN Skills](https://help.aliyun.com/zh/lingma/qoder-cn/user-guide/skills)
- [TRAE Code Skills](https://docs.trae.ai/ide/skills), [TRAE Code Rules](https://docs.trae.ai/ide/rules?ref), and [TraeWork Skills](https://docs.trae.ai/solo/skills?_lang)
- [CodeBuddy Skills](https://www.codebuddy.ai/docs/ide/Features/Skills), [CodeBuddy persistent instructions](https://www.codebuddy.ai/docs/cli/best-practices), and [WorkBuddy Custom Skills](https://www.workbuddy.ai/docs/workbuddy/From-Beginner-to-Expert-Guide/Practice-Cases/Create-Skills)
- [Qwen Code Skills](https://qwenlm.github.io/qwen-code-docs/en/users/features/skills/) and [Kimi Code CLI Skills](https://moonshotai.github.io/kimi-cli/en/customization/skills.html)
- [Pi Skills](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md)
