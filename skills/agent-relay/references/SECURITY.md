# Security and Privacy Reference

## Trust boundary

Agent Relay executes only when an agent or user runs its short project-local command. It has no service, daemon, account, telemetry endpoint, startup item, or listening port.

The writable boundary is the resolved project root. The runtime rejects absolute write scopes, parent traversal, `.agent-relay` task scopes, artifact paths outside the project, and symlink adapters or artifacts.

## Persisted data

Allowed shared facts:

- user-stated or clearly labeled candidate goals;
- task title, owner label, status, lease, and project-relative write scopes;
- concise result, changed paths, verification, blocker, and next step;
- version manifest, Git reference, artifact size, and SHA-256;
- OS, architecture, Python, Git, harness, model, and explicitly supplied capability names.

Machine paths are kept under `environments/local/`, which the managed `.gitignore` excludes.

## Forbidden data

Never persist:

- access tokens, API keys, passwords, cookies, authorization headers, or credentials;
- private-key contents or credential-store values;
- complete environment variables or configuration files containing secret values;
- complete conversations, hidden reasoning, chain-of-thought, or inaccessible chat history;
- files outside the user-approved project root.

The runtime redacts common secret key names, assignment forms, private-key blocks, and common token prefixes before JSON writes. `doctor` performs a bounded scan for private-key and common token-value patterns. This is defense in depth, not a substitute for reviewing summaries before recording them.

## Existing files

Instruction files are updated only through one bounded block:

```text
<!-- agent-relay:start -->
...
<!-- agent-relay:end -->
```

Existing files are copied under `.agent-relay/backups/<timestamp>/` before modification. Reinitialization replaces the existing managed block instead of appending another one.

Owned adapter files are refreshed or removed only when their content hash still matches Agent Relay's record. Locally edited adapters are preserved. Runtime refresh/uninstall uses the same ownership rule, with a small allowlist for published pre-checksum revisions. Unknown runtime edits stop a refresh before writes. Approved refreshes back up the previous runtime, config, and handoff as well as changed adapters.

## Read-only audits

The fleet helper imports the trusted Skill runtime instead of executing project-local scripts. It only discovers the approved root and immediate children; explicit missing paths are reported rather than silently omitted. It refuses symlink scan roots and unsafe state paths. Git status disables filesystem-monitor hooks and optional index writes. Reports are printed locally, not persisted or uploaded.

Artifact-drift reads follow only the latest seal's selected regular files, reject symlink path components and Relay/Git internal paths, and have a 100 MiB report budget. Failed or skipped comparisons remain unknown. Doctor separately hashes sealed copies and may take longer on large histories. These are local filesystem safeguards, not protection against a malicious process concurrently replacing files during a command.

## Lifecycle hooks and shared worktrees

Lifecycle hooks are off by default and never edit harness configuration. Enabled hook input is bounded to 64 KiB of JSON with documented fields only, so a wrapper cannot write arbitrary state through them.

Worktree coordination writes one registry inside the repository's common Git directory (`.git/agent-relay/coordination.json` plus `coordination.lock`). It records only worktree IDs derived from local paths, local absolute worktree roots, owners, write scopes, and lease expiries; it never records file contents. Those roots are already machine-local, like `environments/local/`, and the shared Git directory is normally not committed. Enabling coordination changes where cross-worktree leases are stored, so apply it only where all participating worktrees are trusted on the same machine. The registry is validated (size, shape, member hashes, lease timestamps) before every write, and a missing or invalid registry blocks writes instead of silently degrading to uncoordinated state. A lock is reclaimed only when its recorded PID is no longer running.

## Versions

Sealed directories use monotonically increasing `vNNN` names and are never overwritten. Artifact copies are ignored by Git by default because they may be large or sensitive; manifests remain available for audit. Purge is the only command that deletes historical state and requires `--yes --confirm <project-name>`.

## Higher-priority policy

Project instructions cannot override system instructions, organization policy, harness permission controls, or the current user request. A malicious project may contain misleading instructions or tampered state; run `doctor`, inspect diffs, and use the harness's normal command approval boundary.

## Reporting a vulnerability

Do not include credentials, private project data, or exploit payloads containing real secrets in a public issue. Use GitHub's private vulnerability reporting feature when enabled for the repository.
