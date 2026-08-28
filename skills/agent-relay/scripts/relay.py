#!/usr/bin/env python3
"""Agent Relay: dependency-free, project-local handoff runtime."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Tuple


VERSION = "0.1.0"
SCHEMA_VERSION = 1
STATE_DIR_NAME = ".agent-relay"
MANAGED_START = "<!-- agent-relay:start -->"
MANAGED_END = "<!-- agent-relay:end -->"
LOCK_STALE_SECONDS = 120

SECRET_KEY_RE = re.compile(
    r"(?i)(?:^|[_-])(token|secret|password|passwd|cookie|private[_-]?key|"
    r"api[_-]?key|authorization|credential)(?:$|[_-])"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|secret|password|passwd|cookie|api[_-]?key|authorization)"
    r"\s*[:=]\s*([^\s,;]+)"
)
TOKEN_VALUE_RE = re.compile(
    r"\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b"
)
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?"
    r"-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.DOTALL,
)


class RelayError(RuntimeError):
    """A user-facing runtime error."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def safe_slug(value: str, fallback: str = "work") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug[:36] or fallback).strip("-")


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_string(value: str) -> str:
    value = PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", value)
    value = TOKEN_VALUE_RE.sub("[REDACTED TOKEN]", value)
    return SECRET_ASSIGNMENT_RE.sub(lambda m: "%s=[REDACTED]" % m.group(1), value)


def sanitize(value: Any, key: str = "") -> Any:
    if key and SECRET_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    return value


def atomic_write(path: Path, content: str, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(str(temp_path), mode)
        os.replace(str(temp_path), str(path))
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp_path.unlink()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RelayError("Invalid JSON in %s: %s" % (path, exc))


def run_command(args: Sequence[str], cwd: Path) -> Tuple[int, str]:
    try:
        result = subprocess.run(
            list(args),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=8,
            check=False,
        )
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def discover_root(explicit: Optional[str]) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
    else:
        script = Path(__file__).resolve()
        if script.parent.name == STATE_DIR_NAME:
            root = script.parent.parent
        else:
            code, output = run_command(["git", "rev-parse", "--show-toplevel"], Path.cwd())
            root = Path(output).resolve() if code == 0 and output else Path.cwd().resolve()
    if not root.is_dir():
        raise RelayError("Project root is not a directory: %s" % root)
    return root


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        raise RelayError("Path escapes the project root: %s" % path)


def nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def validate_destination(root: Path, path: Path) -> None:
    relative_path(root, path.parent if path.parent.exists() else nearest_existing(path.parent))
    if path.is_symlink():
        raise RelayError("Refusing to modify symlink: %s" % path)


def project_member(root: Path, value: str) -> Path:
    if not isinstance(value, str) or "\x00" in value:
        raise RelayError("Invalid project-relative path")
    cleaned = value.replace("\\", "/").strip()
    pure = PurePosixPath(cleaned)
    if not cleaned or pure.is_absolute() or ".." in pure.parts:
        raise RelayError("Invalid project-relative path: %s" % value)
    path = root.joinpath(*pure.parts)
    parent = path.parent if path.parent.exists() else nearest_existing(path.parent)
    relative_path(root, parent)
    return path


def normalize_scope(root: Path, value: str) -> str:
    del root
    cleaned = value.replace("\\", "/").strip()
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if not cleaned or cleaned.startswith("/"):
        raise RelayError("Write scopes must be project-relative: %s" % value)
    pure = PurePosixPath(cleaned)
    if ".." in pure.parts or pure.parts[0] == STATE_DIR_NAME:
        raise RelayError("Invalid write scope: %s" % value)
    return pure.as_posix()


def scope_prefix(value: str) -> str:
    parts = []
    for part in PurePosixPath(value).parts:
        if any(char in part for char in "*?["):
            break
        parts.append(part)
    return "/".join(parts).rstrip("/")


def scopes_overlap(left: str, right: str) -> bool:
    if left == right or fnmatch.fnmatch(left, right) or fnmatch.fnmatch(right, left):
        return True
    a, b = scope_prefix(left), scope_prefix(right)
    if not a or not b:
        return True
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return "%.1f %s" % (value, unit) if unit != "B" else "%d B" % value
        value /= 1024
    return "%d B" % size


class StateLock:
    def __init__(self, path: Path, timeout: float = 5.0) -> None:
        self.path = path
        self.timeout = timeout
        self.acquired = False

    def __enter__(self) -> "StateLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout
        payload = json.dumps({"pid": os.getpid(), "created_at": iso_now()})
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                    if age > LOCK_STALE_SECONDS:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.time() >= deadline:
                    raise RelayError("Another Agent Relay command holds the state lock")
                time.sleep(0.1)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.acquired:
            with contextlib.suppress(FileNotFoundError):
                self.path.unlink()


def managed_block(body: str) -> str:
    return "%s\n%s\n%s" % (MANAGED_START, body.strip(), MANAGED_END)


def merge_managed_block(existing: str, body: str) -> str:
    block = managed_block(body)
    starts, ends = existing.count(MANAGED_START), existing.count(MANAGED_END)
    if starts != ends or starts > 1:
        raise RelayError("Malformed or duplicate Agent Relay managed block")
    if starts == 1:
        pattern = re.compile(
            re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END), re.DOTALL
        )
        result = pattern.sub(block, existing)
    else:
        separator = "\n\n" if existing.strip() else ""
        result = existing.rstrip() + separator + block
    return result.rstrip() + "\n"


def remove_managed_block(existing: str) -> str:
    starts, ends = existing.count(MANAGED_START), existing.count(MANAGED_END)
    if starts == 0 and ends == 0:
        return existing
    if starts != 1 or ends != 1:
        raise RelayError("Malformed Agent Relay managed block")
    pattern = re.compile(
        r"\n?" + re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END) + r"\n?",
        re.DOTALL,
    )
    result = pattern.sub("\n", existing).strip()
    return result + "\n" if result else ""


AGENTS_BODY = """
## Agent Relay

This project uses `.agent-relay/` as its canonical handoff and coordination state.
The user's current explicit request always has priority over stored goals.

Before substantive work:

1. Read `.agent-relay/HANDOFF.md`.
2. Run `python3 .agent-relay/relay.py report` for a read-only health summary.
3. Before editing, run `python3 .agent-relay/relay.py start --title "<task>" --scope "<path-or-glob>"` for each planned write scope.

During and after work:

- Use `checkpoint` for a long task and `finish` when work completes or blocks.
- Pass only safe names through `--harness`, `--model`, and repeated `--capability`; never paste configuration values or credentials.
- Record concise operational facts, changed files, verification, blockers, and the next step. Never store hidden reasoning or full conversations.
- Never persist tokens, passwords, cookies, private keys, complete environment variables, or credentials.
- When the user asks for status, run `report`; it must not claim work or mutate state.
- When the user clearly requests a final version or immediate delivery, run `seal` for the explicit artifact scope. Ask when finalization scope is ambiguous.
- Respect active write-scope conflicts. Split work, wait, or use a separate Git worktree instead of bypassing a live lease.
"""

GITIGNORE_BODY = """
# Agent Relay machine-local and potentially large data
.agent-relay/runtime/
.agent-relay/environments/local/
.agent-relay/backups/
.agent-relay/versions/*/artifacts/
"""

PROJECT_SKILL = """---
name: agent-relay
description: Maintains durable project handoff, goal, task, status, environment, and sealed-version state. Use whenever entering a project containing .agent-relay, before substantive edits, when reporting progress, when handing work to another agent, or when the user finalizes a deliverable.
license: MIT
compatibility: Requires Python 3.9 or newer in the project environment.
metadata:
  author: chopperH0824
  version: \"0.1.0\"
---

# Agent Relay project bridge

Treat `.agent-relay/` at the project root as the canonical state. The current user request overrides stored goals.

1. Read `.agent-relay/HANDOFF.md` and run `python3 .agent-relay/relay.py report` when entering the project.
2. Run `start` before substantive writes, declaring every intended project-relative path or glob with `--scope`. Include safe harness, model, and capability names when known; never include configuration values.
3. Use `checkpoint` during long work and `finish` with the result, changed paths, verification, blockers, and next step.
4. Run `report` for status questions. It is read-only.
5. Run `seal --yes` only when finalization and artifact scope are explicit; otherwise ask.
6. Never write secrets, full conversations, or hidden model reasoning to Relay state.

Run `python3 .agent-relay/relay.py --help` for command details.
"""

