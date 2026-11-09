#!/usr/bin/env python3
"""Read-only status audit for an explicitly supplied set of Relay projects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

sys.dont_write_bytecode = True
from relay import Relay, RelayError, redact_string, sanitize


def project_roots(projects: Iterable[str], parents: Iterable[str]) -> List[Path]:
    found: Dict[str, Path] = {}

    def add(path: Path, explicit: bool = False) -> None:
        path = path.expanduser().absolute()
        if explicit or (path / ".agent-relay").exists():
            found[str(path)] = path

    for value in projects:
        add(Path(value), explicit=True)
    for value in parents:
        parent = Path(value).expanduser().absolute()
        if parent.is_symlink() or not parent.is_dir():
            raise RelayError("Scan root must be a directory, not a symlink: %s" % parent)
        add(parent)
        for child in sorted(parent.iterdir()):
            if child.is_dir() and not child.is_symlink():
                add(child)
    return [found[key] for key in sorted(found)]


def run_json(project: Path, command: str) -> Dict[str, Any]:
    try:
        if project.is_symlink():
            raise RelayError("Project symlinks are not scanned")
        if not project.is_dir():
            return {"health": "uninitialized", "error": "Project directory is missing"}
        relay = Relay(project)
        # Validate canonical state before doctor traverses adapters and manifests.
        if relay.config_path.exists():
            relay.require_initialized()
        if command == "doctor" and not relay.config_path.exists():
            return {"health": "uninitialized"}
        if command == "report":
            return relay.report_data()
        return relay.doctor()
    except (OSError, RelayError, UnicodeError, ValueError, TypeError, AttributeError, KeyError) as exc:
        detail = redact_string(str(exc)).replace("\n", " ")[:240]
        return {"health": "degraded", "error": detail or "audit failed"}


def summarize(project: Path) -> Dict[str, Any]:
    report = run_json(project, "report")
    doctor = run_json(project, "doctor")
    return sanitize({
        "project": project.name,
        "path": str(project),
        "health": report.get("health", "degraded"),
        "doctor_health": doctor.get("health", "degraded"),
        "runtime_version": report.get("runtime_version") or doctor.get("installed_runtime_version"),
        "runtime_sha256": doctor.get("runtime_sha256"),
        "reader_version": doctor.get("runtime_version"),
        "migration_required": report.get("migration_required"),
        "state_schema_version": report.get("state_schema_version"),
        "coordination_mode": (report.get("coordination") or {}).get("mode"),
        "doctor_issues": [
            check for check in doctor.get("checks", []) if check.get("status") in ("warn", "fail")
        ],
        "updated_at": report.get("updated_at"),
        "active_tasks": (
            len(report["active_work"]) if "active_work" in report and report["health"] != "degraded" else None
        ),
        "blocked_tasks": (
            len(report["blocked_work"]) if "blocked_work" in report else None
        ),
        "blockers": report.get("blockers") or [],
        "unsealed_changes": (report.get("version_state") or {}).get("unsealed_changes"),
        "drift_basis": (report.get("version_state") or {}).get("drift_basis"),
        "artifact_drift": (report.get("version_state") or {}).get("artifact_drift"),
        "issues": report.get("issues") or [],
        "error": report.get("error") or doctor.get("error"),
    })


def render(rows: List[Dict[str, Any]]) -> str:
    lines = ["Agent Relay fleet report", ""]
    for row in rows:
        lines.append(
            "%s | runtime=%s | report=%s | doctor=%s | active=%s | blocked=%s | drift=%s (%s)"
            % (
                row["project"],
                row["runtime_version"] or "unknown",
                row["health"],
                row["doctor_health"],
                row["active_tasks"],
                row["blocked_tasks"] if row["blocked_tasks"] is not None else "?",
                row["unsealed_changes"],
                row["drift_basis"] or "unknown",
            )
        )
        if row["blockers"]:
            lines.append("  blockers: %s" % "; ".join(row["blockers"]))
        if row["issues"]:
            lines.append("  issues: %s" % "; ".join(row["issues"]))
        if row["error"]:
            lines.append("  error: %s" % row["error"])
        for check in row["doctor_issues"]:
            lines.append("  doctor %s: %s" % (check["name"], check["detail"]))
    if not rows:
        lines.append("No initialized projects found in the supplied paths.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Agent Relay status audit for explicit project paths."
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Initialized project path; repeatable.",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Project or parent directory; inspect the directory and its immediate children.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)
    if not args.project and not args.root:
        parser.error("supply at least one --project or --root path")
    try:
        rows = [summarize(path) for path in project_roots(args.project, args.root)]
    except (OSError, RelayError) as exc:
        print("Audit failed: %s" % redact_string(str(exc)), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
