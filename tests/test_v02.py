from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from test_relay import FLEET, SOURCE_RUNTIME, relay_module


class FleetMigrationTests(unittest.TestCase):
    def test_fleet_reports_migration_state_without_writing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "project"
            root.mkdir()
            subprocess.run([sys.executable, str(SOURCE_RUNTIME), "init", "--project-root",
                            str(root), "--adapters", "minimal", "--yes"], check=True,
                           capture_output=True, text=True)
            config_path = root / ".agent-relay" / "config.json"
            config = json.loads(config_path.read_text())
            config["schema_version"] = 1
            for key in ("hooks", "coordination", "migrations"):
                config.pop(key, None)
            config_path.write_text(json.dumps(config))
            before = config_path.read_bytes()
            result = subprocess.run([sys.executable, str(FLEET), "--project", str(root),
                                     "--json"], capture_output=True, text=True, check=True)
            row = json.loads(result.stdout)[0]
            self.assertTrue(row["migration_required"])
            self.assertEqual(row["state_schema_version"], 1)
            self.assertEqual(row["coordination_mode"], "local")
            self.assertEqual(row["reader_version"], relay_module.VERSION)
            self.assertEqual(config_path.read_bytes(), before)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), result.stderr))
    return result.stdout.strip()


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def relay(
        self,
        root: Path,
        *args: str,
        installed: bool = True,
        check: bool = True,
        stdin: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        script = root / ".agent-relay" / "relay.py" if installed else SOURCE_RUNTIME
        env = os.environ.copy()
        env.pop("AGENT_RELAY_HARNESS", None)
        env.pop("AGENT_RELAY_MODEL", None)
        result = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(root),
            env=env,
            input=stdin,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                "relay %s failed (%s)\nstdout:\n%s\nstderr:\n%s"
                % (" ".join(args), result.returncode, result.stdout, result.stderr)
            )
        return result

    def relay_json(self, root: Path, *args: str, stdin: Optional[str] = None,
                   check: bool = True) -> Dict[str, Any]:
        result = self.relay(root, *args, "--json", stdin=stdin, check=check)
        if not result.stdout.strip():
            self.fail("relay %s produced no JSON: %s" % (" ".join(args), result.stderr))
        return json.loads(result.stdout)

    def init(self, root: Optional[Path] = None) -> None:
        target = root or self.root
        self.relay(
            target,
            "init",
            "--project-root",
            str(target),
            "--adapters",
            "minimal",
            "--yes",
            installed=False,
        )

    def start(self, root: Path, title: str, scope: str) -> Dict[str, Any]:
        return self.relay_json(root, "start", "--title", title, "--scope", scope)

    def state_hash(self, root: Path) -> str:
        digest = hashlib.sha256()
        state = root / ".agent-relay"
        for path in sorted(state.rglob("*")):
            if not path.is_file() or "runtime" in path.parts:
                continue
            digest.update(path.relative_to(state).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()


class MigrationTests(BaseCase):
    def legacy_config(self) -> Path:
        self.init()
        config_path = self.root / ".agent-relay" / "config.json"
        config = json.loads(config_path.read_text())
        for key in ("hooks", "coordination", "migrations"):
            config.pop(key, None)
        config["schema_version"] = 1
        config_path.write_text(json.dumps(config))
        goals_path = self.root / ".agent-relay" / "goals.json"
        goals = json.loads(goals_path.read_text())
        goals["schema_version"] = 1
        goals_path.write_text(json.dumps(goals))
        return config_path

    def test_schema_one_state_is_readable_but_write_blocked(self) -> None:
        self.legacy_config()
        before = self.state_hash(self.root)
        report = self.relay_json(self.root, "report")
        self.assertEqual(report["health"], "healthy")
        self.assertTrue(report["migration_required"])
        self.assertEqual(report["state_schema_version"], 1)
        self.assertEqual(before, self.state_hash(self.root))

        blocked = self.relay(self.root, "start", "--title", "Nope", "--json", check=False)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("Schema migration required", blocked.stderr)
        self.assertEqual(before, self.state_hash(self.root))

        doctor = self.relay_json(self.root, "doctor")
        schema = next(item for item in doctor["checks"] if item["name"] == "schema")
        self.assertEqual(schema["status"], "warn")
        self.assertIn("migrate --dry-run", schema["detail"])

    def test_migrate_dry_run_has_no_side_effects(self) -> None:
        self.legacy_config()
        before = self.state_hash(self.root)
        plan = self.relay_json(self.root, "migrate", "--dry-run")
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["migration"]["from"], 1)
        self.assertEqual(plan["migration"]["to"], 2)
        self.assertEqual(before, self.state_hash(self.root))

    def test_migrate_preserves_history_and_is_idempotent(self) -> None:
        self.legacy_config()
        goals_before = (self.root / ".agent-relay/goals.json").read_text()
        tasks_before = sorted(p.name for p in (self.root / ".agent-relay/tasks").iterdir())
        config_before = (self.root / ".agent-relay/config.json").read_bytes()

        result = self.relay_json(self.root, "migrate", "--yes")
        self.assertEqual(result["schema_version"], 2)
        config = json.loads((self.root / ".agent-relay/config.json").read_text())
        self.assertEqual(config["schema_version"], 2)
        self.assertEqual(config["hooks"], {"enabled": False})
        self.assertEqual(config["coordination"], {"mode": "local"})
        self.assertEqual(config["migrations"][-1]["from"], 1)
        self.assertEqual(len(config["migrations"]), 1)

        goals = json.loads((self.root / ".agent-relay/goals.json").read_text())
        self.assertEqual(goals["schema_version"], 2)
        self.assertEqual([goal["text"] for goal in goals["goals"]],
                         [goal["text"] for goal in json.loads(goals_before)["goals"]])
        self.assertEqual(sorted(p.name for p in (self.root / ".agent-relay/tasks").iterdir()),
                         tasks_before)
        self.assertIn(config_before, [path.read_bytes() for path in
                                      (self.root / ".agent-relay/backups").rglob("config.json")])

        again = self.relay_json(self.root, "migrate", "--yes")
        self.assertFalse(again["changed"])
        self.assertEqual(len(json.loads(
            (self.root / ".agent-relay/config.json").read_text())["migrations"]), 1)
        self.assertEqual(self.relay_json(self.root, "doctor")["health"], "healthy")
        task = self.start(self.root, "After migration", "src/")
        self.assertEqual(task["schema_version"], relay_module.SCHEMA_VERSION)

    def test_migrate_requires_confirmation(self) -> None:
        self.legacy_config()
        before = self.state_hash(self.root)
        result = self.relay(self.root, "migrate", "--json", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("--yes", result.stderr)
        self.assertEqual(before, self.state_hash(self.root))

    def test_future_schema_is_refused(self) -> None:
        self.init()
        config_path = self.root / ".agent-relay/config.json"
        config = json.loads(config_path.read_text())
        config["schema_version"] = 99
        config_path.write_text(json.dumps(config))
        report = self.relay_json(self.root, "report")
        self.assertEqual(report["health"], "degraded")
        self.assertIn("Unsupported", report["issues"][0])
        for command in (("migrate", "--dry-run"), ("start", "--title", "x"), ("doctor",)):
            result = self.relay(self.root, *command, check=False)
            self.assertNotIn("Traceback", result.stderr, command)
        migrate = self.relay(self.root, "migrate", "--dry-run", check=False)
        self.assertEqual(migrate.returncode, 1)
        self.assertIn("Unsupported", migrate.stderr)


class HookTests(BaseCase):
    def test_hooks_are_opt_in_and_never_write_harness_config(self) -> None:
        self.init()
        status = self.relay_json(self.root, "hooks", "status")
        self.assertFalse(status["enabled"])
        ignored = self.relay_json(self.root, "hook", "session-start")
        self.assertEqual(ignored, {"enabled": False, "ignored": True})

        before = self.state_hash(self.root)
        plan = self.relay_json(self.root, "hooks", "enable", "--dry-run")
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["harness_configuration_changed"])
        self.assertEqual(before, self.state_hash(self.root))

        self.relay_json(self.root, "hooks", "enable", "--yes")
        self.assertTrue(self.relay_json(self.root, "hooks", "status")["enabled"])
        self.assertTrue(self.relay_json(self.root, "report")["hooks_enabled"])
        for harness_file in ("CLAUDE.md", ".cursor", ".github", ".codex"):
            self.assertFalse((self.root / harness_file).exists(), harness_file)
        self.relay_json(self.root, "hooks", "disable", "--yes")
        self.assertFalse(self.relay_json(self.root, "hooks", "status")["enabled"])

    def test_hook_lifecycle_matches_cli_records(self) -> None:
        self.init()
        self.relay_json(self.root, "hooks", "enable", "--yes")
        before = self.state_hash(self.root)
        session = self.relay_json(self.root, "hook", "session-start")
        self.assertTrue(session["enabled"])
        self.assertEqual(session["report"]["health"], "healthy")
        self.assertEqual(before, self.state_hash(self.root))

        started = self.relay_json(
            self.root, "hook", "before-write",
            stdin=json.dumps({"title": "Hook task", "scopes": ["src/"], "lease_minutes": 45}),
        )
        starred = started
        self.assertEqual(starred["status"], "active")
        self.assertIsNotNone(starred["lease_expires_at"])

        checked = self.relay_json(
            self.root, "hook", "checkpoint",
            stdin=json.dumps({"task_id": starred["id"], "summary": "halfway",
                              "changed": ["src/a.py"], "verification": ["unit"]}),
        )
        self.assertEqual(checked["task"]["status"], "active")
        finished = self.relay_json(
            self.root, "hook", "task-finish",
            stdin=json.dumps({"task_id": starred["id"], "result": "done",
                              "status": "completed", "verification": ["tests pass"]}),
        )
        self.assertEqual(finished["task"]["status"], "completed")
        report = self.relay_json(self.root, "report")
        self.assertEqual(report["last_completed"]["summary"], "done")

    def test_hook_payloads_are_bounded_and_strict(self) -> None:
        self.init()
        self.relay_json(self.root, "hooks", "enable", "--yes")
        before = self.state_hash(self.root)
        cases = [
            ({}, "missing"),
            ({"title": "x", "unknown": "y"}, "unknown"),
            ({"title": "   "}, "nonempty"),
            ({"title": "x" * 5000}, "nonempty"),
            ({"title": "x", "scopes": ["ok", 3]}, "string list"),
            ({"title": "x", "lease_minutes": 1}, "5 to 1440"),
        ]
        for payload, message in cases:
            result = self.relay(self.root, "hook", "before-write", check=False,
                                stdin=json.dumps(payload))
            self.assertEqual(result.returncode, 1, payload)
            self.assertIn(message, result.stderr)
        too_big = self.relay(self.root, "hook", "before-write", check=False,
                             stdin=json.dumps({"title": "x" * (70 * 1024)}))
        self.assertEqual(too_big.returncode, 1)
        self.assertIn("64 KiB", too_big.stderr)
        invalid = self.relay(self.root, "hook", "checkpoint", check=False, stdin="{not json")
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(before, self.state_hash(self.root))

        started = self.relay_json(self.root, "hook", "before-write",
                                  stdin=json.dumps({"title": "finish me", "scopes": []}))
        bad_status = self.relay(self.root, "hook", "task-finish", check=False, stdin=json.dumps(
            {"task_id": started["id"], "result": "x", "status": "done"}))
        self.assertEqual(bad_status.returncode, 1)
        self.assertIn("completed, blocked, or cancelled", bad_status.stderr)


