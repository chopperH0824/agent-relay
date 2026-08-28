from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional


REPO = Path(__file__).resolve().parents[1]
SOURCE_RUNTIME = REPO / "skills" / "agent-relay" / "scripts" / "relay.py"
SKILL = REPO / "skills" / "agent-relay" / "SKILL.md"


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


if __name__ == "__main__":
    unittest.main()
