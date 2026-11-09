from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SOURCE_RUNTIME = REPO / "skills" / "agent-relay" / "scripts" / "relay.py"
SKILL = REPO / "skills" / "agent-relay" / "SKILL.md"
FLEET = SOURCE_RUNTIME.with_name("fleet_report.py")
spec = importlib.util.spec_from_file_location("relay_under_test", SOURCE_RUNTIME)
relay_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay_module)


class RelayTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_relay(
        self,
        *args: str,
        installed: bool = False,
        check: bool = True,
        env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess[str]:
        script = self.root / ".agent-relay" / "relay.py" if installed else SOURCE_RUNTIME
        command = [sys.executable, str(script), *args]
        merged_env = os.environ.copy()
        merged_env.pop("AGENT_RELAY_HARNESS", None)
        merged_env.pop("AGENT_RELAY_MODEL", None)
        if env:
            merged_env.update(env)
        result = subprocess.run(
            command,
            cwd=str(self.root),
            env=merged_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                "command failed (%s):\nstdout:\n%s\nstderr:\n%s"
                % (result.returncode, result.stdout, result.stderr)
            )
        return result

    def init(self, adapters: str = "minimal") -> None:
        self.run_relay(
            "init",
            "--project-root",
            str(self.root),
            "--adapters",
            adapters,
            "--yes",
            "--harness",
            "test-harness",
            "--model",
            "test-model",
            "--capability",
            "shell",
        )

    def json_output(self, *args: str, installed: bool = True) -> Dict[str, Any]:
        result = self.run_relay(*args, "--json", installed=installed)
        return json.loads(result.stdout)

    def state_hash(self) -> str:
        digest = hashlib.sha256()
        state = self.root / ".agent-relay"
        for path in sorted(state.rglob("*")):
            if not path.is_file() or "runtime" in path.parts:
                continue
            digest.update(path.relative_to(state).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def test_skill_structure_and_frontmatter(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---\n", 2)[1]
        self.assertIn("name: agent-relay\n", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertIn("license: MIT", frontmatter)
        self.assertEqual(SKILL.parent.name, "agent-relay")
        self.assertLess(len(text.splitlines()), 500)
        self.assertTrue(SOURCE_RUNTIME.is_file())

    def test_dry_run_has_no_side_effects(self) -> None:
        result = self.run_relay(
            "init",
            "--project-root",
            str(self.root),
            "--dry-run",
            "--adapters",
            "minimal",
        )
        self.assertIn("No files were written", result.stdout)
        self.assertFalse((self.root / ".agent-relay").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_init_is_idempotent_and_preserves_existing_instructions(self) -> None:
        agents = self.root / "AGENTS.md"
        agents.write_text("# Existing\n\nKeep this line.\n", encoding="utf-8")
        self.init()
        first = agents.read_text(encoding="utf-8")
        self.assertIn("Keep this line.", first)
        self.assertEqual(first.count("<!-- agent-relay:start -->"), 1)
        backups = list((self.root / ".agent-relay" / "backups").rglob("AGENTS.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "# Existing\n\nKeep this line.\n")

        self.run_relay("init", "--adapters", "minimal", "--yes", installed=True)
        second = agents.read_text(encoding="utf-8")
        self.assertEqual(second.count("<!-- agent-relay:start -->"), 1)
        doctor = self.run_relay("doctor", installed=True)
        self.assertIn("Health: healthy", doctor.stdout)

    def test_all_adapter_mode_generates_direct_bridges(self) -> None:
        self.init("all")
        expected = [
            "CLAUDE.md",
            "GEMINI.md",
            "CODEBUDDY.md",
            ".cursor/rules/agent-relay.mdc",
            ".github/copilot-instructions.md",
            ".agents/skills/agent-relay/SKILL.md",
            ".qoder/skills/agent-relay/SKILL.md",
            ".trae/skills/agent-relay/SKILL.md",
            ".codebuddy/skills/agent-relay/SKILL.md",
            ".qwen/skills/agent-relay/SKILL.md",
            ".kimi/skills/agent-relay/SKILL.md",
            ".opencode/skills/agent-relay/SKILL.md",
            ".cline/skills/agent-relay/SKILL.md",
            ".pi/skills/agent-relay/SKILL.md",
            ".windsurf/skills/agent-relay/SKILL.md",
            ".roo/skills/agent-relay/SKILL.md",
            ".kilocode/skills/agent-relay/SKILL.md",
            ".continue/skills/agent-relay/SKILL.md",
            ".kiro/skills/agent-relay/SKILL.md",
            ".goose/skills/agent-relay/SKILL.md",
            ".openhands/skills/agent-relay/SKILL.md",
        ]
        for relative in expected:
            self.assertTrue((self.root / relative).exists(), relative)
        agents_text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        bridge_text = (
            self.root / ".agents" / "skills" / "agent-relay" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("complete restore requires separate explicit confirmation", agents_text)
        self.assertIn("uninstalling and restoring Agent Relay", bridge_text)
        self.assertIn("A complete restore requires explicit confirmation", bridge_text)
        doctor = self.json_output("doctor")
        self.assertEqual(doctor["health"], "healthy")

    def test_task_scope_conflict_then_release(self) -> None:
        self.init()
        first = self.json_output(
            "start",
            "--title",
            "First task",
            "--owner",
            "agent-a",
            "--scope",
            "src/**",
        )
        conflict = self.run_relay(
            "start",
            "--title",
            "Second task",
            "--owner",
            "agent-b",
            "--scope",
            "src/api.py",
            installed=True,
            check=False,
        )
        self.assertEqual(conflict.returncode, 1)
        self.assertIn("Write-scope conflict", conflict.stderr)
        self.json_output(
            "finish",
            "--task-id",
            first["id"],
            "--result",
            "First task complete",
            "--changed",
            "src/api.py",
            "--verify",
            "focused test passed",
        )
        second = self.json_output(
            "start",
            "--title",
            "Second task",
            "--owner",
            "agent-b",
            "--scope",
            "src/api.py",
        )
        self.assertEqual(second["status"], "active")

    def test_report_is_read_only(self) -> None:
        self.init()
        self.json_output("start", "--title", "Read-only report test", "--scope", "docs/**")
        before = self.state_hash()
        report = self.json_output("report")
        after = self.state_hash()
        self.assertEqual(before, after)
        self.assertEqual(report["health"], "healthy")
        self.assertEqual(len(report["active_work"]), 1)

    def test_secret_values_are_redacted(self) -> None:
        self.init()
        task = self.json_output(
            "start",
            "--title",
            "Handle token=plain-secret-value",
            "--owner",
            "agent",
            "--scope",
            "result.txt",
        )
        self.json_output(
            "finish",
            "--task-id",
            task["id"],
            "--result",
            "Saved api_key=sk-abcdefghijklmnopqrstuv",
            "--verify",
            "password=hunter2 was not persisted",
        )
        shared_text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in (self.root / ".agent-relay").rglob("*")
            if path.is_file() and "runtime" not in path.parts and "backups" not in path.parts
        )
        self.assertNotIn("plain-secret-value", shared_text)
        self.assertNotIn("sk-abcdefghijklmnopqrstuv", shared_text)
        self.assertNotIn("hunter2", shared_text)
        self.assertIn("[REDACTED]", shared_text)
        self.assertEqual(self.run_relay("doctor", installed=True).returncode, 0)

    def test_seal_copies_artifact_and_detects_tampering(self) -> None:
        self.init()
        artifact = self.root / "deliverable.txt"
        artifact.write_text("approved v1\n", encoding="utf-8")
        dry = self.json_output("seal", "--artifact", "deliverable.txt", "--dry-run")
        self.assertEqual(dry["version"], "v001")
        self.assertFalse((self.root / ".agent-relay" / "versions" / "v001").exists())
        sealed = self.json_output(
            "seal",
            "--artifact",
            "deliverable.txt",
            "--label",
            "release",
            "--summary",
            "Approved output",
            "--yes",
        )
        self.assertEqual(sealed["version"], "v001")
        copied = self.root / ".agent-relay" / "versions" / "v001" / "artifacts" / "deliverable.txt"
        self.assertEqual(copied.read_text(encoding="utf-8"), "approved v1\n")
        artifact.write_text("working v2\n", encoding="utf-8")
        self.assertEqual(copied.read_text(encoding="utf-8"), "approved v1\n")
        copied.write_text("tampered\n", encoding="utf-8")
        doctor = self.run_relay("doctor", installed=True, check=False)
        self.assertEqual(doctor.returncode, 1)
        self.assertIn("sealed-versions", doctor.stdout)

    def test_goal_lifecycle_updates_report(self) -> None:
        self.init()
        goal = self.json_output(
            "goal",
            "add",
            "Publish v0.1",
            "--kind",
            "explicit",
            "--scope",
            "long-term",
        )
        report = self.json_output("report")
        self.assertEqual(report["project_goal"], "Publish v0.1")
        updated = self.json_output(
            "goal",
            "update",
            goal["id"],
            "--status",
            "completed",
        )
        self.assertEqual(updated["status"], "completed")

    def test_dotfile_scope_is_preserved_and_completed_task_cannot_repeat(self) -> None:
        self.init()
        task = self.json_output(
            "start",
            "--title",
            "Update workflow",
            "--scope",
            ".github/workflows/ci.yml",
        )
        self.assertEqual(task["write_scopes"], [".github/workflows/ci.yml"])
        self.json_output(
            "finish",
            "--task-id",
            task["id"],
            "--result",
            "Workflow updated",
        )
        repeated = self.run_relay(
            "finish",
            "--task-id",
            task["id"],
            "--result",
            "Duplicate finish",
            installed=True,
            check=False,
        )
        self.assertEqual(repeated.returncode, 1)
        self.assertIn("Cannot update task in status completed", repeated.stderr)

    def test_expired_lease_requires_new_task(self) -> None:
        self.init()
        task = self.json_output(
            "start",
            "--title",
            "Old task",
            "--scope",
            "src/**",
        )
        task_path = self.root / ".agent-relay" / "tasks" / (task["id"] + ".json")
        stored = json.loads(task_path.read_text(encoding="utf-8"))
        stored["lease_expires_at"] = "2000-01-01T00:00:00Z"
        task_path.write_text(json.dumps(stored), encoding="utf-8")
        checkpoint = self.run_relay(
            "checkpoint",
            "--task-id",
            task["id"],
            "--summary",
            "Late update",
            installed=True,
            check=False,
        )
        self.assertEqual(checkpoint.returncode, 1)
        self.assertIn("lease expired", checkpoint.stderr)
        replacement = self.json_output(
            "start",
            "--title",
            "Replacement task",
            "--scope",
            "src/**",
        )
        self.assertEqual(replacement["status"], "active")
        old = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertEqual(old["status"], "expired")

    def test_doctor_handles_non_object_config(self) -> None:
        self.init()
        (self.root / ".agent-relay" / "config.json").write_text("[]\n", encoding="utf-8")
        doctor = self.run_relay("doctor", installed=True, check=False)
        self.assertEqual(doctor.returncode, 1)
        self.assertIn("config.json must contain an object", doctor.stdout)
        self.assertNotIn("Traceback", doctor.stderr)

    def test_tampered_managed_path_cannot_escape_project(self) -> None:
        self.init()
        outside = self.root.parent / (self.root.name + "-outside.txt")
        outside.write_text("do not delete\n", encoding="utf-8")
        try:
            config_path = self.root / ".agent-relay" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["managed_files"]["../../%s" % outside.name] = {
                "mode": "owned",
                "created": True,
                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                "adapter": "malicious",
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")
            doctor = self.run_relay("doctor", installed=True, check=False)
            self.assertEqual(doctor.returncode, 1)
            self.assertIn("Invalid project-relative path", doctor.stdout)
            uninstall = self.run_relay("uninstall", "--yes", installed=True)
            self.assertIn("preserved", uninstall.stdout)
            self.assertEqual(outside.read_text(encoding="utf-8"), "do not delete\n")
        finally:
            outside.unlink(missing_ok=True)

    def test_manifest_and_symlink_paths_cannot_escape_seal_boundary(self) -> None:
        self.init()
        artifact = self.root / "artifact.txt"
        artifact.write_text("sealed\n", encoding="utf-8")
        link = self.root / "artifact-link.txt"
        link.symlink_to(artifact)
        rejected = self.run_relay(
            "seal",
            "--artifact",
            "artifact-link.txt",
            "--yes",
            installed=True,
            check=False,
        )
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("Symlink artifacts are not supported", rejected.stderr)
        self.json_output("seal", "--artifact", "artifact.txt", "--yes")
        manifest_path = self.root / ".agent-relay" / "versions" / "v001" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"][0]["path"] = "../../../../outside.txt"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        doctor = self.run_relay("doctor", installed=True, check=False)
        self.assertEqual(doctor.returncode, 1)
        self.assertIn("sealed-versions", doctor.stdout)
        self.assertNotIn("Traceback", doctor.stderr)

    def test_invalid_environment_reference_degrades_report_without_reading_it(self) -> None:
        self.init()
        config_path = self.root / ".agent-relay" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["current_environment"] = "../../private"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        report = self.json_output("report")
        self.assertEqual(report["health"], "degraded")
        self.assertIn("invalid current environment ID", report["issues"])

    def test_uninstall_preserves_user_content_and_history_then_purge(self) -> None:
        agents = self.root / "AGENTS.md"
        agents.write_text("# User policy\n\nPreserve me.\n", encoding="utf-8")
        self.init()
        result = self.json_output("uninstall", "--dry-run")
        self.assertTrue(result["dry_run"])
        self.json_output("uninstall", "--yes")
        self.assertIn("Preserve me.", agents.read_text(encoding="utf-8"))
        self.assertNotIn("agent-relay:start", agents.read_text(encoding="utf-8"))
        self.assertFalse((self.root / ".agent-relay" / "relay.py").exists())
        self.assertTrue((self.root / ".agent-relay" / "events").is_dir())
        config = json.loads((self.root / ".agent-relay" / "config.json").read_text(encoding="utf-8"))
        self.assertFalse(config["installed"])
        self.run_relay(
            "purge",
            "--project-root",
            str(self.root),
            "--yes",
            "--confirm",
            self.root.name,
        )
        self.assertFalse((self.root / ".agent-relay").exists())
        self.assertTrue(agents.exists())

    def test_blocked_and_cancelled_are_not_completed(self) -> None:
        self.init()
        completed = self.json_output("start", "--title", "Implement")
        self.json_output(
            "finish", "--task-id", completed["id"], "--result", "Implementation finished",
            "--blocker", "External acceptance not verified",
        )
        blocked = self.json_output("start", "--title", "Review")
        self.json_output(
            "finish", "--task-id", blocked["id"], "--result", "Review waiting",
            "--status", "blocked", "--blocker", "Awaiting approval",
        )
        cancelled = self.json_output("start", "--title", "Discard")
        self.json_output(
            "finish", "--task-id", cancelled["id"], "--result", "Discarded",
            "--status", "cancelled",
        )
        before = self.state_hash()
        report = self.json_output("report")
        self.assertEqual(report["last_completed"]["task_id"], completed["id"])
        self.assertEqual(report["last_blocked"]["task_id"], blocked["id"])
        self.assertEqual([task["id"] for task in report["blocked_work"]], [blocked["id"]])
        self.assertIn("Awaiting approval", report["blockers"])
        self.assertEqual(report["completion_caveats"], ["External acceptance not verified"])
        handoff = (self.root / ".agent-relay/HANDOFF.md").read_text()
        self.assertIn("Review", handoff)
        self.assertIn("Awaiting approval", handoff)
        self.assertIn("External acceptance not verified", handoff)
        self.assertNotIn("Discarded", handoff)
        self.assertEqual(before, self.state_hash())

    def test_only_blocked_work_has_no_last_completed(self) -> None:
        self.init()
        task = self.json_output("start", "--title", "Waiting")
        self.json_output("finish", "--task-id", task["id"], "--status", "blocked",
                         "--result", "Not finished")
        self.assertIsNone(self.json_output("report")["last_completed"])

    def test_goal_order_is_explicit_recent_and_stable(self) -> None:
        self.init()
        first = self.json_output("goal", "add", "Old explicit", "--kind", "explicit")
        second = self.json_output("goal", "add", "New explicit", "--kind", "explicit")
        candidate = self.json_output("goal", "add", "Possible direction", "--kind", "candidate")
        path = self.root / ".agent-relay/goals.json"
        data = json.loads(path.read_text())
        for goal in data["goals"]:
            goal["updated_at"] = "2026-01-01T00:00:00Z"
        path.write_text(json.dumps(data))
        report = self.json_output("report")
        self.assertEqual(report["project_goal"], second["text"])
        self.assertEqual([item["id"] for item in report["goals"]],
                         [second["id"], first["id"], candidate["id"]])
        data["goals"][0]["updated_at"] = "2026-01-02T00:00:00"
        path.write_text(json.dumps(data))
        self.assertEqual(self.json_output("report")["project_goal"], first["text"])
        self.json_output("goal", "update", first["id"], "--status", "completed")
        self.json_output("goal", "update", second["id"], "--status", "completed")
        report = self.json_output("report")
        self.assertEqual(report["project_goal"], "No explicit goal recorded")
        self.assertEqual(report["goals"][0]["kind"], "candidate")
        handoff = (self.root / ".agent-relay/HANDOFF.md").read_text()
        self.assertLess(handoff.index("## Active goals"), handoff.index("## Active tasks"))

    def test_expired_lease_warns_in_doctor_without_mutation(self) -> None:
        self.init()
        task = self.json_output("start", "--title", "Expired")
        path = self.root / ".agent-relay/tasks" / (task["id"] + ".json")
        task["lease_expires_at"] = "2000-01-01T00:00:00Z"
        path.write_text(json.dumps(task))
        before = self.state_hash()
        report = self.json_output("report")
        doctor = self.json_output("doctor")
        self.assertEqual(report["health"], "stale")
        self.assertEqual(doctor["health"], "warning")
        self.assertEqual(next(item for item in doctor["checks"]
                              if item["name"] == "lease-freshness")["status"], "warn")
        self.assertEqual(before, self.state_hash())

    def test_non_git_drift_tracks_only_latest_manifest(self) -> None:
        self.init()
        artifact = self.root / "output.txt"
        artifact.write_text("approved")
        self.json_output("seal", "--artifact", "output.txt", "--yes")
        original = self.json_output("report")["version_state"]
        self.assertEqual(original["drift_basis"], "artifact-manifest")
        self.assertEqual(original["unsealed_changes"], 0)
        (self.root / "unsealed-new-file.txt").write_text("not in the manifest")
        self.assertEqual(self.json_output("report")["version_state"]["unsealed_changes"], 0)
        artifact.write_text("revised")
        before = self.state_hash()
        changed = self.json_output("report")["version_state"]
        self.assertEqual(changed["artifact_drift"]["changed"], ["output.txt"])
        self.assertEqual(changed["unsealed_changes"], 1)
        self.assertEqual(before, self.state_hash())
        self.json_output("seal", "--artifact", "output.txt", "--yes")
        self.assertEqual(self.json_output("report")["version_state"]["unsealed_changes"], 0)
        artifact.unlink()
        missing = self.json_output("report")["version_state"]
        self.assertEqual(missing["artifact_drift"]["missing"], ["output.txt"])

    def test_git_report_also_compares_sealed_artifacts(self) -> None:
        self.init()
        subprocess.run(["git", "init", str(self.root)], check=True, capture_output=True)
        (self.root / "output.txt").write_text("sealed")
        self.json_output("seal", "--artifact", "output.txt", "--yes")
        (self.root / "output.txt").write_text("working")
        version = self.json_output("report")["version_state"]
        self.assertEqual(version["drift_basis"], "git")
        self.assertEqual(version["artifact_drift"]["changed"], ["output.txt"])

    def test_artifact_scan_bounds_and_io_errors_are_unknown(self) -> None:
        self.init()
        (self.root / "output.txt").write_text("sealed")
        self.json_output("seal", "--artifact", "output.txt", "--yes")
        relay = relay_module.Relay(self.root)
        with mock.patch.object(relay_module, "REPORT_ARTIFACT_MAX_BYTES", 2):
            version = relay.report_data()["version_state"]
        self.assertEqual(version["unsealed_changes"], "unknown")
        self.assertEqual(version["artifact_drift"]["unknown"], ["output.txt"])
        with mock.patch.object(relay_module, "bounded_sha256", side_effect=PermissionError):
            version = relay.report_data()["version_state"]
        self.assertEqual(version["artifact_drift"]["status"], "unknown")
        self.assertEqual(version["artifact_drift"]["scanned_bytes"], 0)

    def test_artifact_scan_refuses_parent_symlinks_and_state_paths(self) -> None:
        self.init()
        directory = self.root / "outputs"
        directory.mkdir()
        (directory / "result.txt").write_text("sealed")
        self.json_output("seal", "--artifact", "outputs/result.txt", "--yes")
        directory.rename(self.root / "moved")
        directory.symlink_to(self.root / "moved", target_is_directory=True)
        version = self.json_output("report")["version_state"]
        self.assertEqual(version["artifact_drift"]["unsafe"], ["outputs/result.txt"])
        self.assertEqual(version["unsealed_changes"], "unknown")
        relay = relay_module.Relay(self.root)
        result = relay._artifact_drift({"artifacts": [
            {"path": "../outside.txt", "sha256": "0" * 64},
            {"path": ".agent-relay/config.json", "sha256": "0" * 64},
            {"path": ".git/config", "sha256": "0" * 64},
        ]})
        self.assertEqual(len(result["unsafe"]), 3)
        self.assertEqual(result["scanned_bytes"], 0)

    def test_upgrade_backs_up_runtime_config_and_owned_bridge(self) -> None:
        self.init()
        state = self.root / ".agent-relay"
        runtime = state / "relay.py"
        config_path = state / "config.json"
        config = json.loads(config_path.read_text())
        legacy_source = runtime.read_text() + "\n# Previous release fixture.\n"
        runtime.write_text(legacy_source)
        config["runtime_sha256"] = hashlib.sha256(runtime.read_bytes()).hexdigest()
        bridge_relative = ".agents/skills/agent-relay/SKILL.md"
        bridge = self.root / bridge_relative
        bridge.write_text("# Previous owned bridge\n")
        config["managed_files"][bridge_relative]["sha256"] = hashlib.sha256(bridge.read_bytes()).hexdigest()
        config_path.write_text(json.dumps(config))
        config_before = config_path.read_bytes()
        goals_before = (state / "goals.json").read_bytes()
        self.init()
        self.assertEqual(runtime.read_bytes(), SOURCE_RUNTIME.read_bytes())
        self.assertIn("Agent Relay project bridge", bridge.read_text())
        backups = list((state / "backups").rglob("relay.py"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), legacy_source)
        self.assertIn(config_before, [path.read_bytes() for path in (state / "backups").rglob("config.json")])
        self.assertEqual((state / "goals.json").read_bytes(), goals_before)
        config = json.loads(config_path.read_text())
        self.assertTrue(config["managed_files"]["AGENTS.md"]["created"])
        self.json_output("uninstall", "--yes")
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_upgrade_and_uninstall_preserve_edited_runtime(self) -> None:
        self.init()
        runtime = self.root / ".agent-relay/relay.py"
        runtime.write_text(runtime.read_text() + "\n# User custom behavior.\n")
        before = self.state_hash()
        plan = self.json_output("init", "--project-root", str(self.root), "--dry-run",
                                "--adapters", "minimal", installed=False)
        self.assertEqual(next(item for item in plan["operations"]
                              if item["kind"] == "runtime")["action"], "conflict")
        result = self.run_relay("init", "--project-root", str(self.root),
                                "--adapters", "minimal", "--yes", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(before, self.state_hash())
        uninstall = self.json_output("uninstall", "--project-root", str(self.root),
                                     "--yes", installed=False)
        self.assertTrue(runtime.exists())
        self.assertIn(".agent-relay/relay.py", [item["path"] for item in uninstall["actions"]
                                             if item["action"] == "preserved"])

    def test_known_legacy_runtime_can_upgrade_without_ownership_record(self) -> None:
        self.init()
        runtime = self.root / ".agent-relay/relay.py"
        runtime.write_text("# Known legacy runtime fixture\n")
        previous = runtime.read_bytes()
        legacy_hash = hashlib.sha256(previous).hexdigest()
        config_path = self.root / ".agent-relay/config.json"
        config = json.loads(config_path.read_text())
        config.pop("runtime_sha256")
        config["runtime_version"] = "0.1.0"
        config_path.write_text(json.dumps(config))
        relay = relay_module.Relay(self.root)
        with mock.patch.dict(relay_module.KNOWN_RUNTIME_HASHES, {legacy_hash: "0.1.0"}):
            plan = relay.init_plan("minimal")
            self.assertEqual(next(item for item in plan["operations"]
                                  if item["kind"] == "runtime")["action"], "modify")
            relay.initialize("minimal", False, True, None, None, None, [])
        self.assertEqual(runtime.read_bytes(), SOURCE_RUNTIME.read_bytes())
        self.assertIn(previous, [path.read_bytes()
                                for path in (self.root / ".agent-relay/backups").rglob("relay.py")])

    def test_refresh_preserves_edited_bridge_and_rejects_state_symlinks(self) -> None:
        self.init()
        bridge = self.root / ".agents/skills/agent-relay/SKILL.md"
        bridge.write_text(bridge.read_text() + "\nMy local instructions.\n")
        before = bridge.read_bytes()
        self.init()
        self.assertEqual(bridge.read_bytes(), before)
        runtime = self.root / ".agent-relay/relay.py"
        runtime.unlink()
        runtime.symlink_to(self.root / "missing-runtime.py")
        result = self.run_relay("init", "--project-root", str(self.root),
                                "--yes", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(runtime.is_symlink())
        self.assertFalse((self.root / "missing-runtime.py").exists())

    def test_fleet_is_read_only_and_never_executes_project_runtime(self) -> None:
        self.init()
        task = self.json_output("start", "--title", "Blocked")
        self.json_output("finish", "--task-id", task["id"], "--status", "blocked",
                         "--result", "Waiting")
        runtime = self.root / ".agent-relay/relay.py"
        runtime.write_text("from pathlib import Path\nPath('executed.txt').touch()\n")
        before = self.state_hash()
        result = subprocess.run([sys.executable, str(FLEET), "--project", str(self.root),
                                 "--json"], check=True, capture_output=True, text=True)
        row = json.loads(result.stdout)[0]
        self.assertEqual(row["blocked_tasks"], 1)
        self.assertEqual(row["doctor_health"], "warning")
        self.assertEqual(before, self.state_hash())
        self.assertFalse((self.root / "executed.txt").exists())
        self.assertFalse((self.root / ".agent-relay/__pycache__").exists())

    def test_fleet_scans_only_immediate_children_and_reports_missing_explicit_path(self) -> None:
        self.init()
        child = self.root / "nested" / "project"
        child.mkdir(parents=True)
        self.run_relay("init", "--project-root", str(child), "--adapters", "minimal", "--yes")
        result = subprocess.run([sys.executable, str(FLEET), "--root", str(self.root),
                                 "--project", str(self.root / "missing"), "--json"],
                                check=True, capture_output=True, text=True)
        rows = json.loads(result.stdout)
        self.assertEqual(len(rows), 2)
        self.assertNotIn(str(child), [item["path"] for item in rows])
        self.assertEqual(next(item for item in rows if item["project"] == "missing")["health"],
                         "uninitialized")

    def test_report_schema_declares_new_version_fields(self) -> None:
        self.init()
        report = self.json_output("report")
        schema = json.loads((SKILL.parent / "assets/report.schema.json").read_text())
        self.assertTrue(set(report["version_state"]).issubset(
            schema["properties"]["version_state"]["properties"]))


if __name__ == "__main__":
    unittest.main()