WORKBUDDY_GUIDE = """# WorkBuddy manual bridge

WorkBuddy uses a custom `skill.yml` package whose public guide does not define a stable field-level schema. Agent Relay therefore does not generate an unverified package.

Authorize only this project folder, then create a WorkBuddy Skill that invokes the following read-only command:

```bash
python3 .agent-relay/relay.py report --json
```

Keep `start`, `finish`, `seal`, `uninstall`, and `purge` behind explicit user confirmation. Record whether WorkBuddy runs locally or in a cloud environment, and never include files outside the authorized project folder.
"""


def cursor_rule() -> str:
    return """---
description: Persistent Agent Relay project handoff and coordination protocol
alwaysApply: true
---

Follow the Agent Relay section in `AGENTS.md`. Read `.agent-relay/HANDOFF.md` before substantive work and use the project-local Relay runtime for task claims, reports, checkpoints, completion, and version sealing.
"""


ADAPTER_SKILL_PATHS = {
    "qoder": ".qoder/skills/agent-relay/SKILL.md",
    "trae": ".trae/skills/agent-relay/SKILL.md",
    "codebuddy": ".codebuddy/skills/agent-relay/SKILL.md",
    "qwen": ".qwen/skills/agent-relay/SKILL.md",
    "kimi": ".kimi/skills/agent-relay/SKILL.md",
    "opencode": ".opencode/skills/agent-relay/SKILL.md",
    "cline": ".cline/skills/agent-relay/SKILL.md",
    "pi": ".pi/skills/agent-relay/SKILL.md",
    "windsurf": ".windsurf/skills/agent-relay/SKILL.md",
    "roo": ".roo/skills/agent-relay/SKILL.md",
    "kilo": ".kilocode/skills/agent-relay/SKILL.md",
    "continue": ".continue/skills/agent-relay/SKILL.md",
    "kiro": ".kiro/skills/agent-relay/SKILL.md",
    "goose": ".goose/skills/agent-relay/SKILL.md",
    "openhands": ".openhands/skills/agent-relay/SKILL.md",
}


