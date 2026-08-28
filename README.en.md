<p align="center">
  <a href="./README.md">简体中文</a> · <strong>English</strong>
</p>

<h1 align="center">Agent Relay</h1>

<p align="center">
  Install once. Keep durable project handoffs, instant status reports, version history, and multi-agent coordination inside the project.
</p>

<p align="center">
  <img alt="Status: specification" src="https://img.shields.io/badge/status-specification-f59e0b">
  <img alt="Agent Skills standard" src="https://img.shields.io/badge/standard-Agent%20Skills-2563eb">
  <img alt="Runtime: planned" src="https://img.shields.io/badge/runtime-planned-lightgrey">
</p>

> [!IMPORTANT]
> **Current status: specification phase.** This repository currently contains the complete design and visual prototype, but it does not yet contain an executable `SKILL.md`, installer, or Relay CLI. The installation commands and runtime behavior below describe the planned `v0.1` interface. Do not use them in production until a working release is published.

Agent Relay is not meant to be a Skill that users must remember to invoke in every conversation. The Skill acts as a **one-time project installer**. Its first run places project-level instruction adapters, a lightweight runtime, and handoff state inside the target project. Future agents discover the protocol from the project itself.

- **The Skill performs installation.**
- **The project retains the capability.**
- **After initialization, users work normally without invoking the Skill again.**

[Visual architecture](./docs/agent-relay-simple.html) · [Simplified specification](./docs/agent-relay-simple.md) · [Desktop preview](./docs/agent-relay-desktop.jpg) · [Mobile preview](./docs/agent-relay-mobile.jpg)

## Contents

