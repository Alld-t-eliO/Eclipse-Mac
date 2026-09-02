from __future__ import annotations
import json
import getpass
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from eclipse.modules.audit import record
from eclipse.system.errors import EclipseError
from eclipse.system.runner import Result, shell_display


INTERVALS = {
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(days=7),
}


@dataclass(frozen=True)
class AutomationJob:
    name: str
    every: str
    command: tuple[str, ...]
    enabled: bool
    created_at: str
    last_run_at: str | None = None
    last_returncode: int | None = None


    @classmethod
    def from_record(cls, data: dict[str, Any]) -> AutomationJob:
        command = data.get("command", [])
        if not isinstance(command, list):
            command = []
        return cls(
            name=str(data.get("name", "")),
            every=str(data.get("every", "")),
            command=tuple(str(item) for item in command),
            enabled=bool(data.get("enabled", True)),
            created_at=str(data.get("created_at", "")),
            last_run_at=str(data["last_run_at"]) if data.get("last_run_at") else None,
            last_returncode=int(data["last_returncode"]) if data.get("last_returncode") is not None else None,
        )


    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "every": self.every,
            "command": list(self.command),
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run_at": self.last_run_at,
            "last_returncode": self.last_returncode,
        }


def default_automation_home() -> Path:
    override = os.environ.get("ECLIPSE_AUTOMATION_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "automation"


def registry_path(root: Path | None = None) -> Path:
    return (root or default_automation_home()).expanduser().resolve() / "jobs.json"


def history_path(root: Path | None = None) -> Path:
    return (root or default_automation_home()).expanduser().resolve() / "history.jsonl"


def validate_interval(value: str) -> str:
    if value not in INTERVALS:
        raise EclipseError("Invalid automation interval. Use hour, day, or week.")
    return value


def default_command(name: str) -> tuple[str, ...]:
    lowered = name.lower()
    if "security" in lowered or "scan" in lowered:
        return ("security", "scan", "--json")
    return ("scripts", "run", name)


def load_jobs(root: Path | None = None) -> dict[str, AutomationJob]:
    path = registry_path(root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EclipseError(f"Unreadable automation registry: {error}") from error
    if not isinstance(raw, list):
        raise EclipseError("Invalid automation registry: expected a list.")
    jobs: dict[str, AutomationJob] = {}
    for item in raw:
        if isinstance(item, dict):
            job = AutomationJob.from_record(item)
            if job.name:
                jobs[job.name] = job
    return jobs


def save_jobs(jobs: dict[str, AutomationJob], root: Path | None = None) -> None:
    path = registry_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        records = [job.to_record() for job in sorted(jobs.values(), key=lambda item: item.name)]
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
    except OSError as error:
        raise EclipseError(f"Unable to write automation registry: {error}") from error


def add_job(
    name: str,
    *,
    every: str,
    command: Iterable[str] | None = None,
    root: Path | None = None,
    overwrite: bool = False,
) -> AutomationJob:
    interval = validate_interval(every)
    jobs = load_jobs(root)
    if name in jobs and not overwrite:
        raise EclipseError(f"Automation already exists: {name}")
    job = AutomationJob(
        name=name,
        every=interval,
        command=tuple(command or default_command(name)),
        enabled=True,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    jobs[name] = job
    save_jobs(jobs, root)
    return job


def set_enabled(name: str, enabled: bool, *, root: Path | None = None) -> AutomationJob:
    jobs = load_jobs(root)
    if name not in jobs:
        raise EclipseError(f"Unknown automation: {name}")
    old = jobs[name]
    job = AutomationJob(old.name, old.every, old.command, enabled, old.created_at, old.last_run_at, old.last_returncode)
    jobs[name] = job
    save_jobs(jobs, root)
    return job


def is_due(job: AutomationJob, *, now: datetime | None = None) -> bool:
    if not job.enabled:
        return False
    if not job.last_run_at:
        return True
    try:
        last = datetime.fromisoformat(job.last_run_at)
    except ValueError:
        return True
    return (now or datetime.now(timezone.utc)) - last >= INTERVALS[job.every]


def append_history(job: AutomationJob, result: Result, *, dry_run: bool, root: Path | None = None) -> None:
    path = history_path(root)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": getpass.getuser(),
        "job": job.name,
        "command": list(job.command),
        "dry_run": dry_run,
        "returncode": result.returncode,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        path.chmod(0o600)
    except OSError:
        pass


def run_job(name: str, *, root: Path | None = None, dry_run: bool = False) -> Result:
    jobs = load_jobs(root)
    if name not in jobs:
        raise EclipseError(f"Unknown automation: {name}")
    job = jobs[name]
    command = [sys.executable, "-m", "eclipse.core.cli", *job.command]
    if dry_run:
        result = Result(0, shell_display(command), "")
        append_history(job, result, dry_run=True, root=root)
        return result
    completed = subprocess.run(command, check=False, text=True)
    result = Result(completed.returncode, "", "")
    updated = AutomationJob(
        job.name,
        job.every,
        job.command,
        job.enabled,
        job.created_at,
        datetime.now(timezone.utc).isoformat(),
        completed.returncode,
    )
    jobs[name] = updated
    save_jobs(jobs, root)
    append_history(updated, result, dry_run=False, root=root)
    record("automation-run", success=completed.returncode == 0, details={"job": name, "code": completed.returncode})
    return result


def run_due(*, root: Path | None = None, dry_run: bool = False) -> list[tuple[AutomationJob, Result]]:
    results: list[tuple[AutomationJob, Result]] = []
    for job in load_jobs(root).values():
        if is_due(job):
            results.append((job, run_job(job.name, root=root, dry_run=dry_run)))
    return results


def load_history(root: Path | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    path = history_path(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]
