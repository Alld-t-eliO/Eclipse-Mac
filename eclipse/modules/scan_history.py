"""Conservative comparison of recorded scan coverage (including legacy reports)."""
from __future__ import annotations


def report_rows(report: dict) -> list[dict]:
    rows = report.get("findings", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def scan_profile(report: dict) -> tuple | None:
    scan = report.get("scan")
    if not isinstance(scan, dict):
        return None
    requested, checks = scan.get("requested"), scan.get("checks")
    if (not isinstance(requested, list) or not requested or
            not all(isinstance(name, str) and name for name in requested) or
            not isinstance(checks, dict) or not isinstance(scan.get("deep"), bool) or
            type(scan.get("revision")) is not int):
        return None
    if any(not isinstance(checks.get(name), dict) or checks[name].get("status") not in
           {"completed", "partial", "failed", "skipped", "not_applicable"} for name in requested):
        return None
    return scan["revision"], scan["deep"], tuple(sorted(set(requested)))


def comparable_checks(previous: dict, current: dict) -> set[str]:
    profile = scan_profile(previous)
    if profile is None or profile != scan_profile(current):
        return set()
    def has_usable_results(report: dict, name: str) -> bool:
        rows = [row for row in report_rows(report) if row.get("check") == name]
        return bool(rows) and all(row.get("level") in {"OK", "INFO", "WARNING", "ERROR", "CRITICAL"}
                                  and row.get("status") in {"pass", "info", "warn", "fail", "not_applicable"} for row in rows)
    return {name for name in profile[2]
            if previous["scan"]["checks"][name]["status"] == "completed"
            and current["scan"]["checks"][name]["status"] == "completed"
            and has_usable_results(previous, name) and has_usable_results(current, name)}


def comparison_notes(previous: dict, current: dict) -> list[str]:
    before, after = scan_profile(previous), scan_profile(current)
    if before is None or after is None:
        return ["Execution coverage unavailable in a legacy or incomplete report. Two legacy reports can compare explicit known results with matching IDs; missing findings are never resolved alerts."]
    if before != after:
        return ["Scan selections, deep mode or check revision differ; no risk changes can be confirmed."]
    excluded = set(after[2]) - comparable_checks(previous, current)
    return ["Not comparable (incomplete, skipped or not applicable): " + ", ".join(sorted(excluded))] if excluded else []


def known_result(row: dict) -> bool:
    return row.get("level") in {"OK", "WARNING", "ERROR", "CRITICAL"} and row.get("status") not in {"unknown", "skipped", "not_applicable"}