class Relay:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.state = self.root / STATE_DIR_NAME
        self.config_path = self.state / "config.json"
        self.goals_path = self.state / "goals.json"
        self.handoff_path = self.state / "HANDOFF.md"
        self.runtime_path = self.state / "relay.py"
        self.tasks_dir = self.state / "tasks"
        self.events_dir = self.state / "events"
        self.versions_dir = self.state / "versions"
        self.environments_dir = self.state / "environments"
        self.lock_path = self.state / "runtime" / "state.lock"

    def require_initialized(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise RelayError(
                "Agent Relay is not initialized in %s. Run init --dry-run first." % self.root
            )
        config = load_json(self.config_path)
        if not isinstance(config, dict) or config.get("schema_version") != SCHEMA_VERSION:
            raise RelayError("Unsupported or invalid Agent Relay configuration")
        if config.get("installed") is False:
            raise RelayError("Agent Relay was uninstalled from this project")
        return config

    def _adapter_specs(self, mode: str) -> List[Tuple[str, str, str, str]]:
        specs = [
            ("AGENTS.md", "block", AGENTS_BODY, "agents"),
            (".gitignore", "block", GITIGNORE_BODY, "gitignore"),
            (".agents/skills/agent-relay/SKILL.md", "owned", PROJECT_SKILL, "universal-skill"),
        ]
        if mode == "minimal":
            return specs

        optional = [
            ("CLAUDE.md", "block", "@AGENTS.md\n\nFollow the Agent Relay section imported from the shared project instructions.", "claude"),
            ("GEMINI.md", "block", "@./AGENTS.md\n\nFollow the Agent Relay section imported from the shared project instructions.", "gemini"),
            ("CODEBUDDY.md", "block", "Follow `AGENTS.md` and the project-local Agent Relay protocol before and after substantive work.", "codebuddy-instructions"),
            (".cursor/rules/agent-relay.mdc", "owned", cursor_rule(), "cursor"),
            (".github/copilot-instructions.md", "block", "Follow the Agent Relay section in `AGENTS.md`; read `.agent-relay/HANDOFF.md` before substantive work.", "copilot"),
        ]
        signals = {
            "claude": ["CLAUDE.md", ".claude"],
            "gemini": ["GEMINI.md", ".gemini"],
            "codebuddy-instructions": ["CODEBUDDY.md", ".codebuddy"],
            "cursor": [".cursor"],
            "copilot": [".github"],
        }
        for spec in optional:
            name = spec[3]
            if mode == "all" or any((self.root / item).exists() for item in signals[name]):
                specs.append(spec)

        for name, relative in ADAPTER_SKILL_PATHS.items():
            if mode == "all" or (self.root / (".%s" % name)).exists() or (self.root / relative.split("/")[0]).exists():
                specs.append((relative, "owned", PROJECT_SKILL, name))
        return specs

    def _classify_adapter(self, relative: str, mode: str, body: str) -> Dict[str, Any]:
        path = self.root / relative
        if path.is_symlink():
            return {"path": relative, "action": "skip", "reason": "existing symlink"}
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if mode == "block":
            desired = merge_managed_block(existing, body)
            action = "unchanged" if desired == existing else ("modify" if path.exists() else "create")
            return {"path": relative, "action": action, "mode": mode, "desired": desired}
        desired = body.rstrip() + "\n"
        if not path.exists():
            action = "create"
        elif existing == desired:
            action = "unchanged"
        elif "name: agent-relay" in existing or MANAGED_START in existing:
            return {
                "path": relative,
                "action": "skip",
                "reason": "existing Agent Relay installation retained",
            }
        else:
            return {
                "path": relative,
                "action": "skip",
                "reason": "existing non-Relay file retained",
            }
        return {"path": relative, "action": action, "mode": mode, "desired": desired}

    def init_plan(self, adapters: str) -> Dict[str, Any]:
        operations = []
        directories = [
            "tasks",
            "events",
            "versions",
            "environments/shared",
            "environments/local",
            "runtime",
            "backups",
            "integrations/workbuddy",
        ]
        for relative in directories:
            path = self.state / relative
            operations.append(
                {
                    "path": "%s/%s/" % (STATE_DIR_NAME, relative),
                    "action": "unchanged" if path.is_dir() else "create",
                    "kind": "directory",
                }
            )
        source = Path(__file__).read_text(encoding="utf-8")
        runtime_action = "create"
        if self.runtime_path.exists():
            runtime_action = (
                "unchanged"
                if self.runtime_path.read_text(encoding="utf-8") == source
                else "modify"
            )
        operations.extend(
            [
                {"path": "%s/relay.py" % STATE_DIR_NAME, "action": runtime_action, "kind": "runtime"},
                {"path": "%s/config.json" % STATE_DIR_NAME, "action": "modify" if self.config_path.exists() else "create", "kind": "state"},
                {"path": "%s/goals.json" % STATE_DIR_NAME, "action": "unchanged" if self.goals_path.exists() else "create", "kind": "state"},
                {"path": "%s/HANDOFF.md" % STATE_DIR_NAME, "action": "modify" if self.handoff_path.exists() else "create", "kind": "state"},
                {
                    "path": "%s/integrations/workbuddy/README.md" % STATE_DIR_NAME,
                    "action": "unchanged" if (self.state / "integrations/workbuddy/README.md").exists() else "create",
                    "kind": "manual-adapter",
                },
            ]
        )
        for relative, adapter_mode, body, name in self._adapter_specs(adapters):
            item = self._classify_adapter(relative, adapter_mode, body)
            item.update({"kind": "adapter", "adapter": name})
            item.pop("desired", None)
            operations.append(item)
        return {
            "project_root": str(self.root),
            "runtime_version": VERSION,
            "adapter_mode": adapters,
            "operations": operations,
            "writes": sum(1 for item in operations if item["action"] in ("create", "modify")),
        }

    def _backup(self, path: Path, stamp: str) -> Optional[str]:
        if not path.exists() or path.is_symlink():
            return None
        relative = relative_path(self.root, path)
        backup = self.state / "backups" / stamp / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(backup))
        return relative_path(self.root, backup)

    def _write_adapter(
        self,
        relative: str,
        mode: str,
        body: str,
        name: str,
        stamp: str,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        info = self._classify_adapter(relative, mode, body)
        info["adapter"] = name
        if info["action"] == "skip":
            return info, None
        path = self.root / relative
        desired = info.pop("desired")
        created = not path.exists()
        backup = None
        if info["action"] == "modify":
            backup = self._backup(path, stamp)
        if info["action"] in ("create", "modify"):
            validate_destination(self.root, path)
            atomic_write(path, desired)
        record = {
            "mode": mode,
            "created": created,
            "sha256": sha256_bytes(desired.encode("utf-8")),
            "adapter": name,
        }
        if backup:
            record["backup"] = backup
        return info, record

    def _base_config(self, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = iso_now()
        existing = existing or {}
        return {
            "schema_version": SCHEMA_VERSION,
            "runtime_version": VERSION,
            "project_id": existing.get("project_id") or str(uuid.uuid4()),
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "installed": True,
            "adapter_mode": existing.get("adapter_mode", "auto"),
            "adapters": existing.get("adapters", []),
            "managed_files": existing.get("managed_files", {}),
            "current_environment": existing.get("current_environment"),
            "policy": {
                "lease_minutes": int(existing.get("policy", {}).get("lease_minutes", 120)),
                "record_hidden_reasoning": False,
                "record_full_conversations": False,
                "persist_secrets": False,
            },
        }

    def initialize(
        self,
        adapters: str,
        dry_run: bool,
        confirmed: bool,
        goal: Optional[str],
        harness: Optional[str],
        model: Optional[str],
        capabilities: Sequence[str],
    ) -> Dict[str, Any]:
        plan = self.init_plan(adapters)
        if dry_run:
            return {"dry_run": True, **plan}
        if not confirmed:
            raise RelayError("Initialization requires --yes after reviewing init --dry-run")
        if self.root == Path.home().resolve():
            raise RelayError("Refusing to initialize the home directory as a project")

        for relative in (
            "tasks",
            "events",
            "versions",
            "environments/shared",
            "environments/local",
            "runtime",
            "backups",
            "integrations/workbuddy",
        ):
            (self.state / relative).mkdir(parents=True, exist_ok=True)

        with StateLock(self.lock_path):
            previous = load_json(self.config_path, {})
            if previous and not isinstance(previous, dict):
                raise RelayError("Existing config.json is not an object")
            config = self._base_config(previous)
            first_install = not bool(previous)
            stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
            managed = dict(config.get("managed_files", {}))
            installed_adapters = {item.get("path"): item for item in config.get("adapters", []) if item.get("path")}
            actions = []

            source = Path(__file__).read_text(encoding="utf-8")
            if not self.runtime_path.exists() or self.runtime_path.read_text(encoding="utf-8") != source:
                atomic_write(self.runtime_path, source, 0o755)
                actions.append({"path": "%s/relay.py" % STATE_DIR_NAME, "action": "written"})

            if not self.goals_path.exists():
                atomic_write(
                    self.goals_path,
                    json_text({"schema_version": SCHEMA_VERSION, "goals": [], "updated_at": iso_now()}),
                )
            workbuddy_guide = self.state / "integrations" / "workbuddy" / "README.md"
            if not workbuddy_guide.exists():
                atomic_write(workbuddy_guide, WORKBUDDY_GUIDE.rstrip() + "\n")
            for relative, adapter_mode, body, name in self._adapter_specs(adapters):
                info, record = self._write_adapter(relative, adapter_mode, body, name, stamp)
                actions.append({k: v for k, v in info.items() if k != "mode"})
                installed_adapters[relative] = {
                    "path": relative,
                    "name": name,
                    "status": "installed" if info["action"] != "skip" else "external",
                }
                if record:
                    managed[relative] = record

            env_id = self._capture_environment(harness, model, capabilities)
            config.update(
                {
                    "runtime_version": VERSION,
                    "updated_at": iso_now(),
                    "installed": True,
                    "adapter_mode": adapters,
                    "adapters": sorted(installed_adapters.values(), key=lambda item: item["path"]),
                    "managed_files": managed,
                    "current_environment": env_id,
                }
            )
            atomic_write(self.config_path, json_text(config))
            if goal:
                self._add_goal_unlocked(goal, "explicit", "long-term", create_event=False)
            event = self._write_event_unlocked(
                "initialized" if first_install else "reinitialized",
                {
                    "summary": "Installed Agent Relay project capability" if first_install else "Refreshed Agent Relay project capability",
                    "adapter_mode": adapters,
                    "environment_id": env_id,
                    "actions": actions,
                    "next_step": "Review .agent-relay/HANDOFF.md, then start the first task",
                },
            )
            self._refresh_handoff_unlocked(event["id"])
            return {
                "dry_run": False,
                "project_root": str(self.root),
                "runtime_version": VERSION,
                "event_id": event["id"],
                "environment_id": env_id,
                "actions": actions,
                "doctor_command": "python3 .agent-relay/relay.py doctor",
            }

    def _detect_harness(self, explicit: Optional[str]) -> str:
        if explicit:
            return redact_string(explicit)[:120]
        if os.environ.get("AGENT_RELAY_HARNESS"):
            return redact_string(os.environ["AGENT_RELAY_HARNESS"])[:120]
        if os.environ.get("PI_AGENT_HOST"):
            return "Pi"
        if os.environ.get("CLAUDE_CODE") or os.environ.get("CLAUDE_SESSION_ID"):
            return "Claude Code"
        return "unknown"

    def _detect_model(self, explicit: Optional[str]) -> str:
        value = explicit or os.environ.get("PI_MODEL") or os.environ.get("AGENT_RELAY_MODEL")
        return redact_string(value)[:120] if value else "unknown"

    def _capture_environment(
        self,
        harness: Optional[str],
        model: Optional[str],
        capabilities: Sequence[str],
    ) -> str:
        git_path = shutil.which("git")
        git_code, git_version = run_command(["git", "--version"], self.root) if git_path else (127, "")
        shared = sanitize(
            {
                "schema_version": SCHEMA_VERSION,
                "os": {
                    "system": platform.system() or "unknown",
                    "release": platform.release() or "unknown",
                    "architecture": platform.machine() or "unknown",
                },
                "python": platform.python_version(),
                "git": git_version if git_code == 0 else "unavailable",
                "harness": self._detect_harness(harness),
                "model": self._detect_model(model),
                "capabilities": sorted(set(redact_string(item)[:80] for item in capabilities)),
            }
        )
        fingerprint = sha256_bytes(json.dumps(shared, sort_keys=True).encode("utf-8"))[:16]
        env_id = "env-%s" % fingerprint
        shared_payload = dict(shared)
        shared_payload.update({"id": env_id, "captured_at": iso_now()})
        shared_path = self.environments_dir / "shared" / (env_id + ".json")
        if not shared_path.exists():
            atomic_write(shared_path, json_text(shared_payload))
        local_payload = sanitize(
            {
                "schema_version": SCHEMA_VERSION,
                "environment_id": env_id,
                "captured_at": iso_now(),
                "project_root": str(self.root),
                "python_executable": sys.executable,
                "git_executable": git_path or "unavailable",
            }
        )
        atomic_write(self.environments_dir / "local" / "current.json", json_text(local_payload))
        return env_id

    def _write_event_unlocked(self, event_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
        now = iso_now()
        event_id = "event-%s-%s" % (
            utc_now().strftime("%Y%m%dT%H%M%S%fZ"),
            uuid.uuid4().hex[:8],
        )
        payload = sanitize(
            {
                "schema_version": SCHEMA_VERSION,
                "id": event_id,
                "type": event_type,
                "created_at": now,
                **details,
            }
        )
        atomic_write(self.events_dir / (event_id + ".json"), json_text(payload))
        return payload

    def _load_items(self, directory: Path, pattern: str = "*.json") -> List[Dict[str, Any]]:
        items = []
        if not directory.exists():
            return items
        for path in sorted(directory.glob(pattern)):
            value = load_json(path)
            if isinstance(value, dict):
                items.append(value)
        return items

    def _load_tasks(self) -> List[Dict[str, Any]]:
        return self._load_items(self.tasks_dir)

    def _load_events(self) -> List[Dict[str, Any]]:
        return self._load_items(self.events_dir)

    def _load_versions(self) -> List[Dict[str, Any]]:
        versions = []
        if not self.versions_dir.exists():
            return versions
        for path in sorted(self.versions_dir.glob("v[0-9][0-9][0-9]/manifest.json")):
            value = load_json(path)
            if isinstance(value, dict):
                versions.append(value)
        return versions

    def _goals(self) -> Dict[str, Any]:
        value = load_json(
            self.goals_path,
            {"schema_version": SCHEMA_VERSION, "goals": [], "updated_at": iso_now()},
        )
        if not isinstance(value, dict) or not isinstance(value.get("goals", []), list):
            raise RelayError("Invalid goals.json")
        return value

    def _save_config(self, config: Dict[str, Any]) -> None:
        config["updated_at"] = iso_now()
        atomic_write(self.config_path, json_text(sanitize(config)))

    def _add_goal_unlocked(
        self,
        text: str,
        kind: str,
        scope: str,
        create_event: bool = True,
    ) -> Dict[str, Any]:
        cleaned = redact_string(text).strip()
        if not cleaned:
            raise RelayError("Goal text cannot be empty")
        data = self._goals()
        for goal in data["goals"]:
            if goal.get("status") == "active" and goal.get("text") == cleaned:
                return goal
        now = iso_now()
        goal = {
            "id": "goal-%s-%s" % (utc_now().strftime("%Y%m%d"), uuid.uuid4().hex[:6]),
            "text": cleaned,
            "kind": kind,
            "scope": scope,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        data["goals"].append(goal)
        data["updated_at"] = now
        atomic_write(self.goals_path, json_text(sanitize(data)))
        if create_event:
            self._write_event_unlocked(
                "goal-added",
                {
                    "goal_id": goal["id"],
                    "summary": "Added %s %s goal: %s" % (kind, scope, cleaned),
                    "next_step": "Use the goal as context; the current user request still takes priority",
                },
            )
        return goal

    def add_goal(self, text: str, kind: str, scope: str) -> Dict[str, Any]:
        self.require_initialized()
        with StateLock(self.lock_path):
            goal = self._add_goal_unlocked(text, kind, scope)
            events = self._load_events()
            self._refresh_handoff_unlocked(events[-1]["id"] if events else "none")
            return goal

    def complete_goal(self, goal_id: str, status: str) -> Dict[str, Any]:
        self.require_initialized()
        with StateLock(self.lock_path):
            data = self._goals()
            goal = next((item for item in data["goals"] if item.get("id") == goal_id), None)
            if not goal:
                raise RelayError("Unknown goal: %s" % goal_id)
            goal["status"] = status
            goal["updated_at"] = iso_now()
            data["updated_at"] = iso_now()
            atomic_write(self.goals_path, json_text(sanitize(data)))
            event = self._write_event_unlocked(
                "goal-updated",
                {
                    "goal_id": goal_id,
                    "summary": "Goal marked %s: %s" % (status, goal.get("text", "")),
                    "next_step": "Continue with the user's current request",
                },
            )
            self._refresh_handoff_unlocked(event["id"])
            return goal

    def _task_path(self, task_id: str) -> Path:
        if not re.fullmatch(r"task-[a-z0-9-]+", task_id):
            raise RelayError("Invalid task ID: %s" % task_id)
        return self.tasks_dir / (task_id + ".json")

    def _is_expired(self, task: Dict[str, Any]) -> bool:
        expiry = parse_time(task.get("lease_expires_at"))
        return bool(task.get("status") == "active" and expiry and expiry < utc_now())

    def _resolve_task(self, task_id: Optional[str]) -> Tuple[Path, Dict[str, Any]]:
        if task_id:
            path = self._task_path(task_id)
            task = load_json(path)
            if not isinstance(task, dict):
                raise RelayError("Unknown task: %s" % task_id)
            return path, task
        active = [task for task in self._load_tasks() if task.get("status") == "active"]
        if len(active) != 1:
            raise RelayError("Specify --task-id when there is not exactly one active task")
        task = active[0]
        return self._task_path(task["id"]), task

    def start_task(
        self,
        title: str,
        owner: Optional[str],
        scopes: Sequence[str],
        lease_minutes: Optional[int],
        harness: Optional[str],
        model: Optional[str],
        capabilities: Sequence[str],
        goal: Optional[str],
    ) -> Dict[str, Any]:
        config = self.require_initialized()
        clean_title = redact_string(title).strip()
        if not clean_title:
            raise RelayError("Task title cannot be empty")
        normalized = sorted(set(normalize_scope(self.root, item) for item in scopes))
        lease = int(lease_minutes or config.get("policy", {}).get("lease_minutes", 120))
        if lease < 5 or lease > 1440:
            raise RelayError("Lease must be between 5 and 1440 minutes")
        detected_harness = self._detect_harness(harness)
        session = os.environ.get("PI_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")
        default_owner = detected_harness + (":" + session[:12] if session else "")
        clean_owner = redact_string(owner or default_owner)[:160]

        with StateLock(self.lock_path):
            tasks = self._load_tasks()
            expired = []
            conflicts = []
            for task in tasks:
                if task.get("status") != "active":
                    continue
                if self._is_expired(task):
                    expired.append(task)
                    continue
                for left in normalized:
                    for right in task.get("write_scopes", []):
                        if scopes_overlap(left, right):
                            conflicts.append(
                                {
                                    "task_id": task.get("id"),
                                    "owner": task.get("owner"),
                                    "requested": left,
                                    "claimed": right,
                                    "lease_expires_at": task.get("lease_expires_at"),
                                }
                            )
            if conflicts:
                details = "; ".join(
                    "%s owns %s until %s"
                    % (item["task_id"], item["claimed"], item["lease_expires_at"])
                    for item in conflicts
                )
                raise RelayError("Write-scope conflict: %s" % details)

            for expired_task in expired:
                expired_task["status"] = "expired"
                expired_task["updated_at"] = iso_now()
                atomic_write(
                    self._task_path(expired_task["id"]),
                    json_text(sanitize(expired_task)),
                )
            env_id = self._capture_environment(harness, model, capabilities)
            config["current_environment"] = env_id
            self._save_config(config)
            if goal:
                self._add_goal_unlocked(goal, "explicit", "short-term", create_event=False)
            now = utc_now()
            task_id = "task-%s-%s-%s" % (
                now.strftime("%Y%m%d"),
                safe_slug(clean_title),
                uuid.uuid4().hex[:6],
            )
            task = sanitize(
                {
                    "schema_version": SCHEMA_VERSION,
                    "id": task_id,
                    "title": clean_title,
                    "owner": clean_owner,
                    "status": "active",
                    "created_at": iso_now(),
                    "updated_at": iso_now(),
                    "lease_expires_at": (now + dt.timedelta(minutes=lease))
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "write_scopes": normalized,
                    "environment_id": env_id,
                    "summary": "",
                    "changed_files": [],
                    "verification": [],
                    "blockers": [],
                    "next_step": "Execute and verify the current user request",
                }
            )
            atomic_write(self._task_path(task_id), json_text(task))
            event = self._write_event_unlocked(
                "task-started",
                {
                    "task_id": task_id,
                    "owner": clean_owner,
                    "summary": clean_title,
                    "write_scopes": normalized,
                    "environment_id": env_id,
                    "expired_tasks_observed": [item["id"] for item in expired],
                    "next_step": task["next_step"],
                },
            )
            self._refresh_handoff_unlocked(event["id"])
            return task

    def update_task(
        self,
        command: str,
        task_id: Optional[str],
        summary: str,
        changed: Sequence[str],
        verification: Sequence[str],
        blockers: Sequence[str],
        next_step: Optional[str],
        status: Optional[str],
        lease_minutes: Optional[int],
    ) -> Dict[str, Any]:
        config = self.require_initialized()
        with StateLock(self.lock_path):
            path, task = self._resolve_task(task_id)
            if task.get("status") != "active":
                raise RelayError("Cannot update task in status %s" % task.get("status"))
            if self._is_expired(task):
                raise RelayError("Task lease expired; start a new task or record an audited takeover")
            clean_changed = sorted(
                set(normalize_scope(self.root, item) for item in changed)
            )
            task["summary"] = redact_string(summary).strip()
            task["changed_files"] = sorted(
                set(task.get("changed_files", []) + clean_changed)
            )
            task["verification"] = list(
                dict.fromkeys(task.get("verification", []) + [redact_string(item) for item in verification])
            )
            task["blockers"] = list(
                dict.fromkeys(task.get("blockers", []) + [redact_string(item) for item in blockers])
            )
            task["next_step"] = redact_string(next_step or task.get("next_step") or "")
            task["updated_at"] = iso_now()
            if command == "checkpoint":
                lease = int(lease_minutes or config.get("policy", {}).get("lease_minutes", 120))
                if lease < 5 or lease > 1440:
                    raise RelayError("Lease must be between 5 and 1440 minutes")
                task["lease_expires_at"] = (
                    utc_now() + dt.timedelta(minutes=lease)
                ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                event_type = "task-checkpoint"
            else:
                task["status"] = status or "completed"
                task["lease_expires_at"] = None
                event_type = "task-finished"
            atomic_write(path, json_text(sanitize(task)))
            event = self._write_event_unlocked(
                event_type,
                {
                    "task_id": task["id"],
                    "owner": task.get("owner"),
                    "status": task.get("status"),
                    "summary": task.get("summary"),
                    "changed_files": task.get("changed_files", []),
                    "verification": task.get("verification", []),
                    "blockers": task.get("blockers", []),
                    "next_step": task.get("next_step"),
                    "environment_id": task.get("environment_id"),
                },
            )
            self._refresh_handoff_unlocked(event["id"])
            return {"task": task, "event_id": event["id"]}

    def _render_handoff(self, source_event_id: str) -> str:
        goals = [goal for goal in self._goals()["goals"] if goal.get("status") == "active"]
        tasks = self._load_tasks()
        active = [task for task in tasks if task.get("status") == "active"]
        events = self._load_events()
        versions = self._load_versions()
        finished = [event for event in events if event.get("type") == "task-finished"]
        goal_text = goals[0].get("text") if goals else "Not recorded"
        lines = [
            "# Agent Relay Handoff",
            "",
            "> Generated from canonical state. The current user request always takes priority over stored goals.",
            "",
            "## Project goal",
            "",
            "- %s" % goal_text,
            "",
            "## Active tasks",
            "",
        ]
        if active:
            for task in active[:8]:
                scopes = ", ".join("`%s`" % item for item in task.get("write_scopes", [])) or "read-only"
                lines.append(
                    "- `%s` · %s · %s · scopes: %s · lease: %s"
                    % (
                        task.get("id"),
                        task.get("title"),
                        task.get("owner"),
                        scopes,
                        task.get("lease_expires_at"),
                    )
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Last completed", ""])
        if finished:
            last = finished[-1]
            verification = "; ".join(last.get("verification", [])) or "not recorded"
            lines.append("- %s" % (last.get("summary") or "Completed task"))
            lines.append("- Verification: %s" % verification)
        else:
            lines.append("- No completed task recorded")
        lines.extend(["", "## Version state", ""])
        if versions:
            version = versions[-1]
            lines.append(
                "- `%s` · %s · sealed %s"
                % (version.get("version"), version.get("label") or "unlabeled", version.get("sealed_at"))
            )
        else:
            lines.append("- No sealed version")
        blockers = []
        for task in active:
            blockers.extend(task.get("blockers", []))
            if self._is_expired(task):
                blockers.append("Expired lease: %s" % task.get("id"))
        lines.extend(["", "## Blockers and next step", ""])
        lines.append("- Blockers: %s" % ("; ".join(blockers) if blockers else "None"))
        next_step = next((task.get("next_step") for task in active if task.get("next_step")), None)
        if not next_step and events:
            next_step = events[-1].get("next_step")
        lines.append("- Next: %s" % (next_step or "Start from the user's current request"))
        config = load_json(self.config_path, {})
        lines.extend(
            [
                "",
                "## Environment and freshness",
                "",
                "- Environment: `%s`" % (config.get("current_environment") or "unknown"),
                "- Updated: %s from `%s`" % (iso_now(), source_event_id),
                "",
            ]
        )
        return "\n".join(lines)

    def _refresh_handoff_unlocked(self, source_event_id: str) -> None:
        atomic_write(self.handoff_path, self._render_handoff(source_event_id))

    def _version_storage_size(self) -> int:
        total = 0
        if not self.versions_dir.exists():
            return total
        for path in self.versions_dir.rglob("*"):
            if path.is_file() and not path.is_symlink():
                with contextlib.suppress(OSError):
                    total += path.stat().st_size
        return total

    def report_data(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {
                "schema_version": SCHEMA_VERSION,
                "health": "uninitialized",
                "project": self.root.name,
                "project_goal": "Not recorded",
                "active_work": [],
                "last_completed": None,
                "version_state": {"latest": None, "unsealed_changes": "unknown", "storage_bytes": 0},
                "environment": None,
                "blockers": ["Agent Relay is not initialized"],
                "next_step": "Run init --dry-run",
                "updated_at": None,
                "source_event_id": None,
                "issues": ["missing .agent-relay/config.json"],
            }
        issues = []
        stale = []
        try:
            config = self.require_initialized()
            goals = [goal for goal in self._goals()["goals"] if goal.get("status") == "active"]
            tasks = self._load_tasks()
            events = self._load_events()
            versions = self._load_versions()
        except RelayError as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "health": "degraded",
                "project": self.root.name,
                "project_goal": "Unknown",
                "active_work": [],
                "last_completed": None,
                "version_state": {"latest": None, "unsealed_changes": "unknown", "storage_bytes": 0},
                "environment": None,
                "blockers": [str(exc)],
                "next_step": "Run doctor and repair invalid state",
                "updated_at": None,
                "source_event_id": None,
                "issues": [str(exc)],
            }
        active = [task for task in tasks if task.get("status") == "active"]
        for task in active:
            if self._is_expired(task):
                stale.append("expired lease: %s" % task.get("id"))
        if not self.handoff_path.exists():
            issues.append("missing HANDOFF.md")
        agents_path = self.root / "AGENTS.md"
        if not agents_path.exists():
            issues.append("missing AGENTS.md managed entry")
        else:
            try:
                if MANAGED_START not in agents_path.read_text(encoding="utf-8"):
                    issues.append("missing AGENTS.md managed entry")
            except (OSError, UnicodeDecodeError):
                issues.append("unreadable AGENTS.md")
        latest_event = events[-1] if events else None
        if latest_event and self.handoff_path.exists():
            event_time = parse_time(latest_event.get("created_at"))
            handoff_time = dt.datetime.fromtimestamp(self.handoff_path.stat().st_mtime, dt.timezone.utc)
            if event_time and handoff_time + dt.timedelta(seconds=1) < event_time:
                stale.append("HANDOFF.md is older than the latest event")
        finished = [event for event in events if event.get("type") == "task-finished"]
        latest_version = versions[-1] if versions else None
        git_code, git_output = run_command(["git", "--no-optional-locks", "status", "--porcelain"], self.root)
        unsealed = len(git_output.splitlines()) if git_code == 0 and git_output else (0 if git_code == 0 else "unknown")
        env = None
        env_id = config.get("current_environment")
        if env_id:
            if not isinstance(env_id, str) or not re.fullmatch(r"env-[0-9a-f]{16}", env_id):
                issues.append("invalid current environment ID")
            else:
                try:
                    env = load_json(self.environments_dir / "shared" / (env_id + ".json"), None)
                except RelayError as exc:
                    env = None
                    issues.append(str(exc))
                if env is None and not any("environment" in item for item in issues):
                    issues.append("missing current environment snapshot")
        blockers = []
        for task in active:
            blockers.extend(task.get("blockers", []))
        blockers.extend(stale)
        health = "degraded" if issues else ("stale" if stale else "healthy")
        next_step = next((task.get("next_step") for task in active if task.get("next_step")), None)
        if not next_step and latest_event:
            next_step = latest_event.get("next_step")
        return sanitize(
            {
                "schema_version": SCHEMA_VERSION,
                "health": health,
                "project": self.root.name,
                "project_goal": goals[0].get("text") if goals else "Not recorded",
                "goals": goals,
                "active_work": active,
                "last_completed": finished[-1] if finished else None,
                "version_state": {
                    "latest": latest_version,
                    "unsealed_changes": unsealed,
                    "storage_bytes": self._version_storage_size(),
                },
                "environment": env,
                "blockers": blockers,
                "next_step": next_step or "Start from the user's current request",
                "updated_at": latest_event.get("created_at") if latest_event else config.get("updated_at"),
                "source_event_id": latest_event.get("id") if latest_event else None,
                "issues": issues + stale,
                "adapters": config.get("adapters", []),
            }
        )

    def render_report(self, data: Dict[str, Any], full: bool = False) -> str:
        active = data.get("active_work", [])
        if active:
            work = "; ".join(
                "%s · %s · %s"
                % (item.get("id"), item.get("owner"), ", ".join(item.get("write_scopes", [])) or "read-only")
                for item in active[:4]
            )
        else:
            work = "None"
        completed = data.get("last_completed") or {}
        completed_text = completed.get("summary") or "None"
        latest = data.get("version_state", {}).get("latest") or {}
        unsealed = data.get("version_state", {}).get("unsealed_changes")
        version_text = "%s; unsealed changes: %s; storage: %s" % (
            latest.get("version") or "none",
            unsealed,
            format_bytes(int(data.get("version_state", {}).get("storage_bytes", 0))),
        )
        environment = data.get("environment") or {}
        env_text = "%s · %s · %s" % (
            environment.get("harness", "unknown"),
            environment.get("model", "unknown"),
            ", ".join(environment.get("capabilities", [])) or "capabilities not recorded",
        )
        lines = [
            "Agent Relay report",
            "Health: %s" % data.get("health"),
            "Project goal: %s" % data.get("project_goal"),
            "Active work: %s" % work,
            "Last completed: %s" % completed_text,
            "Version state: %s" % version_text,
            "Environment: %s" % env_text,
            "Blockers: %s" % ("; ".join(data.get("blockers", [])) or "None"),
            "Next step: %s" % data.get("next_step"),
            "Updated: %s · %s" % (data.get("updated_at") or "unknown", data.get("source_event_id") or "no event"),
        ]
        if full:
            lines.extend(
                [
                    "",
                    "Goals:",
                    json.dumps(data.get("goals", []), ensure_ascii=False, indent=2),
                    "",
                    "Active tasks:",
                    json.dumps(active, ensure_ascii=False, indent=2),
                    "",
                    "Adapters:",
                    json.dumps(data.get("adapters", []), ensure_ascii=False, indent=2),
                    "",
                    "Issues:",
                    json.dumps(data.get("issues", []), ensure_ascii=False, indent=2),
                ]
            )
        return "\n".join(lines)

    def status_data(self) -> Dict[str, Any]:
        config = self.require_initialized()
        return sanitize(
            {
                "schema_version": SCHEMA_VERSION,
                "runtime_version": VERSION,
                "project": self.root.name,
                "goals": self._goals()["goals"],
                "tasks": self._load_tasks(),
                "recent_events": self._load_events()[-10:],
                "versions": self._load_versions(),
                "environment_id": config.get("current_environment"),
                "adapters": config.get("adapters", []),
            }
        )

    def _next_version(self) -> str:
        numbers = []
        if self.versions_dir.exists():
            for path in self.versions_dir.iterdir():
                match = re.fullmatch(r"v(\d{3})", path.name)
                if match and path.is_dir():
                    numbers.append(int(match.group(1)))
        return "v%03d" % ((max(numbers) if numbers else 0) + 1)

    def _collect_artifacts(
        self, values: Sequence[str], max_bytes: int
    ) -> Tuple[List[Tuple[Path, str]], int]:
        files = []
        total = 0
        seen = set()
        for value in values:
            requested = self.root / value if not Path(value).is_absolute() else Path(value)
            if requested.is_symlink():
                raise RelayError("Symlink artifacts are not supported: %s" % value)
            candidate = requested.resolve()
            relative = relative_path(self.root, candidate)
            if candidate == self.root or relative == STATE_DIR_NAME or relative.startswith(STATE_DIR_NAME + "/"):
                raise RelayError("Artifact scope cannot include the project root or .agent-relay")
            if not candidate.exists():
                raise RelayError("Artifact does not exist: %s" % value)
            if candidate.is_symlink():
                raise RelayError("Symlink artifacts are not supported: %s" % value)
            candidates = [candidate] if candidate.is_file() else sorted(candidate.rglob("*"))
            for path in candidates:
                rel = relative_path(self.root, path)
                parts = PurePosixPath(rel).parts
                if ".git" in parts or STATE_DIR_NAME in parts:
                    continue
                if path.is_symlink():
                    raise RelayError("Artifact tree contains a symlink: %s" % rel)
                if not path.is_file() or rel in seen:
                    continue
                size = path.stat().st_size
                total += size
                if total > max_bytes:
                    raise RelayError(
                        "Artifact selection exceeds %s; narrow the scope or raise --max-bytes"
                        % format_bytes(max_bytes)
                    )
                seen.add(rel)
                files.append((path, rel))
        return files, total

    def seal(
        self,
        artifacts: Sequence[str],
        label: Optional[str],
        summary: Optional[str],
        dry_run: bool,
        confirmed: bool,
        max_bytes: int,
    ) -> Dict[str, Any]:
        self.require_initialized()
        if max_bytes <= 0:
            raise RelayError("--max-bytes must be greater than zero")
        files, total = self._collect_artifacts(artifacts, max_bytes)
        git_code, git_head = run_command(["git", "rev-parse", "HEAD"], self.root)
        if not files and git_code != 0:
            raise RelayError("Select at least one --artifact when Git metadata is unavailable")
        version = self._next_version()
        plan = {
            "version": version,
            "label": redact_string(label or ""),
            "artifacts": [relative for _, relative in files],
            "artifact_bytes": total,
            "git_reference": git_head if git_code == 0 else None,
        }
        if dry_run:
            return {"dry_run": True, **plan}
        if not confirmed:
            raise RelayError("Sealing requires --yes after explicit finalization and scope confirmation")

        with StateLock(self.lock_path):
            version = self._next_version()
            final_dir = self.versions_dir / version
            if final_dir.exists():
                raise RelayError("Version already exists: %s" % version)
            temp_dir = self.versions_dir / (".%s.tmp-%s" % (version, uuid.uuid4().hex[:8]))
            temp_dir.mkdir(parents=True, exist_ok=False)
            checksums = []
            try:
                for source, relative in files:
                    destination = temp_dir / "artifacts" / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(source), str(destination))
                    checksums.append(
                        {
                            "path": relative,
                            "bytes": destination.stat().st_size,
                            "sha256": sha256_file(destination),
                        }
                    )
                git_status_code, git_status = run_command(["git", "status", "--porcelain"], self.root)
                events = self._load_events()
                previous = self._load_versions()
                previous_time = parse_time(previous[-1].get("sealed_at")) if previous else None
                source_events = []
                for event in events:
                    event_time = parse_time(event.get("created_at"))
                    if not previous_time or (event_time and event_time > previous_time):
                        source_events.append(event.get("id"))
                manifest = sanitize(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "runtime_version": VERSION,
                        "version": version,
                        "label": redact_string(label or "") or None,
                        "summary": redact_string(summary or "") or None,
                        "sealed_at": iso_now(),
                        "git": {
                            "head": git_head if git_code == 0 else None,
                            "dirty": bool(git_status) if git_status_code == 0 else None,
                            "changed_entries": len(git_status.splitlines()) if git_status_code == 0 and git_status else 0,
                        },
                        "artifacts": checksums,
                        "artifact_bytes": total,
                        "source_event_ids": source_events,
                    }
                )
                atomic_write(temp_dir / "manifest.json", json_text(manifest))
                os.replace(str(temp_dir), str(final_dir))
            except Exception:
                shutil.rmtree(str(temp_dir), ignore_errors=True)
                raise
            event = self._write_event_unlocked(
                "version-sealed",
                {
                    "version": version,
                    "summary": manifest.get("summary") or "Sealed %s" % version,
                    "artifact_paths": [item["path"] for item in checksums],
                    "artifact_bytes": total,
                    "verification": ["SHA-256 recorded for %d artifact(s)" % len(checksums)],
                    "next_step": "Continue work in the editable project; do not overwrite the sealed version",
                },
            )
            self._refresh_handoff_unlocked(event["id"])
            return {"dry_run": False, **manifest, "event_id": event["id"]}

    def doctor(self) -> Dict[str, Any]:
        checks = []

        def add(name: str, status: str, detail: str) -> None:
            checks.append({"name": name, "status": status, "detail": detail})

        if sys.version_info < (3, 9):
            add("python", "fail", "Python 3.9 or newer is required")
        else:
            add("python", "pass", platform.python_version())
        if not self.config_path.exists():
            add("initialization", "fail", "Missing .agent-relay/config.json")
            return {"health": "uninitialized", "runtime_version": VERSION, "checks": checks}
        try:
            config = load_json(self.config_path)
            if not isinstance(config, dict):
                add("schema", "fail", "config.json must contain an object")
                return {"health": "degraded", "runtime_version": VERSION, "checks": checks}
            if config.get("schema_version") != SCHEMA_VERSION:
                add("schema", "fail", "Unsupported config schema")
            elif config.get("installed") is False:
                add("initialization", "fail", "Project capability is uninstalled")
            else:
                add("schema", "pass", "schema %s" % SCHEMA_VERSION)
        except RelayError as exc:
            add("config", "fail", str(exc))
            return {"health": "degraded", "runtime_version": VERSION, "checks": checks}

        required = [
            self.tasks_dir,
            self.events_dir,
            self.versions_dir,
            self.environments_dir / "shared",
            self.environments_dir / "local",
            self.state / "runtime",
        ]
        missing = [relative_path(self.root, path) for path in required if not path.is_dir()]
        add("state-directories", "fail" if missing else "pass", ", ".join(missing) if missing else "all present")
        add(
            "runtime",
            "pass" if self.runtime_path.exists() else "fail",
            "project-local relay.py present" if self.runtime_path.exists() else "missing .agent-relay/relay.py",
        )
        add(
            "handoff",
            "pass" if self.handoff_path.exists() else "fail",
            "HANDOFF.md present" if self.handoff_path.exists() else "missing HANDOFF.md",
        )
        try:
            self._goals()
            self._load_tasks()
            self._load_events()
            self._load_versions()
            add("state-json", "pass", "canonical JSON files parse")
        except RelayError as exc:
            add("state-json", "fail", str(exc))

        managed_files = config.get("managed_files", {})
        if not isinstance(managed_files, dict):
            add("managed-files", "fail", "config managed_files must be an object")
            managed_files = {}
        for relative, record in managed_files.items():
            if not isinstance(record, dict):
                add("adapter:%s" % relative, "fail", "managed file record must be an object")
                continue
            try:
                path = project_member(self.root, relative)
            except RelayError as exc:
                add("adapter:%s" % relative, "fail", str(exc))
                continue
            if path.is_symlink():
                add("adapter:%s" % relative, "fail", "managed path is a symlink")
                continue
            if not path.exists():
                add("adapter:%s" % relative, "fail", "managed path missing")
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                add("adapter:%s" % relative, "fail", str(exc))
                continue
            if record.get("mode") == "block":
                okay = text.count(MANAGED_START) == 1 and text.count(MANAGED_END) == 1
                add("adapter:%s" % relative, "pass" if okay else "fail", "managed block present" if okay else "managed block missing or duplicated")
            else:
                actual = sha256_bytes(text.encode("utf-8"))
                okay = actual == record.get("sha256")
                add("adapter:%s" % relative, "pass" if okay else "warn", "owned adapter unchanged" if okay else "owned adapter has local edits")

        checksum_failures = []
        for manifest in self._load_versions():
            version = manifest.get("version")
            if not isinstance(version, str) or not re.fullmatch(r"v[0-9]{3}", version):
                checksum_failures.append("invalid-version-field")
                continue
            artifact_root = self.versions_dir / version / "artifacts"
            for artifact in manifest.get("artifacts", []):
                artifact_name = artifact.get("path", "") if isinstance(artifact, dict) else ""
                try:
                    path = project_member(artifact_root, artifact_name)
                    if path.is_symlink():
                        raise RelayError("artifact is a symlink")
                    relative_path(artifact_root, path)
                except RelayError:
                    checksum_failures.append("%s:%s" % (version, artifact_name or "invalid-path"))
                    continue
                if not path.exists() or sha256_file(path) != artifact.get("sha256"):
                    checksum_failures.append("%s:%s" % (version, artifact_name))
        add(
            "sealed-versions",
            "fail" if checksum_failures else "pass",
            ", ".join(checksum_failures) if checksum_failures else "artifact checksums valid",
        )

        secret_hits = []
        scan_paths = [self.config_path, self.goals_path, self.handoff_path]
        scan_paths.extend(self.tasks_dir.glob("*.json"))
        scan_paths.extend(self.events_dir.glob("*.json"))
        scan_paths.extend((self.environments_dir / "shared").glob("*.json"))
        for path in scan_paths:
            if not path.exists() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if PRIVATE_KEY_RE.search(text) or TOKEN_VALUE_RE.search(text):
                secret_hits.append(relative_path(self.root, path))
        add(
            "secret-scan",
            "fail" if secret_hits else "pass",
            ", ".join(secret_hits) if secret_hits else "no private-key or common token pattern found",
        )
        failures = [item for item in checks if item["status"] == "fail"]
        warnings = [item for item in checks if item["status"] == "warn"]
        return {
            "health": "degraded" if failures else ("warning" if warnings else "healthy"),
            "runtime_version": VERSION,
            "checks": checks,
            "failures": len(failures),
            "warnings": len(warnings),
        }

    def uninstall_plan(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise RelayError("Agent Relay is not initialized")
        config = load_json(self.config_path)
        if not isinstance(config, dict):
            raise RelayError("config.json must contain an object")
        managed_files = config.get("managed_files", {})
        if not isinstance(managed_files, dict):
            raise RelayError("config managed_files must be an object")
        operations = []
        for relative, record in sorted(managed_files.items()):
            if not isinstance(record, dict):
                raise RelayError("Invalid managed file record: %s" % relative)
            path = self.root / relative
            operations.append(
                {
                    "path": relative,
                    "action": "remove-managed-block" if record.get("mode") == "block" else "remove-if-unchanged",
                    "exists": path.exists(),
                }
            )
        operations.append({"path": "%s/relay.py" % STATE_DIR_NAME, "action": "remove-runtime", "exists": self.runtime_path.exists()})
        return {
            "project_root": str(self.root),
            "operations": operations,
            "preserved": [
                "%s/events/" % STATE_DIR_NAME,
                "%s/versions/" % STATE_DIR_NAME,
                "%s/goals.json" % STATE_DIR_NAME,
                "%s/backups/" % STATE_DIR_NAME,
            ],
        }

    def uninstall(self, dry_run: bool, confirmed: bool) -> Dict[str, Any]:
        plan = self.uninstall_plan()
        if dry_run:
            return {"dry_run": True, **plan}
        if not confirmed:
            raise RelayError("Uninstall requires --yes after reviewing uninstall --dry-run")
        with StateLock(self.lock_path):
            config = load_json(self.config_path)
            if not isinstance(config, dict):
                raise RelayError("config.json must contain an object")
            managed_files = config.get("managed_files", {})
            if not isinstance(managed_files, dict):
                raise RelayError("config managed_files must be an object")
            remaining = {}
            results = []
            for relative, record in sorted(managed_files.items()):
                if not isinstance(record, dict):
                    results.append({"path": relative, "action": "preserved", "reason": "invalid managed file record"})
                    remaining[relative] = record
                    continue
                try:
                    path = project_member(self.root, relative)
                except RelayError as exc:
                    results.append({"path": relative, "action": "preserved", "reason": str(exc)})
                    remaining[relative] = record
                    continue
                if not path.exists():
                    results.append({"path": relative, "action": "already-missing"})
                    continue
                if path.is_symlink():
                    results.append({"path": relative, "action": "preserved", "reason": "symlink"})
                    remaining[relative] = record
                    continue
                text = path.read_text(encoding="utf-8")
                if record.get("mode") == "block":
                    updated = remove_managed_block(text)
                    if not updated and record.get("created"):
                        path.unlink()
                        results.append({"path": relative, "action": "deleted"})
                    else:
                        atomic_write(path, updated)
                        results.append({"path": relative, "action": "managed-block-removed"})
                else:
                    current_hash = sha256_bytes(text.encode("utf-8"))
                    if current_hash == record.get("sha256"):
                        path.unlink()
                        results.append({"path": relative, "action": "deleted"})
                    else:
                        results.append({"path": relative, "action": "preserved", "reason": "local edits"})
                        remaining[relative] = record
            event = self._write_event_unlocked(
                "uninstalled",
                {
                    "summary": "Removed Agent Relay managed entry points and runtime",
                    "actions": results,
                    "next_step": "Historical state remains under .agent-relay; use the installer Skill to reinitialize",
                },
            )
            self._refresh_handoff_unlocked(event["id"])
            config["installed"] = False
            config["uninstalled_at"] = iso_now()
            config["managed_files"] = remaining
            config["updated_at"] = iso_now()
            atomic_write(self.config_path, json_text(config))
            with contextlib.suppress(FileNotFoundError):
                self.runtime_path.unlink()
            return {"dry_run": False, "actions": results, "preserved_state": str(self.state)}

    def purge(self, confirmed: bool, confirmation: Optional[str]) -> Dict[str, Any]:
        if not confirmed or confirmation != self.root.name:
            raise RelayError("Purge requires --yes --confirm %s" % self.root.name)
        if self.config_path.exists():
            config = load_json(self.config_path, {})
            if config.get("installed") is not False:
                self.uninstall(dry_run=False, confirmed=True)
        if self.state.exists():
            shutil.rmtree(str(self.state))
        return {"purged": True, "project_root": str(self.root)}


def output_result(value: Any, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(sanitize(value), ensure_ascii=False, indent=2, sort_keys=True))
        return
    if isinstance(value, str):
        print(value)
        return
    print(json.dumps(sanitize(value), ensure_ascii=False, indent=2, sort_keys=True))


def add_common(parser: argparse.ArgumentParser, include_json: bool = True) -> None:
    parser.add_argument("--project-root", help="Target project root; defaults to Git root or cwd")
    if include_json:
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relay",
        description="Durable project handoff, status, versioning, and multi-agent coordination",
    )
    parser.add_argument("--version", action="version", version="Agent Relay %s" % VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Install or refresh project-local Agent Relay capability")
    add_common(init)
    init.add_argument("--dry-run", action="store_true", help="Preview without writing")
    init.add_argument("--yes", action="store_true", help="Confirm the reviewed initialization plan")
    init.add_argument("--adapters", choices=("minimal", "auto", "all"), default="auto")
    init.add_argument("--goal", help="Optional explicit project goal")
    init.add_argument("--harness", help="Current agent harness name")
    init.add_argument("--model", help="Current model name")
    init.add_argument("--capability", action="append", default=[], help="Safe capability name; repeatable")

    start = commands.add_parser("start", help="Create a task lease and claim write scopes")
    add_common(start)
    start.add_argument("--title", required=True, help="Concise task title")
    start.add_argument("--owner", help="Agent/session owner label")
    start.add_argument("--scope", action="append", default=[], help="Project-relative write path or glob; repeatable")
    start.add_argument("--lease-minutes", type=int, help="Lease duration, 5-1440 minutes")
    start.add_argument("--harness", help="Current harness name")
    start.add_argument("--model", help="Current model name")
    start.add_argument("--capability", action="append", default=[], help="Safe capability name; repeatable")
    start.add_argument("--goal", help="Optional explicit short-term goal")

    checkpoint = commands.add_parser("checkpoint", help="Record a safe handoff point and renew a lease")
    add_common(checkpoint)
    checkpoint.add_argument("--task-id")
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--changed", action="append", default=[], help="Changed project-relative path; repeatable")
    checkpoint.add_argument("--verify", action="append", default=[], help="Verification fact; repeatable")
    checkpoint.add_argument("--blocker", action="append", default=[], help="Current blocker; repeatable")
    checkpoint.add_argument("--next-step")
    checkpoint.add_argument("--lease-minutes", type=int)

    finish = commands.add_parser("finish", help="Finish or block a task and release its lease")
    add_common(finish)
    finish.add_argument("--task-id")
    finish.add_argument("--result", required=True, help="Concise operational result")
    finish.add_argument("--changed", action="append", default=[], help="Changed project-relative path; repeatable")
    finish.add_argument("--verify", action="append", default=[], help="Verification fact; repeatable")
    finish.add_argument("--blocker", action="append", default=[], help="Blocker; repeatable")
    finish.add_argument("--next-step")
    finish.add_argument("--status", choices=("completed", "blocked", "cancelled"), default="completed")

    report = commands.add_parser("report", help="Read-only current project report")
    add_common(report)
    report.add_argument("--short", action="store_true", help="Use the default concise output")
    report.add_argument("--full", action="store_true", help="Include goals, raw active tasks, adapters, and issues")

    status = commands.add_parser("status", help="Show canonical goals, tasks, events, versions, and adapters")
    add_common(status)

    doctor = commands.add_parser("doctor", help="Validate runtime, state, adapters, checksums, and secret hygiene")
    add_common(doctor)

    seal = commands.add_parser("seal", help="Create a non-overwriting version manifest and artifact copy")
    add_common(seal)
    seal.add_argument("--artifact", action="append", default=[], help="Project-relative artifact file or directory; repeatable")
    seal.add_argument("--label")
    seal.add_argument("--summary")
    seal.add_argument("--dry-run", action="store_true")
    seal.add_argument("--yes", action="store_true", help="Confirm explicit finalization and artifact scope")
    seal.add_argument("--max-bytes", type=int, default=100 * 1024 * 1024)

    goal = commands.add_parser("goal", help="Manage explicit or candidate project goals")
    goal_commands = goal.add_subparsers(dest="goal_command", required=True)
    goal_add = goal_commands.add_parser("add", help="Add a goal")
    add_common(goal_add)
    goal_add.add_argument("text")
    goal_add.add_argument("--kind", choices=("explicit", "candidate"), default="explicit")
    goal_add.add_argument("--scope", choices=("long-term", "short-term"), default="long-term")
    goal_list = goal_commands.add_parser("list", help="List goals")
    add_common(goal_list)
    goal_list.add_argument("--all", action="store_true", help="Include inactive goals")
    goal_update = goal_commands.add_parser("update", help="Complete, pause, or supersede a goal")
    add_common(goal_update)
    goal_update.add_argument("goal_id")
    goal_update.add_argument("--status", choices=("completed", "paused", "superseded"), required=True)

    uninstall = commands.add_parser("uninstall", help="Remove managed adapters and runtime, preserving history")
    add_common(uninstall)
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.add_argument("--yes", action="store_true")

    purge = commands.add_parser("purge", help="Permanently delete all Relay state after explicit confirmation")
    add_common(purge)
    purge.add_argument("--yes", action="store_true")
    purge.add_argument("--confirm", help="Project directory name")
    return parser


def render_init_plan(result: Dict[str, Any]) -> str:
    lines = [
        "Agent Relay init dry-run",
        "Project: %s" % result["project_root"],
        "Adapters: %s" % result["adapter_mode"],
        "",
    ]
    for item in result["operations"]:
        detail = " (%s)" % item.get("reason") if item.get("reason") else ""
        lines.append("%-9s %s%s" % (item["action"].upper(), item["path"], detail))
    lines.extend(["", "No files were written. Apply with the same options plus --yes."])
    return "\n".join(lines)


def render_doctor(result: Dict[str, Any]) -> str:
    lines = ["Agent Relay doctor", "Health: %s" % result.get("health"), ""]
    for check in result.get("checks", []):
        lines.append("%-5s %-30s %s" % (check["status"].upper(), check["name"], check["detail"]))
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = discover_root(getattr(args, "project_root", None))
        relay = Relay(root)
        command = args.command
        if command == "init":
            result = relay.initialize(
                args.adapters,
                args.dry_run,
                args.yes,
                args.goal,
                args.harness,
                args.model,
                args.capability,
            )
            if args.json:
                output_result(result, True)
            elif args.dry_run:
                print(render_init_plan(result))
            else:
                print("Agent Relay %s initialized in %s" % (VERSION, root))
                print("Event: %s" % result["event_id"])
                print("Next: %s" % result["doctor_command"])
        elif command == "start":
            result = relay.start_task(
                args.title,
                args.owner,
                args.scope,
                args.lease_minutes,
                args.harness,
                args.model,
                args.capability,
                args.goal,
            )
            output_result(result, args.json)
        elif command == "checkpoint":
            result = relay.update_task(
                "checkpoint",
                args.task_id,
                args.summary,
                args.changed,
                args.verify,
                args.blocker,
                args.next_step,
                None,
                args.lease_minutes,
            )
            output_result(result, args.json)
        elif command == "finish":
            result = relay.update_task(
                "finish",
                args.task_id,
                args.result,
                args.changed,
                args.verify,
                args.blocker,
                args.next_step,
                args.status,
                None,
            )
            output_result(result, args.json)
        elif command == "report":
            result = relay.report_data()
            output_result(result, True) if args.json else print(relay.render_report(result, args.full))
        elif command == "status":
            output_result(relay.status_data(), args.json)
        elif command == "doctor":
            result = relay.doctor()
            output_result(result, True) if args.json else print(render_doctor(result))
            return 1 if result.get("health") in ("degraded", "uninitialized") else 0
        elif command == "seal":
            result = relay.seal(
                args.artifact,
                args.label,
                args.summary,
                args.dry_run,
                args.yes,
                args.max_bytes,
            )
            output_result(result, args.json)
        elif command == "goal":
            if args.goal_command == "add":
                result = relay.add_goal(args.text, args.kind, args.scope)
            elif args.goal_command == "update":
                result = relay.complete_goal(args.goal_id, args.status)
            else:
                goals = relay._goals()["goals"]
                result = goals if args.all else [item for item in goals if item.get("status") == "active"]
            output_result(result, args.json)
        elif command == "uninstall":
            result = relay.uninstall(args.dry_run, args.yes)
            output_result(result, args.json)
        elif command == "purge":
            result = relay.purge(args.yes, args.confirm)
            output_result(result, args.json)
        return 0
    except RelayError as exc:
        print("Agent Relay error: %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Agent Relay interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