- [What Agent Relay solves](#what-agent-relay-solves)
- [Five core capabilities](#five-core-capabilities)
- [How one initialization remains active](#how-one-initialization-remains-active)
- [Installation and first initialization](#installation-and-first-initialization)
- [What to do after initialization](#what-to-do-after-initialization)
- [What it does to your computer](#what-it-does-to-your-computer)
- [What it does not do](#what-it-does-not-do)
- [Project file layout](#project-file-layout)
- [Daily workflow](#daily-workflow)
- [Quick status report](#quick-status-report)
- [Goals, actions, versions, and environments](#goals-actions-versions-and-environments)
- [Multi-agent coordination](#multi-agent-coordination)
- [Harness compatibility](#harness-compatibility)
- [Privacy and security](#privacy-and-security)
- [Planned commands](#planned-commands)
- [Uninstall and recovery](#uninstall-and-recovery)
- [Limitations](#limitations)
- [FAQ](#faq)
- [Roadmap](#roadmap)

## What Agent Relay solves

A project may move between different models, desktop applications, and CLI agents. A new agent usually cannot reliably know:

- the user's long-term objective for the project;
- what the previous agent changed and what it verified;
- which version was already sent to a manager, colleague, client, or customer;
- which files another agent is currently editing;
- which model, MCP server, plugin, browser, or local tool supported a historical workflow;
- whether the current harness has equivalent capabilities.

Agent Relay maintains a small, explicit handoff layer inside the project so the next agent reads operational facts before acting on the current request.

Historical goals are reminders, not mandates. **The user's current explicit request always takes priority.**

## Five core capabilities

| Capability | Automatic behavior | Purpose |
| --- | --- | --- |
| Automatic handoff | Read `HANDOFF.md` before starting | Understand current state, active work, and the next safe step |
| Automatic record | Record the problem, actions, result, and verification at task end | Preserve enough operational context without copying full chats |
| Quick status report | Generate a fixed-format summary with `relay report` | Answer “where are we now?” without reading the event history |
| Automatic version sealing | Detect clear finalization or immediate delivery intent | Keep immutable deliverables from being overwritten by later edits |
| Automatic coordination | Claim tasks and write scopes; compare environment capabilities | Prevent concurrent edits and identify missing tools |

## How one initialization remains active

Ordinary Skills are loaded on demand and may not be selected in every session. Agent Relay's first run installs a minimal persistent layer into the project:

```mermaid
flowchart LR
    A[Install the Agent Relay Skill] --> B[Run init once in a target project]
    B --> C[Write project instruction adapters]
    C --> D[Install the project-local Relay runtime]
    D --> E[Create HANDOFF and state directories]
    E --> F[Run doctor]
    F --> G[No manual Skill invocation afterward]
```

Future sessions use project instructions that the harness loads automatically:

```mermaid
flowchart LR
    A[Agent opens the project] --> B[Load AGENTS / CLAUDE / GEMINI adapters]
    B --> C[Read HANDOFF]
    C --> D[Create or claim a task]
    D --> E[Execute the current user request]
    E --> F[Record the result and refresh handoff]
```

This is not a background daemon. Agent Relay does not continuously consume CPU or listen on a port. The agent invokes short project-local commands at session start, checkpoints, task completion, and version sealing.

## Installation and first initialization

### Current release status

The commands in this section describe the planned `v0.1` workflow. They will only work after this repository publishes a valid `SKILL.md` and installer.

### Option A: install into one project

Use this when Agent Relay is needed in a single project:

```bash
cd /path/to/your-project
npx skills add chopperH0824/agent-relay --skill agent-relay
```

`npx skills` is a third-party Agent Skills installer and is not part of Agent Relay. By default, it installs the Skill into project-level locations supported by the selected agents.

To disable that third-party CLI's own anonymous telemetry:

```bash
DO_NOT_TRACK=1 npx skills add chopperH0824/agent-relay --skill agent-relay
```

### Option B: install globally, then initialize multiple projects

```bash
DO_NOT_TRACK=1 npx skills add chopperH0824/agent-relay --skill agent-relay --global
```

A global installation only makes the installer Skill available to harnesses. Each target project still requires one explicit initialization.

### Run one initialization in the target project

Open the target project and tell the agent:

```text
Use agent-relay to initialize this project. Show a dry-run first, list every file that will be created or modified, and wait for my approval before applying it.
```

Harnesses with Skill commands may use the planned interface:

```text
/agent-relay init --dry-run
/agent-relay init
```

The initializer should:

1. confirm that the current directory or Git root is the intended project;
2. inspect existing project instructions without overwriting user content;
3. show every path it will create, modify, back up, or ignore;
4. write the project-local runtime only after approval;
5. run `doctor` to verify that adapters and state are readable;
6. create the first `HANDOFF.md`, leaving unknown goals blank.

## What to do after initialization

After a successful initialization, the user only needs to:

1. review `.agent-relay/HANDOFF.md` and correct the project summary or detected goals if needed;
2. optionally add a long-term goal, or leave it blank;
3. continue giving normal requests to any agent.

There is no need to invoke `/agent-relay` again. A new agent should automatically:

- read the handoff summary;
- check active tasks and claimed file scopes;
- record the current harness, model, and capabilities;
- complete the user's task;
- append a short action event and refresh the handoff;
- create a version copy when the user clearly finalizes or immediately sends a deliverable.

The planned reporting and health commands remain available:

```bash
python .agent-relay/relay.py report
python .agent-relay/relay.py status
python .agent-relay/relay.py doctor
```

## What it does to your computer

This section describes the intended default safe mode. All project initialization writes must stay inside the user-approved project root. User-level Skill directories are modified only when the user explicitly chooses a global Skill installation.

### 1. During Skill installation

Depending on the selected harness and scope, an Agent Skills installer may write Agent Relay to one of these locations:

| Scope | Example path | Purpose |
| --- | --- | --- |
| Project | `.agents/skills/agent-relay/`, `.claude/skills/agent-relay/`, `.cursor/skills/agent-relay/` | Make the one-time installer available in one project |
| User | `~/.agents/skills/agent-relay/`, `~/.claude/skills/agent-relay/`, `~/.codex/skills/agent-relay/` | Make the installer available across projects |

The exact path is chosen by the harness or Skill installer. Review third-party Skills, their `SKILL.md`, and scripts before installation.

### 2. Information read during project initialization

| Information | Reason | Stored verbatim? |
| --- | --- | --- |
| Current directory and Git root | Establish the installation boundary | Only the normalized project path is retained |
| Existing `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and adapter rules | Merge entry points without overwriting content | Used only to generate managed blocks |
| Git status, current branch, and latest commit ID | Record a project baseline | Necessary summary only; no automatic commit |
| OS, CPU architecture, shell, and Python/Git paths | Create an environment snapshot | Sanitized metadata only |
| Discoverable harnesses, Skills, MCP servers, and plugins | Decide whether historical workflows can be reused | Names, versions, and config paths; no secret values |
| Host aliases and `IdentityFile` paths from `~/.ssh/config` | Describe available remote connection routes | Only with approved local-tool scanning; private keys are never opened |

Environment scanning has two levels:

- **Default: metadata scan.** Reads versions, executable paths, and project-visible configuration.
- **Optional: local-tool scan.** After user approval, reads non-secret fields from known MCP, plugin, and SSH configurations.

### 3. Content created inside the project

| Path | Default action | Purpose |
| --- | --- | --- |
| `.agent-relay/HANDOFF.md` | Create and refresh | Short summary every new agent reads first |
| `.agent-relay/relay.py` | Create | Dependency-free project-local runtime |
| `.agent-relay/config.json` | Create | Schema version, adapters, and record policy |
| `.agent-relay/goals.json` | Create; may remain empty | Explicit, inferred, long-term, and short-term goals |
| `.agent-relay/tasks/` | Create | One file per task, including claims and write scopes |
| `.agent-relay/events/` | Create | One file per event to avoid concurrent append conflicts |
| `.agent-relay/versions/` | Create | Sealed deliverables, checksums, and version history |
| `.agent-relay/environments/` | Create | Sanitized environment and capability snapshots |
| `.agent-relay/runtime/` | Create and Git-ignore | Locks, leases, caches, and local transient state |
| `.agent-relay/backups/` | Create when existing files are changed | Pre-change copies for recovery |

### 4. Project files it may modify

Agent Relay should not overwrite whole files. It maintains bounded marker blocks inside existing files:

```text
<!-- agent-relay:start -->
...project handoff entry point managed by Agent Relay...
<!-- agent-relay:end -->
```

| File | Modification | Reason |
| --- | --- | --- |
| `AGENTS.md` | Create if absent; otherwise insert a managed block | Cross-harness primary entry point |
| `CLAUDE.md` | Create or add an `@AGENTS.md` import when needed | Claude Code adapter |
| `GEMINI.md` | Create or import `AGENTS.md` when needed | Gemini context adapter |
| `.cursor/rules/agent-relay.mdc` | Create when Cursor is detected or all adapters are requested | Strengthen always-on Cursor loading |
| `.github/copilot-instructions.md` | Add a managed block only for legacy compatibility | GitHub Copilot adapter |
| `.gitignore` | Add a managed ignore block | Exclude locks, caches, local paths, and optional version copies |

Existing files are backed up before modification. Re-running `init` must be idempotent and must not duplicate marker blocks.

### 5. Writes during normal work

Agent Relay may:

- create or update the current task file;
- create a concise action event;
- update an environment snapshot reference;
- atomically regenerate `HANDOFF.md`;
- release task leases;
- copy selected deliverables into the versions directory and calculate SHA-256 when finalization is explicit;
- avoid copying the full repository by default.

Version copies consume disk space. `status` should report version storage size, and deleting a sealed version must require explicit confirmation.

## What it does not do

In default mode, Agent Relay **does not**:

- request `sudo`, administrator access, or system extension permissions;
- install startup items, LaunchAgents, Windows services, scheduled tasks, or background daemons;
- continuously watch ports, keyboard input, mouse input, clipboard data, or browser activity;
- read macOS Keychain, OS credential stores, browser cookies, or login sessions;
- read SSH private key contents;
- store tokens, passwords, cookies, private keys, complete environment variable values, or MCP secrets;
- upload projects, handoffs, or environment snapshots to an Agent Relay service;
- send telemetry;
- run `git commit`, `git push`, create pull requests, or publish releases automatically;
- modify user-level harness, MCP, shell, Git, or SSH configuration automatically;
- delete existing project files or overwrite sealed versions;
- read private chat histories from other harnesses;
- store hidden model reasoning or full conversation transcripts.

The Skill installer, GitHub, model provider, and harness may have their own network or telemetry policies. Those policies are separate from Agent Relay and should be reviewed independently.

## Project file layout

```text
project/
├── AGENTS.md
├── CLAUDE.md                       # when needed
├── GEMINI.md                       # when needed
├── .agents/
│   └── skills/
│       └── agent-relay/            # optional project bridge Skill
└── .agent-relay/
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
    ├── backups/
    └── runtime/
```

Recommended data boundary:

| Data type | Commit to Git? | Examples |
| --- | --- | --- |
| Shared handoff facts | Yes, after sanitization | `HANDOFF.md`, goals, task outcomes, version manifests |
| Machine-local environment | No | Home-directory paths, local harness locations, SSH identity paths |
| Runtime coordination | No | Locks, leases, PIDs, caches |
| Large version artifacts | No by default | Presentation, video, archive, or binary deliverable copies |

## Daily workflow

```mermaid
flowchart LR
    A[Read HANDOFF] --> B[Create or claim a task]
    B --> C{Capabilities sufficient?}
    C -- Yes --> D[Execute and verify]
    C -- No --> E[Explain the gap and confirm an alternative]
    E -- Accepted --> D
    E -- Rejected --> F[Record the blocker]
    D --> G[Record the result and refresh HANDOFF]
```

Each event contains operational facts only: problem summary, actions, changed files, verification, remaining work, and the next step. It must not contain hidden chain-of-thought.

## Quick status report

When the user asks “give me a status report,” “where are we now?”, “check agent-relay,” or an equivalent question, the agent should not scan every historical event. It should run the read-only command:

```bash
python .agent-relay/relay.py report
```

The default report has a stable structure that an agent can relay directly:

```text
Agent Relay report
Health: healthy / degraded / stale / uninitialized
Project goal: explicit goal, candidate goal, or “not recorded”
Active work: task ID, owner, progress, and write scope
Last completed: latest result and verification
Version state: latest sealed version, unsealed changes, and storage size
Environment: harness, model, key capabilities, and environment changes
Blockers: path conflicts, expired leases, missing capabilities, or “none”
Next step: one safe action to continue
Updated: source timestamp and event ID
```

Three output modes are planned:

| Command | Output | Use |
| --- | --- | --- |
| `relay report` / `relay report --short` | About 8–10 Markdown lines | Fast user-facing report |
| `relay report --full` | Expanded goals, tasks, versions, and environment differences | Handoff, review, and diagnosis |
| `relay report --json` | Stable machine-readable object | Hooks, MCP, scripts, and other agents |

`report` is side-effect free: it does not claim a task, renew a lease, create an event, or rewrite `HANDOFF.md`. It reads canonical state under `.agent-relay/` and performs lightweight consistency checks. The design target is a few seconds for a typical local project.

The three inspection commands answer different questions:

| Command | Question answered |
| --- | --- |
| `relay report` | “What is the project situation right now?” |
| `relay status` | “What are the raw goals, tasks, versions, and leases?” |
| `relay doctor` | “Are installation, schema, permissions, and harness adapters healthy?” |

If `HANDOFF.md` is older than the latest event, a task lease has expired, a version manifest fails validation, or the current harness lacks a historical capability, the report must show `degraded` or `stale` rather than a false healthy state.

## Goals, actions, versions, and environments

### Goals

- Leave the global goal blank when none can be identified.
- Mark user-stated goals as `explicit`.
- Mark agent-inferred goals as unconfirmed `candidate` entries.
- Separate long-term and short-term goals; allow pause, completion, and supersession.
- Use goals as reminders, never as a reason to reject the user's current request.

### Actions

At task start, meaningful checkpoints, completion, or blocking events, record:

- a short summary of the user's problem;
- explainable approach and key decisions;
- files created, modified, or deleted;
- important commands and verification results;
- current status, blockers, and next step;
- harness, model, session, and environment snapshot references.

### Versions

Automatic sealing requires full conversational intent that the deliverable is ready now:

| User language | Default behavior |
| --- | --- |
| “Finalize this,” “final version,” “send this version” | Seal automatically |
| “Send this to my manager/colleague/client now” | Seal before delivery |
| “Looks good,” “that's it” | Use context; ask when scope is unclear |
| “We will send it later,” “keep editing” | Do not seal |

Sealing flow: determine artifact scope → copy into a temporary version directory → calculate checksums → summarize events since the previous version → atomically publish `v001`, `v002`, and so on → continue edits in the working copy.

For code projects, record a Git reference or working-tree manifest by default; do not create a commit automatically. For Office documents, images, audio, video, and other binary deliverables, copy only the selected artifacts.

### Environments

Actions reference an environment snapshot ID. A new snapshot is created only when the environment changes.

Allowed metadata includes:

- OS, architecture, shell, harness, and model;
- capabilities such as shell, browser, computer use, network, Office, and image generation;
- Skill, MCP, and plugin names, versions, and sanitized config paths;
- Git and SSH executable paths, SSH host aliases, public-key fingerprints, and last verification time.

If a previous workflow required computer use but the current harness only has DOM browser automation, the agent must explain the missing capability, closest alternative, and result difference before using a materially different method.

## Multi-agent coordination

Each task carries a unique ID, owner, state, dependencies, lease, heartbeat, and declared write scope.

```mermaid
flowchart LR
    A[Agent A claims src/api/**] --> C{Does Agent B overlap?}
    B[Agent B is ready] --> C
    C -- No --> D[Run in parallel]
    C -- Yes --> E[Wait, split the task, or use another worktree]
```

| Situation | Behavior |
| --- | --- |
| Different tasks with disjoint writes | Run in parallel |
| Overlapping write scopes | Block the second writer |
| Original agent has no heartbeat | Take over after lease expiry and record the reason |
| Same module must be changed concurrently | Use separate Git worktrees, then review and merge |
| Multiple readers of the same file | Allow parallel reads |

One working directory is suitable only for disjoint concurrent writes. Network filesystems, cloud-synced folders, and cross-machine locking are outside the first release's consistency guarantees.

## Harness compatibility

Agent Skills and project instructions load differently across harnesses. Agent Relay uses **one canonical state, thin adapters, and verification by `doctor`**. The evidence below was reviewed on **2026-08-28**. It describes the planned adapter surface, not completed end-to-end support in the current repository.

### Compatibility levels

| Level | Meaning |
| --- | --- |
| **A: official mechanism verified** | Official documentation confirms `SKILL.md`, `AGENTS.md`, or persistent project rules, so a direct adapter can be designed |
| **B: standard ecosystem path** | Agent Skills/AGENTS.md tooling has an installation path, but Agent Relay still needs product-level tests |
| **C: bridge adapter** | The product has custom Skills, Rules, or folder context, but uses a different format or import flow |
| **D: research pending** | No stable public project-instruction or Skill interface was found; only manual guidance is possible |

### Popular products with verified official mechanisms

| Product / harness | Planned entry point | Level | Notes |
| --- | --- | --- | --- |
| OpenAI Codex | `AGENTS.md` + `.codex/skills/` | A | Hierarchical project instruction chain |
| Claude Code | `CLAUDE.md` → `@AGENTS.md` + `.claude/skills/` | A | Imports preserve one source of truth |
| Cursor | `AGENTS.md` + `.agents/skills/` / `.cursor/skills/` | A | An always-on Cursor Rule may be added |
| GitHub Copilot / VS Code | `AGENTS.md` + `.agents/skills/` / `.github/skills/` | A | Covers IDE, CLI, and cloud-agent entry points |
| Gemini CLI | `GEMINI.md` → `@./AGENTS.md` + `.gemini/skills/` | A | Context filenames can also be configured |
| Qoder IDE / Qoder CLI / Qoder agent workbench, sometimes called Qoder Work | `AGENTS.md` + `.qoder/skills/` | A | Official Rules recognize `AGENTS.md`; IDE and CLI share the Skill model |
| Qoder CN CLI, documented under Alibaba Lingma | `AGENTS.md` + `.qoder/skills/`; user Skills in `~/.qoder-cn/skills/` | A | Supports automatic and manual `SKILL.md` invocation |
| TRAE Code | `AGENTS.md` + `.trae/skills/`; optional `.agents/skills/` | A | AGENTS and `.agents` imports must be enabled in settings |
| TraeWork | `.trae/skills/` or uploaded `.zip` / `.skill` with root `SKILL.md` | A | Local and cloud task environments must be recorded separately |
| Tencent CodeBuddy IDE / CodeBuddy Code CLI | `CODEBUDDY.md` + `.codebuddy/skills/` | A | `CODEBUDDY.md` is persistent; Skills load on demand |
| Qwen Code | `.qwen/skills/` | A | Official Agent Skills; project Skills can be shared through Git |
| Kimi Code CLI | `.agents/skills/` / `.kimi/skills/` | A | Official Agent Skills support plus Claude/Codex Skill directory compatibility |
| OpenCode | `AGENTS.md` + `.opencode/skills/` | A | Native on-demand Agent Skills |
| Cline | `AGENTS.md` + `.cline/skills/` / `.clinerules/` | A | Recognizes several cross-tool rule sources |
| Pi | Project Skill + `AGENTS.md` | A | Uses Agent Skills and project instructions |

### Standard-ecosystem adapter targets

The following tools are present in the Agent Skills installation ecosystem or the `AGENTS.md` ecosystem. The first release will generate a standard entry point and let `relay doctor` classify it as `verified`, `partial`, or `manual`:

| Product / harness | Candidate entry point | Level |
| --- | --- | --- |
| Windsurf / Cascade | `AGENTS.md` + `.windsurf/skills/` / rules | B |
| Roo Code | `AGENTS.md` + `.roo/skills/` | B |
| Kilo Code | `AGENTS.md` + `.kilocode/skills/` | B |
| Continue | `.continue/skills/` + Continue Rules | B |
| Aider | `AGENTS.md` configured through `read` | B |
| Amp | `AGENTS.md` + `.agents/skills/` | B |
| Factory Droid | `AGENTS.md` + `.factory/skills/` | B |
| Amazon Kiro / Kiro CLI | `.kiro/skills/` + agent resources | B |
| JetBrains Junie | `AGENTS.md` + `.junie/skills/` | B |
| Goose | `AGENTS.md` + `.goose/skills/` | B |
| OpenHands | `.openhands/skills/` + project instructions | B |
| Devin | `AGENTS.md` + Knowledge / Skills | B |
| Warp | `AGENTS.md` / project rules | B |
| Zed | `AGENTS.md` / Agent Rules | B |
| Augment Code | `AGENTS.md` | B |
| Google Jules | `AGENTS.md` | B |
| Google Antigravity | `.agent/skills/` + project rules | B |

### Bridge scope for Chinese office and development agents

| Product | Verified official mechanism | Level | Agent Relay plan |
| --- | --- | --- | --- |
| Tencent WorkBuddy | Custom Skills use `skill.yml`, implementation files, and a README; authorized folders can be operated on | C | Generate a WorkBuddy bridge Skill that calls `relay report --json` read-only and requests explicit project-folder authorization |
| Alibaba Lingma IDE | Coding-agent and rules features; Qoder CN CLI has documented `SKILL.md` support | C | Detect the IDE separately from Qoder CN CLI so paths are not reused incorrectly |
| Baidu Comate | Public product includes agent and codebase capabilities, but no stable public Agent Skills/AGENTS interface was found | D | Generate manual handoff guidance only until an official interface is verified |
| Zhipu CodeGeeX | Code-agent capabilities are public, but no standard project Skill directory was verified | D | Use manual project instructions without claiming automatic loading |
| Huawei CodeArts Snap | Development-assistant capabilities exist, but no general Skill/AGENTS interface was verified | D | Stay in manual mode and report the limitation through `doctor` |
| Fitten Code | IDE agent capabilities exist; no general project-rule interface was verified | D | Stay in manual mode |
| iFlyCode / iFlytek coding assistant | Coding-assistant capabilities exist; no general project-rule interface was verified | D | Stay in manual mode |

Office agents such as WorkBuddy and TraeWork can process documents, spreadsheets, presentations, and local folders. Their adapters must record which folder was authorized and whether execution is local or cloud-based. They must not silently include personal files outside the project.

Compatibility appears in `relay report`: detected harness, active entry point, last verification time, compatibility level, and missing capabilities. Level `A` means an official mechanism exists; it does not mean Agent Relay has already passed implementation tests for that product.

Compatibility also does not let project files override system or organization policy. System instructions, managed policy, and the user's current explicit request remain higher priority.

## Privacy and security

Default safeguards:

- show a dry-run before installation;
- do not pre-approve unrestricted shell access in `SKILL.md`;
- keep writes inside the approved project root;
- parse structured configuration instead of copying whole config files;
- refuse to persist fields named like `token`, `secret`, `password`, `cookie`, or `private_key`;
- separate shareable state from machine-local state;
- use one event per file and temporary-file-plus-atomic-rename writes;
- never overwrite sealed version directories;
- back up instruction files before modification;
- provide no Agent Relay cloud service and upload no data automatically.

Any Skill can instruct an agent to run commands. Review its source, `SKILL.md`, and scripts before installation, and retain the harness's command approval controls.

## Planned commands

| Command | Purpose |
| --- | --- |
| `relay init --dry-run` | Preview all reads and writes |
| `relay init` | Install persistent project capability |
| `relay start` | Capture the session environment and create or claim a task |
| `relay checkpoint` | Record a safe handoff point in long work |
| `relay finish` | Record the outcome, release the task, and refresh handoff |
| `relay report [--short\|--full\|--json]` | Generate a read-only current-state report |
| `relay seal` | Create an immutable version and its history |
| `relay status` | Show goals, tasks, conflicts, versions, and recent actions |
| `relay doctor` | Validate adapters, schema, permissions, and harness discovery |
| `relay uninstall` | Remove managed entry points and runtime; preserve history by default |
| `relay purge` | Delete handoff data and versions only after explicit confirmation |

The first release is planned as a Python standard-library implementation with no project package dependencies. The minimum Python version will be set after implementation and tests.

## Uninstall and recovery

Planned safe uninstall flow:

```bash
python .agent-relay/relay.py uninstall --dry-run
python .agent-relay/relay.py uninstall
```

Default uninstall should only:

- remove marker blocks managed by Agent Relay;
- remove the project bridge Skill and runtime;
- preserve `events/`, `versions/`, `goals.json`, and backups;
- leave all pre-existing project instructions intact.

Permanent data deletion requires a separate, explicitly confirmed `purge` operation.

For a globally installed Skill:

```bash
npx skills remove --global agent-relay
```

Removing the global Skill does not alter already initialized projects. Each project's runtime and data are managed independently.

## Limitations

- Project instructions are model context, not system-level enforcement; adherence can differ between models.
- Level `A` in the compatibility matrix means an official entry point was verified, not that Agent Relay has completed implementation and regression tests for that harness.
- Some harnesses need lifecycle hooks for deterministic start/stop actions. Hooks will be optional enhancements, not silent global modifications.
- Agent Relay cannot universally read private conversation histories across Codex, Claude, Cursor, and other products.
- Inaccessible information must remain unknown; it must not be invented.
- Ambiguous finalization must be confirmed rather than inferred from one keyword.
- The first release targets same-machine local filesystems; it will not promise strongly consistent locks on Dropbox, cloud drives, NFS, or multiple machines.
- Large binary versions consume disk space, so only explicit deliverables are copied by default.
- This repository does not yet provide an executable release.

## FAQ

### Must I invoke the Skill in every session?

No. Initialization leaves entry points and a runtime in the project. Future harnesses load the project instructions and the agent invokes the project-local runtime.

### How can an agent report the current situation quickly?

Say “give me a status report” or “check agent-relay.” The agent should run `relay report` and relay the fixed-format summary. It does not need to read the full event history, and reporting does not claim a task or modify state.

### Does it run continuously in the background?

No. There is no daemon, listening port, or startup item. It runs short commands at start, checkpoints, completion, and sealing.

### Does it upload my project?

Agent Relay itself does not. Your model provider, harness, Git host, and Skill installer may have separate network policies.

### Will it modify an existing `AGENTS.md`?

Yes, but only through a bounded managed block, with a backup created first. Uninstall removes only that managed block.

### Does it work without Git?

That is planned. Without Git, the current directory becomes the project root and versions use file manifests and hashes. Git capabilities are marked unavailable.

### Will it commit or push automatically?

No. It will not commit, push, open a pull request, or publish unless the user's current request explicitly asks for it.

### Can it read chats from another AI application?

Usually not. Initialization reads accessible project facts and approved local metadata. Unavailable history remains blank.

### Does “looks good” always seal a version?

No. It seals only when context clearly says the complete deliverable is ready now. Otherwise, it asks for scope.

### How are simultaneous file edits prevented?

Agents claim a task and write scope before editing. Overlapping writes are blocked; use task splitting or separate worktrees when concurrency is required.

### Are SSH private keys or MCP tokens stored?

No. Only approved names, versions, paths, and fingerprints are retained. Secret fields and private-key contents are prohibited.

## Roadmap

- [x] Simplified architecture and data boundaries
- [x] Desktop and mobile visual documentation
- [x] Bilingual GitHub README
- [x] Quick-report protocol and expanded harness compatibility matrix
- [ ] Agent Skills-compliant `SKILL.md`
- [ ] Idempotent installer, dry-run, backups, and uninstall
- [ ] File-based events, task leases, and path conflict detection
- [ ] Goals, environment snapshots, capability negotiation, and `relay report`
- [ ] Immutable version sealing and checksum verification
- [ ] Adapter tests for major international harnesses
- [ ] Dedicated tests for Qoder, Qoder CN, TRAE Code, TraeWork, CodeBuddy, WorkBuddy, Qwen Code, and Kimi Code CLI
- [ ] Unit tests, failure recovery tests, and the first `v0.1.0` release

## Documentation

- [Simplified architecture specification](./docs/agent-relay-simple.md)
- [Visual architecture](./docs/agent-relay-simple.html)
- [Agent Skills Specification](https://agentskills.io/specification)
- [AGENTS.md](https://agents.md/)
- [skills CLI](https://github.com/antfu/skills-cli)
- [Qoder Rules](https://docs.qoder.com/user-guide/rules) · [Qoder Skills](https://docs.qoder.com/extensions/skills) · [Qoder CN Skills](https://help.aliyun.com/zh/lingma/qoder-cn/user-guide/skills)
- [TRAE Code Skills](https://docs.trae.ai/ide/skills) · [TRAE Code Rules](https://docs.trae.ai/ide/rules?ref) · [TraeWork Skills](https://docs.trae.ai/solo/skills?_lang)
- [CodeBuddy Skills](https://www.codebuddy.ai/docs/ide/Features/Skills) · [CodeBuddy Best Practices](https://www.codebuddy.ai/docs/cli/best-practices) · [WorkBuddy Custom Skills](https://www.workbuddy.ai/docs/workbuddy/From-Beginner-to-Expert-Guide/Practice-Cases/Create-Skills)
- [Qwen Code Skills](https://qwenlm.github.io/qwen-code-docs/en/users/features/skills/) · [Kimi Code CLI Skills](https://moonshotai.github.io/kimi-cli/en/customization/skills.html)

## Contributing and license

Before the first executable release, issues and design feedback are the most useful contributions. Changes to the installer, security boundaries, harness adapters, or data schema should include tests and updates to both language versions.

This repository does not yet include an open-source license. Until a license is added, do not assume permission to copy, modify, or redistribute its contents.
