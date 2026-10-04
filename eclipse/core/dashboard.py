"""Read-only daily overview built from saved local activity."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from eclipse.core.logs import collect_logs
from eclipse.modules.automation import is_due, load_jobs
from eclipse.modules.security import LEVEL_ORDER, diff_reports, load_reports
from eclipse.system.errors import EclipseError


@dataclass
class Overview:
    attention: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    activity: list[str] = field(default_factory=list)


def report_findings(report: dict) -> list[dict]:
    rows = report.get("findings", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def report_scope(report: dict) -> set[str]:
    return {str(row.get("category", "")) for row in report_findings(report)}


def security_overview(reports: list[dict], *, now: datetime | None = None) -> Overview:
    overview = Overview()
    if not reports:
        overview.attention.append("No saved scan yet. Start with [1] Check my Mac.")
        overview.changes.append("Changes appear after two scans covering the same categories.")
        return overview
    latest = reports[-1]
    rows = report_findings(latest)
    stamp = str(latest.get("created_at", "unknown date"))
    overview.attention.append(f"Last saved scan: {stamp}")
    try:
        scanned_at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if scanned_at.tzinfo is None:
            scanned_at = scanned_at.replace(tzinfo=timezone.utc)
        if (now or datetime.now(timezone.utc)) - scanned_at > timedelta(days=7):
            overview.attention.append("Scan older than 7 days. Refresh with [1].")
    except ValueError:
        overview.attention.append("Scan date unavailable. Refresh with [1].")
    risks = sorted((row for row in rows if LEVEL_ORDER.get(str(row.get("level")), 0) >= 2),
                   key=lambda row: LEVEL_ORDER[str(row["level"])], reverse=True)
    for row in risks[:3]:
        overview.attention.append(f"[{row['level']}] {row.get('title', 'Finding')} — review with [2]")
    if len(risks) > 3:
        overview.attention.append(f"{len(risks) - 3} more alerts in [2].")
    unknown = sum(row.get("status", "unknown" if row.get("level") == "INFO" else "") == "unknown" for row in rows)
    overview.attention.append(f"{len(risks)} alerts; {unknown} unknown results; {len(report_scope(latest))} categories represented.")
    if not rows:
        overview.attention.append("No findings available. Run a new scan with [1].")
    previous = next((report for report in reversed(reports[:-1])
                     if report_scope(report) == report_scope(latest) and rows), None)
    if previous is None:
        overview.changes.append("No earlier scan covering the same categories to compare.")
    else:
        changes = diff_reports(previous, latest)
        overview.changes.append(f"Compared with {previous.get('created_at', 'previous scan')}:")
        overview.changes.append(
            f"{len(changes['new_risk'])} new alerts, {len(changes['worse'])} worse, "
            f"{len(changes['better'])} improved, {len(changes['resolved'])} alerts no longer reported.")
    return overview


def load_overview() -> Overview:
    try:
        overview = security_overview(load_reports(limit=20))
    except (EclipseError, OSError, ValueError) as error:
        overview = Overview(attention=[f"Security history unavailable: {error}"])
    try:
        jobs = list(load_jobs().values())
        due = sum(is_due(job) for job in jobs)
        failed = sum(job.last_returncode not in (None, 0) for job in jobs)
        if due or failed:
            overview.attention.append(f"Automations: {due} due, {failed} last runs failed — review with [4].")
    except (EclipseError, OSError, ValueError) as error:
        overview.attention.append(f"Automations unavailable: {error}")
    try:
        overview.activity = [f"{row.timestamp} · {row.action} · {row.status}"
                             for row in reversed(collect_logs(limit=3))]
    except (EclipseError, OSError, ValueError) as error:
        overview.activity = [f"Recent activity unavailable: {error}"]
    return overview