@unittest.skipUnless(shutil.which("git"), "git is required for worktree coordination")
class WorktreeTests(BaseCase):
    def setUp(self) -> None:
        super().setUp()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "relay@example.invalid")
        git(self.root, "config", "user.name", "Relay Test")
        (self.root / "README.md").write_text("fixture\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "init")
        self.peer = self.base / "peer"
        git(self.root, "worktree", "add", "-q", str(self.peer), "-b", "peer")

    def registry_path(self, root: Path) -> Path:
        common = git(root, "rev-parse", "--absolute-git-dir")
        return Path(common) / ".agent-relay" / "coordination.json"

    def test_opt_in_requires_confirmation_and_git(self) -> None:
        self.init()
        before = self.state_hash(self.root)
        plan = self.relay_json(self.root, "worktree", "enable", "--dry-run")
        self.assertEqual(plan["mode"], "git-common-dir")
        self.assertEqual(before, self.state_hash(self.root))
        refused = self.relay(self.root, "worktree", "enable", "--json", check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("--yes", refused.stderr)
        self.relay_json(self.root, "worktree", "enable", "--yes")
        status = self.relay_json(self.root, "worktree", "status")
        self.assertEqual(status["mode"], "git-common-dir")
        self.assertEqual(status["registered_worktrees"], 1)

        plain = self.base / "plain"
        plain.mkdir()
        self.init(plain)
        result = self.relay(plain, "worktree", "enable", "--yes", "--json", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Git repository", result.stderr)

    def test_cross_worktree_scopes_block_and_release(self) -> None:
        self.init()
        self.init(self.peer)
        self.relay_json(self.root, "worktree", "enable", "--yes")
        self.relay_json(self.peer, "worktree", "enable", "--yes")
        task = self.start(self.root, "Feature in main", "src/")
        conflict = self.relay(self.peer, "start", "--title", "Overlap", "--scope",
                              "src/app", "--json", check=False)
        self.assertEqual(conflict.returncode, 1)
        self.assertIn("Cross-worktree write-scope conflict", conflict.stderr)
        self.assertIn(task["id"], conflict.stderr)

        docs = self.start(self.peer, "Docs elsewhere", "docs/")
        self.assertEqual(docs["status"], "active")
        self.relay_json(self.peer, "finish", "--task-id", docs["id"], "--result", "docs done")
        self.assertEqual(self.relay_json(self.peer, "doctor")["health"], "healthy")

        # A peer cannot finish a task it does not own locally.
        foreign = self.relay(self.peer, "finish", "--task-id", task["id"],
                             "--result", "nope", check=False)
        self.assertEqual(foreign.returncode, 1)

        self.relay_json(self.root, "finish", "--task-id", task["id"], "--result", "shipped")
        registry = json.loads(self.registry_path(self.root).read_text())
        self.assertEqual(registry["claims"], {})
        self.assertIn(str(self.peer), [member["root"] for member in registry["members"].values()])

    def test_unregistered_worktree_uses_local_state(self) -> None:
        # Worktree-private state is Git-cleaned, so a worktree that never opted
        # in keeps its own local leases instead of consulting shared claims.
        self.init()
        self.init(self.peer)
        self.relay_json(self.root, "worktree", "enable", "--yes")
        self.start(self.root, "Feature in main", "src/")
        local = self.start(self.peer, "Local work", "src/")
        self.assertEqual(local["status"], "active")
        self.assertEqual(self.relay_json(self.peer, "worktree", "status")["mode"], "local")

    def test_disable_requires_no_active_claims_and_cleans_registry(self) -> None:
        self.init()
        self.relay_json(self.root, "worktree", "enable", "--yes")
        task = self.start(self.root, "Feature in main", "src/")
        blocked = self.relay(self.root, "worktree", "disable", "--yes", check=False)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("Finish active tasks", blocked.stderr)
        self.relay_json(self.root, "finish", "--task-id", task["id"], "--result", "done")
        plan = self.relay_json(self.root, "worktree", "disable", "--dry-run")
        self.assertEqual(plan["mode"], "local")
        self.relay_json(self.root, "worktree", "disable", "--yes")
        self.assertEqual(self.relay_json(self.root, "worktree", "status")["mode"], "local")
        self.assertFalse(self.registry_path(self.root).exists())
        self.assertEqual(self.relay_json(self.root, "doctor")["health"], "healthy")

    def test_tampered_registry_blocks_writes(self) -> None:
        self.init()
        self.relay_json(self.root, "worktree", "enable", "--yes")
        registry_path = self.registry_path(self.root)
        data = json.loads(registry_path.read_text())
        data["members"] = {"0" * 24: {"root": str(self.root), "worktree_id": "0" * 24}}
        registry_path.write_text(json.dumps(data))
        result = self.relay(self.root, "start", "--title", "x", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid coordination member", result.stderr)

        data["members"] = {}
        data["claims"] = {"task-x": {"worktree_id": "0" * 24, "write_scopes": ["src"],
                                     "lease_expires_at": "not a time"}}
        registry_path.write_text(json.dumps(data))
        result = self.relay(self.root, "start", "--title", "x", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid shared task claim", result.stderr)

        registry_path.unlink()
        result = self.relay(self.root, "start", "--title", "x", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("registry is missing", result.stderr)

    def test_report_and_doctor_are_read_only_when_coordinated(self) -> None:
        self.init()
        self.relay_json(self.root, "worktree", "enable", "--yes")
        self.start(self.root, "Feature in main", "src/")
        before = self.state_hash(self.root)
        report = self.relay_json(self.root, "report")
        self.assertEqual(report["coordination"]["mode"], "git-common-dir")
        self.assertEqual(len(report["coordination"]["active_claims"]), 1)
        self.assertEqual(self.relay_json(self.root, "doctor")["health"], "healthy")
        self.assertEqual(before, self.state_hash(self.root))


if __name__ == "__main__":
    unittest.main()
