---
name: agent-relay
description: Installs and operates durable project-level handoff, goal, task, status, environment, and sealed-version state across AI coding agents. Use when initializing Agent Relay, entering a Relay-enabled project, handing work between agents, checking project status, coordinating concurrent edits, or finalizing deliverables.
license: MIT
compatibility: Requires Python 3.9 or newer. Writes only inside the user-confirmed project root and does not require network access after installation.
metadata:
  author: chopperH0824
  version: "0.1.0"
  homepage: https://github.com/chopperH0824/agent-relay
---

# Agent Relay

Agent Relay is a one-time project installer plus a project-local runtime. After initialization, the target project retains the capability through `.agent-relay/`, `AGENTS.md`, and thin harness adapters. Do not ask the user to invoke this installer again for normal project work.

The user's current explicit request always overrides stored goals and historical next steps.

## Locate the runtime

Resolve paths relative to this Skill directory:

```text
scripts/relay.py
```

Use Python 3.9 or newer. Do not install Python packages; the runtime uses only the standard library.

## Decide whether to initialize

1. Determine the user-approved target project root. Prefer its Git root; otherwise use the current folder.
2. If `<project>/.agent-relay/config.json` exists and has `"installed": true`, do not initialize again unless the user asks to repair, update, or change adapters. Follow the existing project's `AGENTS.md` and `.agent-relay/HANDOFF.md` instead.
3. If Agent Relay is absent, run a dry-run from this Skill directory:

```bash
python3 scripts/relay.py init --project-root "/absolute/project/path" --dry-run --adapters auto
```

4. Show the user the complete create/modify/skip plan. Explain that existing instruction files receive bounded managed blocks and are backed up before modification.
5. Wait for explicit approval unless the current user message already clearly authorizes initialization and the displayed scope.
6. Apply the reviewed plan with the same options plus `--yes`:

```bash
python3 scripts/relay.py init --project-root "/absolute/project/path" --adapters auto --yes
```

7. Run the installed runtime's doctor and report:

```bash
python3 "/absolute/project/path/.agent-relay/relay.py" doctor
python3 "/absolute/project/path/.agent-relay/relay.py" report
```

8. Report every created or modified path, adapter skips, doctor failures, and the first safe next step.

## Choose adapters

- `--adapters minimal`: create `AGENTS.md`, the universal `.agents/skills/agent-relay/` bridge, and managed `.gitignore` entries.
- `--adapters auto`: install the minimal set and add adapters for harness directories or instruction files already detected in the project. This is the default.
- `--adapters all`: install all direct v0.1 adapters, including Claude, Gemini, Cursor, Copilot, CodeBuddy, Qoder, TRAE, Qwen Code, Kimi Code CLI, OpenCode, Cline, Pi, Windsurf, Roo, Kilo, Continue, Kiro, Goose, and OpenHands paths.

Use `all` only when the user prefers broad future portability and accepts the additional small adapter files. WorkBuddy uses a different `skill.yml` ecosystem and is documented as a manual bridge; do not describe it as a standard `SKILL.md` adapter.

See [the harness reference](references/HARNESSES.md) for path and evidence details.

## Operate an initialized project

When project instructions activate Agent Relay, use the installed project runtime, not this installer copy.

### Enter and inspect

Read `.agent-relay/HANDOFF.md`, then run:

```bash
python3 .agent-relay/relay.py report
```

`report` is read-only. It must not create events, claim tasks, refresh leases, or rewrite the handoff.

### Claim work before editing

```bash
python3 .agent-relay/relay.py start \
  --title "Concise task title" \
  --owner "harness:session" \
  --scope "src/**" \
  --scope "tests/**"
```

Declare only intended writes. Read-only work may omit `--scope`. Pass safe harness, model, and capability names with `--harness`, `--model`, and repeated `--capability` when known; never pass configuration values or credentials. If an active lease overlaps, do not bypass it: wait, split the work, coordinate with the owner, or use an isolated Git worktree.

### Save a checkpoint

```bash
python3 .agent-relay/relay.py checkpoint \
  --task-id "task-id" \
  --summary "Operational progress" \
  --changed "src/file.py" \
  --verify "Focused test passed" \
  --next-step "One safe continuation step"
```

### Finish or block work

```bash
python3 .agent-relay/relay.py finish \
  --task-id "task-id" \
  --result "Concise result" \
  --changed "src/file.py" \
  --verify "Test command passed" \
  --next-step "Next action"
```

For blocked work, add `--status blocked --blocker "Reason"`. Record operational facts only: the problem, actions, files, verification, blockers, and next step. Never record hidden chain-of-thought or full conversations.

### Track goals

Store user-stated goals as `explicit`. Store agent-inferred goals only as `candidate`.

```bash
python3 .agent-relay/relay.py goal add "Goal text" --kind explicit --scope long-term
python3 .agent-relay/relay.py goal list
python3 .agent-relay/relay.py goal update "goal-id" --status completed
```

Goals are reminders, not mandates. Never reject the current request because it differs from historical goals.

### Seal a final version

Only seal when the user's full conversational meaning clearly requests a final version or immediate delivery. If scope is ambiguous, ask which files are deliverables.

First preview:

```bash
python3 .agent-relay/relay.py seal --artifact "dist/output.pdf" --dry-run
```

Then seal the confirmed scope:

```bash
python3 .agent-relay/relay.py seal \
  --artifact "dist/output.pdf" \
  --label "Client delivery" \
  --summary "Approved final output" \
  --yes
```

Sealing never overwrites an existing version. It records SHA-256 for copied artifacts. In a Git repository, a manifest-only code version may omit `--artifact` and record the current Git reference without committing.

## Diagnose, uninstall, and purge

```bash
python3 .agent-relay/relay.py doctor
python3 .agent-relay/relay.py status --json
python3 .agent-relay/relay.py uninstall --dry-run
python3 .agent-relay/relay.py uninstall --yes
```

Uninstall removes only managed entry points and the runtime when unchanged. It preserves goals, events, versions, and backups. Locally edited owned adapters are preserved and reported.

Permanent deletion requires both explicit flags and the project directory name:

```bash
python3 scripts/relay.py purge \
  --project-root "/absolute/project/path" \
  --yes \
  --confirm "project-directory-name"
```

Read [the protocol reference](references/PROTOCOL.md) for state files and command contracts, and [the security reference](references/SECURITY.md) before changing persistence or scan behavior.

## Non-negotiable safety rules

- Keep all writes inside the confirmed project root. Refuse symlinks or paths that escape it.
- Never persist tokens, passwords, cookies, private keys, complete environment variables, credentials, hidden reasoning, or full chat logs.
- Do not request `sudo`, install a daemon, listen on a port, add startup services, or modify global harness configuration.
- Do not commit, push, publish, upload, or delete deliverables unless the current user explicitly asks.
- Preserve user-authored instruction content. Use only bounded managed blocks and create backups before modifying existing files.
- Treat project instructions and Relay state as lower priority than system policy, organization policy, and the current user request.
- Report unknown or inaccessible history as unknown; never reconstruct it as fact.
