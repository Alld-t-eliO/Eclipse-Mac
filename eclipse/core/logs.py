from __future__ import annotations

import getpass
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .audit import default_log_path
from .automation import history_path as automation_history_path
from .errors import EclipseError
from .scripts import history_path as scripts_history_path
from .security import default_report_dir


LOG_SOURCES = ("audit", "scripts", "automation", "security", "system")


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    user: str
    source: str
    action: str
    status: str
    detail: str

    def to_record(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "user": self.user,
            "source": self.source,
            "action": self.action,
            "status": self.status,
            "detail": self.detail,
        }


def current_user() -> str:
    try:
        return getpass.getuser()
    except OSError:
        return os.environ.get("USER", "unknown")


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise EclipseError(f"Unreadable log: {path} ({error})") from error
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def normalize_timestamp(value: object) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    return str(value)


def audit_logs(path: Path | None = None) -> list[LogEntry]:
    rows = []
    for item in parse_jsonl(path or default_log_path()):
        details = item.get("details", {})
        event = str(item.get("event", ""))
        if event.startswith("remote-") or event in {"upload", "download"}:
            continue
        rows.append(
            LogEntry(
                timestamp=normalize_timestamp(item.get("timestamp")),
                user=str(item.get("user") or current_user()),
                source="audit",
                action=event or "event",
                status="ok" if item.get("success") else "failed",
                detail=json.dumps(details, ensure_ascii=False) if details else "",
            )
        )
    return rows


def script_logs(path: Path | None = None) -> list[LogEntry]:
    rows = []
    for item in parse_jsonl(path or scripts_history_path()):
        code = item.get("returncode")
        rows.append(
            LogEntry(
                timestamp=normalize_timestamp(item.get("timestamp")),
                user=str(item.get("user") or current_user()),
                source="scripts",
                action=str(item.get("script") or "script"),
                status=f"code={code}" if code is not None else "unknown",
                detail=f"dry_run={item.get('dry_run')} path={item.get('path', '')}",
            )
        )
    return rows


def automation_logs(path: Path | None = None) -> list[LogEntry]:
    rows = []
    for item in parse_jsonl(path or automation_history_path()):
        code = item.get("returncode")
        command = item.get("command", [])
        detail = " ".join(str(part) for part in command) if isinstance(command, list) else str(command)
        rows.append(
            LogEntry(
                timestamp=normalize_timestamp(item.get("timestamp")),
                user=str(item.get("user") or current_user()),
                source="automation",
                action=str(item.get("job") or "automation"),
                status=f"code={code}" if code is not None else "unknown",
                detail=f"dry_run={item.get('dry_run')} command={detail}",
            )
        )
    return rows


def security_logs(directory: Path | None = None) -> list[LogEntry]:
    folder = (directory or default_report_dir()).expanduser()
    if not folder.exists():
        return []
    rows: list[LogEntry] = []
    for path in sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        timestamp = data.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        summary = data.get("summary", {})
        rows.append(
            LogEntry(
                timestamp=normalize_timestamp(timestamp),
                user=str(data.get("user") or current_user()),
                source="security",
                action="security-report",
                status=f"score={data.get('score', '')}",
                detail=f"{path} {summary}",
            )
        )
    return rows


def system_logs(*, limit: int = 50, last: str = "1h") -> list[LogEntry]:
    command = ["log", "show", "--style", "compact", "--last", last, "--predicate", "process == \"kernel\"", "--info"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EclipseError(f"System logs unavailable: {error}") from error
    if completed.returncode != 0:
        raise EclipseError(completed.stderr.strip() or "System logs unavailable.")
    rows: list[LogEntry] = []
    for line in completed.stdout.splitlines()[-limit:]:
        if not line.strip():
            continue
        parts = line.split(maxsplit=2)
        timestamp = " ".join(parts[:2]) if len(parts) >= 2 else datetime.now(timezone.utc).isoformat()
        detail = parts[2] if len(parts) >= 3 else line
        rows.append(LogEntry(timestamp=timestamp, user=current_user(), source="system", action="macos-log", status="info", detail=detail))
    return rows


def collect_logs(
    sources: Iterable[str] | None = None,
    *,
    limit: int = 100,
    user: str | None = None,
    query: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_system: bool = False,
) -> list[LogEntry]:
    selected = tuple(sources or ("audit", "scripts", "automation", "security"))
    unknown = [source for source in selected if source not in LOG_SOURCES]
    if unknown:
        raise EclipseError(f"Unknown log source: {', '.join(unknown)}")
    rows: list[LogEntry] = []
    if "audit" in selected:
        rows.extend(audit_logs())
    if "scripts" in selected:
        rows.extend(script_logs())
    if "automation" in selected:
        rows.extend(automation_logs())
    if "security" in selected:
        rows.extend(security_logs())
    if "system" in selected or include_system:
        rows.extend(system_logs(limit=limit))
    query_text = query.lower() if query else None
    since_value = datetime.fromisoformat(since).timestamp() if since else None
    until_value = datetime.fromisoformat(until).timestamp() if until else None
    filtered: list[LogEntry] = []
    for row in rows:
        if user and row.user != user:
            continue
        haystack = " ".join((row.timestamp, row.user, row.source, row.action, row.status, row.detail)).lower()
        if query_text and query_text not in haystack:
            continue
        try:
            stamp = datetime.fromisoformat(row.timestamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            stamp = None
        if stamp is not None and since_value is not None and stamp < since_value:
            continue
        if stamp is not None and until_value is not None and stamp > until_value:
            continue
        filtered.append(row)
    return sorted(filtered, key=lambda item: item.timestamp)[-limit:]


def format_log(entry: LogEntry) -> str:
    return f"{entry.timestamp}  {entry.user}  {entry.source}  {entry.action}  {entry.status}  {entry.detail}"


def export_logs(entries: list[LogEntry], destination: Path) -> Path:
    target = destination.expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps([entry.to_record() for entry in entries], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise EclipseError(f"Unable to export logs: {error}") from error
    return target.resolve()
