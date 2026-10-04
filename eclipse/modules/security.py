from __future__ import annotations

import json
import getpass
import html
import ipaddress
import plistlib
import os
import re
import shutil
import stat
import subprocess
import time
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from eclipse.system.errors import EclipseError
from eclipse.system.storage import atomic_write
from eclipse.modules.scan_history import comparable_checks, comparison_notes, known_result, report_rows, scan_profile


LEVEL_ORDER = {"OK": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
SUSPICIOUS_PLIST = re.compile(r"curl|wget|nc |netcat|base64|osascript|python|perl|ruby|chmod \+x|/tmp/|/var/tmp/", re.I)
DEFAULT_CHECKS = ("security", "firewall", "sharing", "network", "persistence", "services", "updates", "filesystem", "processes", "docker")
PASSWORD_ROTATION_DAYS = 183
SENSITIVE_DOCKER_MOUNTS = ("/", "/etc", "/var/run/docker.sock", "/Users", str(Path.home()))
REPORT_FORMATS = ("json", "markdown", "html")
INVENTORY_IDS = {
    "mac.firewall.apps", "mac.network.listeners", "mac.network.connections",
    "mac.persistence.launch_items", "mac.persistence.shell_startup",
    "mac.services.brew_services", "mac.services.brew_taps",
    "mac.processes.top_cpu", "mac.processes.top_memory", "docker.containers",
}


@dataclass(frozen=True)
class Finding:
    level: str
    category: str
    title: str
    detail: str = ""
    remediation: str = ""
    id: str = ""
    status: str = ""
    source: str = ""
    evidence: str = ""
    timestamp: str = ""
    risk: int = 0
    check: str = ""

    def to_record(self) -> dict[str, str | int]:
        record: dict[str, str | int] = {
            "level": self.level,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "remediation": self.remediation,
        }
        for key in ("id", "status", "source", "evidence", "timestamp", "check"):
            value = getattr(self, key)
            if value:
                record[key] = value
        if self.risk:
            record["risk"] = self.risk
        return record


@dataclass(frozen=True)
class SecurityCheck:
    name: str
    label: str
    category: str
    runner: Callable[[], list[Finding]]
    deep: bool = False
    description: str = ""


@dataclass(frozen=True)
class PasswordStatus:
    changed: bool
    expired: bool
    last_confirmed_at: str | None
    user: str
    next_due_at: str | None


def default_security_state_path() -> Path:
    override = os.environ.get("ECLIPSE_SECURITY_STATE_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "security-state.json"


def password_status(path: Path | None = None, *, now: datetime | None = None) -> PasswordStatus:
    state_path = path or default_security_state_path()
    user = getpass.getuser()
    if not state_path.exists():
        return PasswordStatus(False, True, None, user, None)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PasswordStatus(False, True, None, user, None)
    if not isinstance(data, dict):
        return PasswordStatus(False, True, None, user, None)
    confirmed = data.get("passwords_changed_at")
    if not confirmed:
        return PasswordStatus(False, True, None, str(data.get("user") or user), None)
    try:
        confirmed_at = datetime.fromisoformat(str(confirmed))
    except ValueError:
        return PasswordStatus(False, True, None, str(data.get("user") or user), None)
    if confirmed_at.tzinfo is None:
        confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)
    due_at = confirmed_at + timedelta(days=PASSWORD_ROTATION_DAYS)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return PasswordStatus(True, current >= due_at or confirmed_at > current, confirmed_at.isoformat(), str(data.get("user") or user), due_at.isoformat())


def confirm_password_rotation(path: Path | None = None, *, user: str | None = None) -> PasswordStatus:
    state_path = path or default_security_state_path()
    payload = {
        "passwords_changed_at": datetime.now(timezone.utc).isoformat(),
        "user": user or getpass.getuser(),
    }
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(state_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        state_path.chmod(0o600)
    except OSError as error:
        raise EclipseError(f"Unable to write security state: {error}") from error
    return password_status(state_path)


def format_password_status(status: PasswordStatus) -> str:
    if not status.changed:
        return "Passwords: confirmation required (red)"
    if status.expired:
        return f"Passwords: renewal due since {status.next_due_at} (red)"
    return f"Passwords: OK until {status.next_due_at} (green)"


_command_cache: ContextVar[dict | None] = ContextVar("scan_command_cache", default=None)
_command_errors: ContextVar[list | None] = ContextVar("scan_command_errors", default=None)


def run_text(command: list[str], *, timeout: int = 10) -> tuple[int, str, str]:
    cache = _command_cache.get()
    key = (tuple(command), timeout)
    if cache is not None and key in cache:
        result = cache[key]
    else:
        result = _execute_text(command, timeout=timeout)
        if cache is not None:
            cache[key] = result
    code, output, error = result
    # lsof returns 1 when no matching sockets exist, without an error message.
    empty_lsof = command[0] == "lsof" and code == 1 and not output and not error
    errors = _command_errors.get()
    if code and not empty_lsof and errors is not None:
        errors.append({"command": command, "returncode": code, "error": error})
    return result


def _execute_text(command: list[str], *, timeout: int) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, "", str(error)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def available(program: str) -> bool:
    return shutil.which(program) is not None


def finding(
    level: str,
    category: str,
    title: str,
    detail: str = "",
    remediation: str = "",
    *,
    id: str = "",
    status: str = "",
    source: str = "",
    evidence: str = "",
    risk: int = 0,
) -> Finding:
    if level not in LEVEL_ORDER:
        raise EclipseError(f"Invalid finding level: {level}")
    return Finding(
        level,
        category,
        title,
        detail,
        remediation,
        id=id,
        status=status or ("info" if level == "INFO" and id in INVENTORY_IDS else status_for_level(level)),
        source=source,
        evidence=evidence,
        timestamp=datetime.now(timezone.utc).isoformat(),
        risk=risk or risk_for_level(level),
    )


def status_for_level(level: str) -> str:
    return {
        "OK": "pass",
        "INFO": "unknown",
        "WARNING": "warn",
        "ERROR": "fail",
        "CRITICAL": "fail",
    }.get(level, "unknown")


def risk_for_level(level: str) -> int:
    return {"WARNING": 8, "ERROR": 10, "CRITICAL": 25}.get(level, 0)


def parse_filevault_status(text: str) -> str:
    lowered = text.lower()
    if "filevault is on" in lowered:
        return "on"
    if "filevault is off" in lowered:
        return "off"
    if "deferred" in lowered:
        return "deferred"
    if "encrypting" in lowered:
        return "encrypting"
    return "unknown"


def parse_gatekeeper_status(text: str) -> str:
    lowered = text.lower()
    if "assessments enabled" in lowered:
        return "enabled"
    if "assessments disabled" in lowered:
        return "disabled"
    return "unknown"


def parse_sip_status(text: str) -> str:
    lowered = text.lower()
    if "disabled" in lowered:
        return "disabled"
    if "enabled" in lowered:
        return "enabled"
    return "unknown"


def parse_firewall_state(text: str) -> str:
    lowered = text.lower()
    if "enabled" in lowered or "state = 1" in lowered or "stealth mode is on" in lowered:
        return "enabled"
    if "disabled" in lowered or "state = 0" in lowered or "stealth mode is off" in lowered:
        return "disabled"
    return "unknown"


def parse_firewall_apps(text: str) -> tuple[str, ...]:
    apps: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\d+\s*:", stripped):
            apps.append(stripped)
    return tuple(apps)


def check_filevault() -> list[Finding]:
    code, stdout, stderr = run_text(["fdesetup", "status"])
    text = stdout or stderr
    state = parse_filevault_status(text)
    if state == "on":
        return [finding("OK", "security", "FileVault enabled", stdout, id="mac.filevault.enabled", source="fdesetup status", evidence=text)]
    if state == "encrypting":
        return [finding("INFO", "security", "FileVault encryption in progress", text, id="mac.filevault.enabled", source="fdesetup status", evidence=text)]
    if state == "deferred":
        return [
            finding(
                "INFO",
                "security",
                "FileVault enablement deferred",
                text,
                "Complete the deferred FileVault enablement by logging out or following the fdesetup guidance.",
                id="mac.filevault.enabled",
                source="fdesetup status",
                evidence=text,
            )
        ]
    if state == "off":
        return [
            finding(
                "WARNING",
                "security",
                "FileVault disabled",
                text,
                "Enable FileVault in System Settings > Privacy & Security.",
                id="mac.filevault.enabled",
                source="fdesetup status",
                evidence=text,
            )
        ]
    _, apfs, _ = run_text(["diskutil", "apfs", "list"], timeout=20)
    encrypted = [line for line in apfs.splitlines() if "FileVault" in line or "Encrypted:" in line]
    if encrypted:
        return [finding("INFO", "security", "FileVault needs review", "\n".join(encrypted[:10]), id="mac.filevault.enabled", source="diskutil apfs list")]
    if code:
        return [finding("INFO", "security", "FileVault could not be verified", text, id="mac.filevault.enabled", source="fdesetup status", evidence=text)]
    return [finding("INFO", "security", "FileVault needs review", text, id="mac.filevault.enabled", source="fdesetup status", evidence=text)]


def check_gatekeeper() -> list[Finding]:
    code, stdout, stderr = run_text(["spctl", "--status"])
    if code:
        return [finding("INFO", "security", "Gatekeeper could not be verified", stderr, id="mac.gatekeeper.enabled", source="spctl --status", evidence=stderr)]
    state = parse_gatekeeper_status(stdout)
    if state == "enabled":
        return [finding("OK", "security", "Gatekeeper enabled", stdout, id="mac.gatekeeper.enabled", source="spctl --status", evidence=stdout)]
    if state == "unknown":
        return [finding("INFO", "security", "Gatekeeper needs review", stdout, id="mac.gatekeeper.enabled", source="spctl --status", evidence=stdout)]
    return [
        finding(
            "WARNING",
            "security",
            "Gatekeeper disabled",
            stdout,
            "Re-enable Gatekeeper with spctl after reviewing the configuration.",
            id="mac.gatekeeper.enabled",
            source="spctl --status",
            evidence=stdout,
        )
    ]


def check_sip() -> list[Finding]:
    code, stdout, stderr = run_text(["csrutil", "status"])
    if code:
        return [finding("INFO", "security", "SIP could not be verified", stderr, id="mac.sip.enabled", source="csrutil status", evidence=stderr)]
    state = parse_sip_status(stdout)
    if state == "enabled":
        return [finding("OK", "security", "System Integrity Protection enabled", stdout, id="mac.sip.enabled", source="csrutil status", evidence=stdout)]
    if state == "unknown":
        return [finding("INFO", "security", "System Integrity Protection needs review", stdout, id="mac.sip.enabled", source="csrutil status", evidence=stdout)]
    return [
        finding(
            "CRITICAL",
            "security",
            "System Integrity Protection disabled",
            stdout,
            "Re-enable SIP from recoveryOS with csrutil enable.",
            id="mac.sip.enabled",
            source="csrutil status",
            evidence=stdout,
        )
    ]


def check_xprotect() -> list[Finding]:
    bundle = Path("/Library/Apple/System/Library/CoreServices/XProtect.bundle")
    if not bundle.exists():
        return [finding("INFO", "security", "XProtect not detected at the standard path", id="mac.xprotect.detected", source=str(bundle))]
    _, version, _ = run_text(["defaults", "read", str(bundle / "Contents/Info"), "CFBundleShortVersionString"])
    return [finding("OK", "security", "XProtect detected", version, id="mac.xprotect.detected", source="defaults read XProtect Info", evidence=version)]


def check_firewall() -> list[Finding]:
    tool = Path("/usr/libexec/ApplicationFirewall/socketfilterfw")
    if not tool.exists():
        return [finding("INFO", "firewall", "Firewall utility not found", id="mac.firewall.available", source=str(tool))]
    results: list[Finding] = []
    code, state, error = run_text([str(tool), "--getglobalstate"])
    firewall_state = parse_firewall_state(state) if not code else "unknown"
    state = state or error
    if firewall_state == "enabled":
        results.append(finding("OK", "firewall", "Application firewall enabled", state, id="mac.firewall.enabled", source="socketfilterfw --getglobalstate", evidence=state))
    elif firewall_state == "disabled":
        results.append(
            finding(
                "WARNING",
                "firewall",
                "Application firewall disabled",
                state,
                "Enable the firewall in System Settings > Network > Firewall.",
                id="mac.firewall.enabled",
                source="socketfilterfw --getglobalstate",
                evidence=state,
            )
        )
    else:
        results.append(finding("INFO", "firewall", "Application firewall needs review", state, id="mac.firewall.enabled", source="socketfilterfw --getglobalstate", evidence=state))
    code, stealth, error = run_text([str(tool), "--getstealthmode"])
    stealth_state = parse_firewall_state(stealth) if not code else "unknown"
    stealth = stealth or error
    level = "OK" if stealth_state == "enabled" else "INFO"
    results.append(finding(level, "firewall", "Stealth mode", stealth, id="mac.firewall.stealth", status="unknown" if stealth_state == "unknown" else "pass" if stealth_state == "enabled" else "info", source="socketfilterfw --getstealthmode", evidence=stealth))
    code, apps, error = run_text([str(tool), "--listapps"], timeout=20)
    if code:
        results.append(finding("INFO", "firewall", "Firewall rules could not be read", error, status="unknown", id="mac.firewall.apps", source="socketfilterfw --listapps"))
    elif apps:
        app_rules = parse_firewall_apps(apps)
        results.append(finding("INFO", "firewall", f"Application firewall rules: {len(app_rules)}", limit_lines(apps, 20), id="mac.firewall.apps", source="socketfilterfw --listapps"))
    return results


def check_sharing() -> list[Finding]:
    code, listeners, error = run_text(["lsof", "+c", "0", "-nP", "-iTCP", "-sTCP:LISTEN"], timeout=15)
    if code and (code != 1 or error.strip()):
        return [finding("INFO", "sharing", "Sharing listeners could not be inspected", error, id="mac.sharing.remote_services", status="unknown", source="lsof TCP LISTEN")]
    selected = [line for line in listeners.splitlines() if re.search(r"screensharing|sshd|smbd|sharingd|rapportd|remoted", line, re.I)]
    if not selected:
        return [finding("OK", "sharing", "No monitored remote sharing service detected", id="mac.sharing.remote_services", source="lsof TCP LISTEN")]
    remote = [line for line in selected if re.search(r"^(?:screensharing\S*|sshd|smbd)\s", line, re.I)]
    exposed = [line for line in remote if not listener_is_loopback(line)]
    return [
        finding(
            "WARNING" if exposed else "INFO",
            "sharing",
            "Sharing listeners on non-loopback or unidentified interfaces" if exposed else "Local sharing-related listeners detected",
            "\n".join(selected[:20]),
            "Review enabled services in System Settings > General > Sharing. A listening socket alone does not establish Internet reachability or a vulnerability.",
            id="mac.sharing.remote_services",
            status="warn" if exposed else "info",
            source="lsof TCP LISTEN",
        )
    ]


def listener_is_loopback(line: str) -> bool:
    match = re.search(r"\bTCP\s+(\S+)", line)
    if not match:
        return False
    host = match.group(1).rsplit(":", 1)[0].strip("[]")
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_network() -> list[Finding]:
    results: list[Finding] = []
    for state, label, check_id in (("LISTEN", "Listening TCP ports", "mac.network.listeners"),
                                    ("ESTABLISHED", "Established TCP connections", "mac.network.connections")):
        code, output, error = run_text(["lsof", "+c", "0", "-nP", "-iTCP", f"-sTCP:{state}"], timeout=15)
        if code and not (code == 1 and not output and not error):
            results.append(finding("INFO", "network", f"{label} could not be inspected", error, status="unknown", id=check_id, source="lsof"))
        else:
            count = max(0, len(output.splitlines()) - 1)
            results.append(finding("INFO", "network", f"{label}: {count}", limit_lines(output, 20), status="info", id=check_id, source="lsof"))
    code, proxy, error = run_text(["scutil", "--proxy"])
    if code or not proxy:
        results.append(finding("INFO", "network", "Proxy configuration could not be inspected", error, status="unknown", id="mac.network.proxy", source="scutil --proxy"))
    else:
        enabled_proxy = [line for line in proxy.splitlines() if re.search(r"Enable\s*:\s*1", line)]
        level = "WARNING" if enabled_proxy else "OK"
        results.append(finding(level, "network", "Proxy configuration", limit_lines(proxy, 20), "Review configured proxies if you did not add them intentionally." if enabled_proxy else "", id="mac.network.proxy", source="scutil --proxy"))
    return results


def check_persistence() -> list[Finding]:
    results: list[Finding] = []
    plist_paths = launch_plists()
    if plist_paths:
        results.append(finding("INFO", "persistence", f"Third-party LaunchAgents/Daemons: {len(plist_paths)}", "\n".join(str(path) for path in plist_paths[:30]), id="mac.persistence.launch_items", source="LaunchAgents/LaunchDaemons"))
    else:
        results.append(finding("OK", "persistence", "No third-party LaunchAgent/Daemon detected", id="mac.persistence.launch_items", source="LaunchAgents/LaunchDaemons"))
    suspicious = []
    unreadable = []
    for path in plist_paths:
        try:
            if suspicious_plist(path):
                suspicious.append(path)
        except (OSError, ValueError, plistlib.InvalidFileException):
            unreadable.append(path)
    if suspicious:
        results.append(finding("WARNING", "persistence", "Persistence commands need review", "\n".join(str(path) for path in suspicious[:30]), "Inspect ProgramArguments, owner, and referenced binaries. Matching a command pattern alone does not establish malicious behavior.", id="mac.persistence.suspicious_plists", source="LaunchAgent/Daemon Program and ProgramArguments"))
    if unreadable:
        results.append(finding("INFO", "persistence", "Some launch items could not be inspected", "\n".join(map(str, unreadable)), status="unknown", id="mac.persistence.unreadable", source="plistlib"))
    startup = [path for path in shell_startup_files() if path.exists()]
    if startup:
        details = "\n".join(f"{path} | {mode_owner(path)}" for path in startup)
        results.append(finding("INFO", "persistence", "Shell startup files present", details, id="mac.persistence.shell_startup", source="shell startup files"))
    return results


def check_services() -> list[Finding]:
    if not available("brew"):
        return [finding("INFO", "services", "Homebrew not installed", id="mac.services.homebrew", status="not_applicable", source="shutil.which")]
    results: list[Finding] = []
    code, services, error = run_text(["brew", "services", "list"], timeout=20)
    if code:
        results.append(finding("INFO", "services", "Homebrew services could not be inspected", error, status="unknown", id="mac.services.brew_services", source="brew services list"))
    elif services:
        results.append(finding("INFO", "services", "Homebrew services", limit_lines(services, 30), id="mac.services.brew_services", source="brew services list"))
    code, taps, error = run_text(["brew", "tap"], timeout=20)
    if code:
        results.append(finding("INFO", "services", "Homebrew taps could not be inspected", error, status="unknown", id="mac.services.brew_taps", source="brew tap"))
        return results
    custom = [tap for tap in taps.splitlines() if tap and tap not in {"homebrew/core", "homebrew/cask", "homebrew/services"}]
    if custom:
        results.append(finding("INFO", "services", "Additional Homebrew taps", "\n".join(custom), "Review these repositories if you do not recognize them; their presence alone is not a security issue.", id="mac.services.brew_taps", source="brew tap"))
    else:
        results.append(finding("OK", "services", "Standard Homebrew taps", id="mac.services.brew_taps", source="brew tap"))
    return results


def check_updates(*, deep: bool = False) -> list[Finding]:
    if not deep:
        return [finding("INFO", "updates", "Update check not run", "Use --deep to run softwareupdate -l.", id="mac.updates.available", status="skipped", source="softwareupdate -l")]
    code, output, stderr = run_text(["softwareupdate", "-l"], timeout=120)
    text = output or stderr
    if code:
        return [finding("INFO", "updates", "Unable to check for updates", text, status="unknown", id="mac.updates.available", source="softwareupdate -l")]
    if "No new software available" in text:
        return [finding("OK", "updates", "No macOS update available", limit_lines(text, 20), id="mac.updates.available", source="softwareupdate -l")]
    return [finding("INFO", "updates", "macOS updates need review", limit_lines(text, 40), id="mac.updates.available", source="softwareupdate -l")]


def check_filesystem() -> list[Finding]:
    results: list[Finding] = []
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        results.append(finding("INFO", "filesystem", "No ~/.ssh directory detected", id="mac.filesystem.ssh_keys", status="not_applicable", source="~/.ssh"))
    else:
        loose: list[str] = []
        unreadable: list[str] = []
        identified = 0
        for path in ssh_dir.iterdir():
            if not path.is_file() or path.name in {"config", "known_hosts"} or path.suffix == ".pub":
                continue
            try:
                with path.open("rb") as stream:
                    prefix = stream.read(256)
                if not re.search(rb"-----BEGIN (?:OPENSSH |RSA |DSA |EC |ENCRYPTED )?PRIVATE KEY-----", prefix):
                    continue
                identified += 1
                mode = stat.S_IMODE(path.stat().st_mode)
            except OSError:
                unreadable.append(str(path))
                continue
            if mode & 0o077:
                loose.append(f"{path} | mode={mode:o}")
        if loose:
            results.append(finding("WARNING", "filesystem", "Local keys with broad permissions", "\n".join(loose), "Reduce private key permissions with chmod 600.", id="mac.filesystem.ssh_keys", source="~/.ssh"))
        elif identified:
            results.append(finding("OK", "filesystem", "Local key permissions are restrictive", id="mac.filesystem.ssh_keys", source="~/.ssh"))
        else:
            results.append(finding("INFO", "filesystem", "No recognized private key found", id="mac.filesystem.ssh_keys", status="info", source="~/.ssh"))
        if unreadable:
            results.append(finding("INFO", "filesystem", "Some SSH files could not be inspected", "\n".join(unreadable), id="mac.filesystem.ssh_unreadable", status="unknown", source="~/.ssh"))
    writable = world_writable_paths()
    shared = [path for path in writable if path == Path.home() / "Public" / "Drop Box" and not path.is_symlink() and path.stat().st_uid == os.getuid()]
    review = [path for path in writable if path not in shared]
    if shared:
        results.append(finding("INFO", "filesystem", "User-owned public Drop Box is world-writable",
                               "\n".join(f"{path} | {mode_owner(path)}" for path in shared),
                               "This is a file-drop location. Confirm you intend to accept files here; its presence alone is not evidence of compromise.",
                               id="mac.filesystem.public_dropbox", status="info", source="os.walk (depth 2)"))
    if review:
        results.append(finding("WARNING", "filesystem", "World-writable directories need context review", "\n".join(f"{path} | {mode_owner(path)}" for path in review[:30]), "Other local users may be able to write here. Check the purpose, owner and permissions before changing them; application caches may be intentionally shared.", id="mac.filesystem.world_writable", source="os.walk (depth 2)"))
    else:
        results.append(finding("OK", "filesystem", "No other world-writable directory found in inspected paths", id="mac.filesystem.world_writable", source="os.walk (depth 2)"))
    if getattr(writable, "incomplete", False):
        results.append(finding("INFO", "filesystem", "Directory inspection incomplete", "Some paths could not be read or the 50-result limit was reached. Inspection is limited to depth 2 under home and system LaunchAgents/Daemons.", status="unknown", id="mac.filesystem.coverage", source="os.walk"))
    return results


def check_processes() -> list[Finding]:
    results: list[Finding] = []
    code, cpu, error = run_text(["ps", "-axo", "pid,user,%cpu,%mem,command"], timeout=15)
    if code or not cpu:
        return [finding("INFO", "processes", "Processes could not be inspected", error, status="unknown", id="mac.processes.available", source="ps")]
    if cpu:
        rows = sorted(cpu.splitlines()[1:], key=lambda line: numeric_column(line, 2), reverse=True)
        results.append(finding("INFO", "processes", "Top CPU", "\n".join([cpu.splitlines()[0], *rows[:10]]), id="mac.processes.top_cpu", source="ps"))
        rows = sorted(cpu.splitlines()[1:], key=lambda line: numeric_column(line, 3), reverse=True)
        results.append(finding("INFO", "processes", "Top memory", "\n".join([cpu.splitlines()[0], *rows[:10]]), id="mac.processes.top_memory", source="ps"))
    return results


def check_docker() -> list[Finding]:
    if not available("docker"):
        return [finding("INFO", "docker", "Docker not installed", id="docker.available", status="not_applicable", source="shutil.which")]
    code, _, _ = run_text(["docker", "info"], timeout=15)
    if code:
        return [finding("INFO", "docker", "Docker runtime could not be inspected", "The daemon may be stopped or inaccessible. Container checks were not performed.", id="docker.daemon", status="skipped", source="docker info")]
    results = [finding("OK", "docker", "Docker daemon active", id="docker.daemon", source="docker info")]
    code, containers, error = run_text(["docker", "ps", "-a", "--format", "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"], timeout=20)
    if code:
        results.append(finding("INFO", "docker", "Docker containers could not be listed", error, status="unknown", id="docker.containers", source="docker ps -a"))
    elif containers:
        results.append(finding("INFO", "docker", "Docker containers", limit_lines(containers, 30), id="docker.containers", source="docker ps -a"))
        exposed = docker_exposed_ports(containers)
        if exposed:
            results.append(
                finding(
                    "WARNING",
                    "docker",
                    "Docker ports published on non-loopback host interfaces",
                    "\n".join(exposed[:20]),
                    "Review whether each published port needs a non-loopback binding. This does not establish Internet reachability; firewall and routing also matter.",
                    id="docker.containers.exposed_ports",
                    source="docker ps -a",
                )
            )
        weak_images = docker_weak_image_tags(containers)
        if weak_images:
            results.append(
                finding(
                    "WARNING",
                    "docker",
                    "Docker containers use weak image tags",
                    "\n".join(weak_images[:20]),
                    "Pin images to explicit maintained versions instead of latest or untagged image IDs.",
                    id="docker.images.weak_tags",
                    source="docker ps -a",
                )
            )
    code, container_ids, error = run_text(["docker", "ps", "-aq"], timeout=20)
    if code:
        results.append(finding("INFO", "docker", "Docker runtime inspection incomplete", error, status="unknown", id="docker.runtime.inspection", source="docker ps -aq"))
        return results
    ids = [item for item in container_ids.splitlines() if item.strip()]
    if ids:
        code, inspect, error = run_text(
            ["docker", "inspect", "--format", "{{.Name}}\t{{.HostConfig.Privileged}}\t{{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}", *ids],
            timeout=20,
        )
        if code:
            results.append(finding("INFO", "docker", "Docker runtime inspection incomplete", error, status="unknown", id="docker.runtime.inspection", source="docker inspect"))
            return results
        risky_runtime = docker_risky_runtime(inspect)
        if risky_runtime:
            results.append(
                finding(
                    "WARNING",
                    "docker",
                    "Docker containers use risky runtime settings",
                    "\n".join(risky_runtime[:20]),
                    "Disable privileged mode and avoid mounting sensitive host paths unless they are required.",
                    id="docker.runtime.risky_settings",
                    source="docker inspect",
                )
            )
    return results


def docker_exposed_ports(text: str) -> list[str]:
    rows = docker_rows(text)
    exposed: list[str] = []
    for row in rows:
        for host in re.findall(r"(\[[^\]]+\]|[0-9a-fA-F:.]+):\d+->", row):
            try:
                loopback = ipaddress.ip_address(host.strip("[]")).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                exposed.append(row)
                break
    return exposed


def docker_weak_image_tags(text: str) -> list[str]:
    weak: list[str] = []
    for row in docker_rows(text):
        parts = row.split(maxsplit=2)
        if len(parts) < 2:
            continue
        image = parts[1]
        if image == "<none>" or image.endswith(":latest") or ":" not in image.rsplit("/", 1)[-1]:
            weak.append(row)
    return weak


def docker_risky_runtime(text: str) -> list[str]:
    risky: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        name, privileged, mounts = split_docker_inspect_line(line)
        reasons: list[str] = []
        if privileged.lower() == "true":
            reasons.append("privileged=true")
        for mount in mounts.split():
            source = mount.split(":", 1)[0]
            if source in SENSITIVE_DOCKER_MOUNTS:
                reasons.append(f"sensitive_mount={source}")
        if reasons:
            risky.append(f"{name or 'container'} {' '.join(reasons)}")
    return risky


def docker_rows(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lower().startswith("names")]


def split_docker_inspect_line(line: str) -> tuple[str, str, str]:
    parts = line.split("\t", 2)
    if len(parts) == 3:
        return parts[0].lstrip("/"), parts[1], parts[2]
    if len(parts) == 2:
        return parts[0].lstrip("/"), parts[1], ""
    return line.strip().lstrip("/"), "", ""


def security_checks(*, deep: bool = False) -> dict[str, SecurityCheck]:
    return {
        "security": SecurityCheck(
            "security",
            "Apple controls",
            "security",
            lambda: check_filevault() + check_gatekeeper() + check_sip() + check_xprotect(),
            description="FileVault, Gatekeeper, SIP, and XProtect.",
        ),
        "firewall": SecurityCheck("firewall", "Firewall", "firewall", check_firewall, description="Application firewall state, stealth mode, and app rules."),
        "sharing": SecurityCheck("sharing", "Remote sharing", "sharing", check_sharing, description="Remote sharing services visible through local listeners."),
        "network": SecurityCheck("network", "Network", "network", check_network, description="Listening ports, established TCP connections, and proxy state."),
        "persistence": SecurityCheck("persistence", "Persistence", "persistence", check_persistence, description="LaunchAgents, LaunchDaemons, and shell startup files."),
        "services": SecurityCheck("services", "Services", "services", check_services, description="Homebrew services and non-standard taps."),
        "updates": SecurityCheck("updates", "Updates", "updates", lambda: check_updates(deep=deep), deep=True, description="macOS software update availability when --deep is enabled."),
        "filesystem": SecurityCheck("filesystem", "Sensitive files", "filesystem", check_filesystem, description="SSH key permissions and sensitive world-writable directories."),
        "processes": SecurityCheck("processes", "Processes", "processes", check_processes, description="Top local CPU and memory consumers."),
        "docker": SecurityCheck("docker", "Docker", "docker", check_docker, description="Docker installation, daemon, and local containers."),
    }


def list_checks() -> tuple[SecurityCheck, ...]:
    checks = security_checks()
    return tuple(checks[name] for name in DEFAULT_CHECKS)


class ScanFindings(list[Finding]):
    """List-compatible results retaining the actual execution coverage."""

    def __init__(self, requested: tuple[str, ...], deep: bool):
        super().__init__()
        self.scan = {"revision": 1, "requested": list(requested), "deep": deep, "checks": {}}


def run_checks(checks: Iterable[str] = DEFAULT_CHECKS, *, deep: bool = False,
               progress: Callable[[int, int, str, str], None] | None = None) -> ScanFindings:
    dispatch = security_checks(deep=deep)
    requested = tuple(dict.fromkeys(checks))
    for check in requested:
        if check not in dispatch:
            raise EclipseError(f"Unknown check: {check}")
    results = ScanFindings(requested, deep)
    cache_token = _command_cache.set({})
    try:
        for index, check in enumerate(requested, 1):
            label = dispatch[check].label
            if progress:
                progress(index, len(requested), label, "running")
            started = time.monotonic()
            errors: list[dict] = []
            error_token = _command_errors.set(errors)
            failed = False
            try:
                rows = dispatch[check].runner()
                if not rows:
                    rows = [finding("INFO", dispatch[check].category, "No result returned by this check", status="unknown", id=f"scan.{check}.empty")]
            except (OSError, ValueError, EclipseError, subprocess.TimeoutExpired) as error:
                failed = True
                rows = [finding("INFO", dispatch[check].category, f"{label} could not be completed", str(error), status="unknown", id=f"scan.{check}.failed")]
            finally:
                _command_errors.reset(error_token)
            states = {row.status or status_for_level(row.level) for row in rows}
            state = ("failed" if failed else "skipped" if states == {"skipped"}
                     else "not_applicable" if states == {"not_applicable"}
                     else "partial" if errors or states & {"unknown", "skipped"} else "completed")
            if errors and not states & {"unknown", "skipped"}:
                rows.append(finding("INFO", dispatch[check].category, f"{label}: some commands failed",
                                    "\n".join(f"{' '.join(item['command'])}: exit {item['returncode']}" for item in errors),
                                    status="unknown", id=f"scan.{check}.commands"))
            results.extend(replace(row, check=check, status=row.status or status_for_level(row.level)) for row in rows)
            results.scan["checks"][check] = {"status": state, "duration_seconds": round(time.monotonic() - started, 3), "command_errors": errors}
            if progress:
                progress(index, len(requested), label, state)
    finally:
        _command_cache.reset(cache_token)
    return results


def summary(findings: Iterable[Finding]) -> dict[str, int]:
    counts = {level: 0 for level in LEVEL_ORDER}
    for item in findings:
        counts[item.level] += 1
    return counts


def security_score(findings: Iterable[Finding]) -> int:
    penalties = {"WARNING": 8, "ERROR": 10, "CRITICAL": 25}
    score = 100
    for item in findings:
        score -= penalties.get(item.level, 0)
    return max(0, score)


def default_report_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "security-reports"


def default_baseline_path() -> Path:
    override = os.environ.get("ECLIPSE_SECURITY_BASELINE_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "security-baseline.json"


def default_policy_path() -> Path:
    override = os.environ.get("ECLIPSE_SECURITY_POLICY_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "security-policy.json"


def write_report(findings: list[Finding], destination: Path | None = None) -> Path:
    root = (destination or default_report_dir()).expanduser()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = next_report_path(root, stamp)
    payload = report_payload(findings)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        path.chmod(0o600)
    except OSError as error:
        raise EclipseError(f"Unable to write security report: {error}") from error
    return path


def report_payload(findings: list[Finding]) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "scan": findings.scan if isinstance(findings, ScanFindings) else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user": getpass.getuser(),
        "score": security_score(findings),
        "summary": summary(findings),
        "findings": [item.to_record() for item in findings],
    }


def next_report_path(root: Path, stamp: str) -> Path:
    path = root / f"security-{stamp}.json"
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = root / f"security-{stamp}-{index}.json"
        if not candidate.exists():
            return candidate
        index += 1


def load_reports(directory: Path | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    if limit < 1:
        raise EclipseError("Report limit must be positive.")
    folder = (directory or default_report_dir()).expanduser()
    if not folder.exists():
        return []
    reports: list[dict[str, Any]] = []
    candidates = []
    for path in folder.glob("*.json"):
        try:
            candidates.append((path.stat().st_mtime_ns, path.name, path))
        except OSError:
            continue
    for _, _, path in sorted(candidates, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("findings"), list) and all(isinstance(row, dict) for row in payload["findings"]):
            payload["_path"] = str(path)
            reports.append(payload)
            if len(reports) == limit:
                break
    return list(reversed(reports))


def load_latest_report(directory: Path | None = None) -> dict[str, Any]:
    reports = load_reports(directory, limit=1)
    if not reports:
        raise EclipseError("No security report found.")
    return reports[0]


def save_baseline(findings: list[Finding], path: Path | None = None) -> Path:
    target = (path or default_baseline_path()).expanduser()
    payload = report_payload(findings)
    payload["kind"] = "security-baseline"
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        target.chmod(0o600)
    except OSError as error:
        raise EclipseError(f"Unable to write security baseline: {error}") from error
    return target


def load_baseline(path: Path | None = None) -> dict[str, Any]:
    target = (path or default_baseline_path()).expanduser()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EclipseError(f"Security baseline not found: {target}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise EclipseError(f"Unreadable security baseline: {error}") from error
    if not isinstance(payload, dict):
        raise EclipseError("Invalid security baseline: expected an object.")
    payload["_path"] = str(target)
    return payload


def compare_baseline(findings: list[Finding], path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    current = report_payload(findings)
    return diff_reports(load_baseline(path), current)


def format_report_history(reports: list[dict[str, Any]]) -> str:
    if not reports:
        return "No security reports."
    lines: list[str] = []
    for report in reversed(reports):
        summary_text = report.get("summary", {})
        lines.append(f"{report.get('created_at', '')} score={report.get('score', '')} {summary_text}")
        lines.append(f"  {report.get('_path', '')}")
    return "\n".join(lines)


def default_policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "minimum_alert_level": "WARNING",
        "required_checks": list(DEFAULT_CHECKS),
        "ignored_finding_ids": [],
        "level_overrides": {
            "mac.firewall.enabled": "CRITICAL",
            "mac.sip.enabled": "CRITICAL",
            "mac.filevault.enabled": "WARNING",
        },
    }


def write_default_policy(path: Path | None = None, *, overwrite: bool = False) -> Path:
    target = (path or default_policy_path()).expanduser()
    if target.exists() and not overwrite:
        raise EclipseError(f"Security policy already exists: {target}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(target, json.dumps(default_policy(), ensure_ascii=False, indent=2) + "\n")
        target.chmod(0o600)
    except OSError as error:
        raise EclipseError(f"Unable to write security policy: {error}") from error
    return target


def load_policy(path: Path | None = None) -> dict[str, Any]:
    target = (path or default_policy_path()).expanduser()
    if not target.exists():
        return default_policy()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EclipseError(f"Unreadable security policy: {error}") from error
    if not isinstance(payload, dict):
        raise EclipseError("Invalid security policy: expected an object.")
    policy = default_policy()
    policy.update(payload)
    return policy


def evaluate_policy(findings: list[Finding], policy: dict[str, Any] | None = None, *, checks: Iterable[str] = DEFAULT_CHECKS) -> dict[str, Any]:
    active_policy = policy or load_policy()
    ignored = {str(item) for item in active_policy.get("ignored_finding_ids", []) if item}
    overrides = active_policy.get("level_overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}
    minimum = str(active_policy.get("minimum_alert_level") or "WARNING")
    minimum_order = LEVEL_ORDER.get(minimum, LEVEL_ORDER["WARNING"])
    required = {str(item) for item in active_policy.get("required_checks", []) if item}
    selected = set(findings.scan["requested"]) if isinstance(findings, ScanFindings) else set(checks)
    missing_required = sorted(required - selected)
    incomplete_required = sorted(name for name in required & selected
                                 if isinstance(findings, ScanFindings) and findings.scan["checks"][name]["status"] not in {"completed", "not_applicable"})
    alerts: list[dict[str, Any]] = []
    for item in findings:
        record = item.to_record()
        check_id = str(record.get("id", ""))
        if check_id in ignored:
            continue
        level = str((overrides.get(check_id) if known_result(record) else None) or record.get("level") or "INFO")
        if LEVEL_ORDER.get(level, 0) >= minimum_order:
            record["policy_level"] = level
            alerts.append(record)
    return {"policy": active_policy, "alerts": alerts, "missing_required_checks": missing_required, "incomplete_required_checks": incomplete_required}


def format_policy(policy: dict[str, Any]) -> str:
    lines = [
        f"Minimum alert level: {policy.get('minimum_alert_level', 'WARNING')}",
        f"Required checks: {', '.join(str(item) for item in policy.get('required_checks', []))}",
        f"Ignored finding ids: {', '.join(str(item) for item in policy.get('ignored_finding_ids', [])) or 'none'}",
        "Level overrides:",
    ]
    overrides = policy.get("level_overrides", {})
    if isinstance(overrides, dict) and overrides:
        for check_id, level in sorted(overrides.items()):
            lines.append(f"  {check_id}: {level}")
    else:
        lines.append("  none")
    return "\n".join(lines)


def format_policy_evaluation(result: dict[str, Any]) -> str:
    alerts = result.get("alerts", [])
    missing = result.get("missing_required_checks", [])
    lines = [f"Policy alerts: {len(alerts)}"]
    for item in alerts[:30]:
        lines.append(f"  [{item.get('policy_level', item.get('level', ''))}] {finding_key(item)} - {item.get('title', '')}")
    if missing:
        lines.append(f"Missing required checks: {', '.join(str(item) for item in missing)}")
    if result.get("incomplete_required_checks"):
        lines.append("Incomplete required checks: " + ", ".join(result["incomplete_required_checks"]))
    return "\n".join(lines)


def finding_key(record: dict[str, Any]) -> str:
    return str(record.get("id") or f"{record.get('category', '')}:{record.get('title', '')}")


def diff_reports(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    previous_findings = {finding_key(item): item for item in report_rows(previous)}
    current_findings = {finding_key(item): item for item in report_rows(current)}
    added = [current_findings[key] for key in sorted(current_findings.keys() - previous_findings.keys())]
    removed = [previous_findings[key] for key in sorted(previous_findings.keys() - current_findings.keys())]
    common_checks = comparable_checks(previous, current)
    legacy = previous.get("scan") is None and current.get("scan") is None
    unverified = []
    for item in added + removed:
        if item.get("check") not in common_checks:
            unverified.append(item)
    new_risk = [item for item in added if item.get("check") in common_checks and LEVEL_ORDER.get(str(item.get("level")), 0) >= LEVEL_ORDER["WARNING"]]
    resolved = [item for item in removed if item.get("check") in common_checks and known_result(item) and LEVEL_ORDER.get(str(item.get("level")), 0) >= LEVEL_ORDER["WARNING"]]
    changed: list[dict[str, Any]] = []
    worse: list[dict[str, Any]] = []
    better: list[dict[str, Any]] = []
    for key in sorted(previous_findings.keys() & current_findings.keys()):
        before = previous_findings[key]
        after = current_findings[key]
        if any(before.get(field) != after.get(field) for field in ("level", "status", "title", "detail", "evidence")):
            item = {"id": key, "before": before, "after": after}
            changed.append(item)
            before_level = LEVEL_ORDER.get(str(before.get("level")), 0)
            after_level = LEVEL_ORDER.get(str(after.get("level")), 0)
            same_check = before.get("check") == after.get("check") and after.get("check") in common_checks
            comparable = (legacy or same_check) and known_result(before) and known_result(after)
            if not comparable:
                unverified.append(item)
            elif after_level > before_level:
                worse.append(item)
            elif after_level < before_level:
                better.append(item)
    return {"added": added, "removed": removed, "changed": changed, "new_risk": new_risk, "resolved": resolved, "worse": worse, "better": better, "unverified": unverified,
            "notes": [{"message": note} for note in comparison_notes(previous, current)]}


def format_report_diff(previous: dict[str, Any], current: dict[str, Any]) -> str:
    diff = diff_reports(previous, current)
    lines = [
        f"Previous: {previous.get('created_at', '')} score={previous.get('score', '')}",
        f"Current : {current.get('created_at', '')} score={current.get('score', '')}",
    ]
    lines.extend(format_diff_categories(diff).splitlines())
    return "\n".join(lines)


def format_diff_categories(diff: dict[str, list[dict[str, Any]]]) -> str:
    lines: list[str] = [item["message"] for item in diff.get("notes", [])]
    lines.append(f"Unverified changes: {len(diff.get('unverified', []))}")
    for label in ("added", "removed"):
        items = diff[label]
        lines.append(f"{label.title()}: {len(items)}")
        for item in items[:20]:
            lines.append(f"  [{item.get('level', '')}] {finding_key(item)} - {item.get('title', '')}")
    changed = diff["changed"]
    lines.append(f"Changed: {len(changed)}")
    for item in changed[:20]:
        before = item["before"]
        after = item["after"]
        lines.append(f"  {item['id']}: {before.get('level', '')} -> {after.get('level', '')}")
    for label in ("new_risk", "resolved", "worse", "better"):
        items = diff[label]
        lines.append(f"{label.replace('_', ' ').title()}: {len(items)}")
        for item in items[:20]:
            if "before" in item and "after" in item:
                before = item["before"]
                after = item["after"]
                lines.append(f"  {item['id']}: {before.get('level', '')} -> {after.get('level', '')}")
            else:
                lines.append(f"  [{item.get('level', '')}] {finding_key(item)} - {item.get('title', '')}")
    return "\n".join(lines)


def latest_report_pair(directory: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    reports = load_reports(directory, limit=2)
    if len(reports) < 2:
        raise EclipseError("At least two security reports are required for diff.")
    return reports[0], reports[1]


def export_report(report: dict[str, Any], destination: Path, *, format: str) -> Path:
    if format not in REPORT_FORMATS:
        raise EclipseError(f"Unsupported report format: {format}")
    target = destination.expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if format == "json":
            atomic_write(target, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        elif format == "markdown":
            atomic_write(target, report_markdown(report))
        else:
            atomic_write(target, report_html(report))
    except OSError as error:
        raise EclipseError(f"Unable to export security report: {error}") from error
    return target


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Eclipse Security Report",
        "",
        f"- Created at: {report.get('created_at', '')}",
        f"- User: {report.get('user', '')}",
        f"- Score: {report.get('score', '')}/100",
        f"- Summary: {report.get('summary', {})}",
        f"- Coverage: {coverage_text(report)}",
        "",
        "## Findings",
        "",
    ]
    for item in report.get("findings", []):
        if not isinstance(item, dict):
            continue
        lines.append(f"### [{item.get('level', '')}] {item.get('title', '')}")
        lines.append("")
        lines.append(f"- ID: {finding_key(item)}")
        lines.append(f"- Category: {item.get('category', '')}")
        lines.append(f"- Status: {item.get('status', '')}")
        if item.get("remediation"):
            lines.append(f"- Remediation: {item.get('remediation')}")
        if item.get("detail"):
            lines.append("")
            lines.append("```text")
            lines.append(str(item.get("detail", "")))
            lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def report_html(report: dict[str, Any]) -> str:
    rows: list[str] = []
    for item in report.get("findings", []):
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('level', '')))}</td>"
            f"<td>{html.escape(finding_key(item))}</td>"
            f"<td>{html.escape(str(item.get('category', '')))}</td>"
            f"<td>{html.escape(str(item.get('title', '')))}</td>"
            f"<td>{html.escape(str(item.get('remediation', '')))}</td>"
            "</tr>"
        )
    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\"><title>Eclipse Security Report</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:32px;line-height:1.4}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}"
        "th{background:#f5f5f5}</style></head><body>"
        "<h1>Eclipse Security Report</h1>"
        f"<p><strong>Created at:</strong> {html.escape(str(report.get('created_at', '')))}<br>"
        f"<strong>User:</strong> {html.escape(str(report.get('user', '')))}<br>"
        f"<strong>Score:</strong> {html.escape(str(report.get('score', '')))}/100</p>"
        f"<p><strong>Coverage:</strong> {html.escape(coverage_text(report))}</p>"
        "<table><thead><tr><th>Level</th><th>ID</th><th>Category</th><th>Title</th><th>Remediation</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>\n"
    )


def remediation_plan(findings: Iterable[Finding | dict[str, Any]]) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for item in findings:
        record = item.to_record() if isinstance(item, Finding) else item
        level = str(record.get("level", "INFO"))
        if level == "OK":
            continue
        remediation = str(record.get("remediation") or default_remediation(str(record.get("id", ""))))
        if not remediation:
            continue
        rows.append(
            {
                "id": str(record.get("id") or finding_key(record)),
                "level": level,
                "category": str(record.get("category", "")),
                "title": str(record.get("title", "")),
                "remediation": remediation,
                "risk": int(record.get("risk") or risk_for_level(level)),
            }
        )
    return sorted(rows, key=lambda row: (int(row["risk"]), LEVEL_ORDER.get(str(row["level"]), 0)), reverse=True)


def default_remediation(check_id: str) -> str:
    defaults = {
        "mac.filevault.enabled": "Enable FileVault in System Settings > Privacy & Security.",
        "mac.gatekeeper.enabled": "Re-enable Gatekeeper after reviewing why assessments are disabled.",
        "mac.sip.enabled": "Re-enable SIP from recoveryOS with csrutil enable.",
        "mac.firewall.enabled": "Enable the application firewall in System Settings > Network > Firewall.",
        "mac.firewall.stealth": "Enable stealth mode if this Mac should not respond to unsolicited probes.",
        "mac.network.proxy": "Remove unexpected proxy settings from System Settings > Network.",
        "mac.persistence.suspicious_plists": "Inspect the listed LaunchAgent or LaunchDaemon files and remove entries you do not recognize.",
        "mac.filesystem.ssh_keys": "Set private SSH key permissions to 600.",
        "mac.filesystem.world_writable": "Remove world-writable permissions from sensitive directories.",
        "docker.containers.exposed_ports": "Restrict published Docker ports to required interfaces and services.",
        "docker.images.weak_tags": "Pin Docker images to explicit maintained versions.",
        "docker.runtime.risky_settings": "Disable privileged containers and remove sensitive host path mounts.",
    }
    return defaults.get(check_id, "")


def format_remediation_plan(rows: list[dict[str, str | int]]) -> str:
    if not rows:
        return "No remediation needed."
    lines = ["Remediation plan:"]
    for index, item in enumerate(rows, 1):
        lines.append(f"{index}. [{item['level']}] {item['id']} - {item['title']}")
        lines.append(f"   Risk: {item['risk']}")
        lines.append(f"   Action: {item['remediation']}")
    return "\n".join(lines)


def coverage_text(report: dict) -> str:
    profile = scan_profile(report)
    if profile is None:
        return "Execution coverage not recorded."
    scan = report["scan"]
    states = ", ".join(f"{name}: {scan['checks'][name]['status']}" for name in profile[2])
    return f"Deep mode: {scan['deep']}. {states}"


def format_scan_summary(findings: list[Finding]) -> str:
    """Concise UI result; raw evidence remains in the full report."""
    groups = (
        ("PROTECTIONS / CHECKS PASSED", [item for item in findings if item.level == "OK"]),
        ("NEEDS REVIEW", sorted([item for item in findings if item.level in {"WARNING", "ERROR", "CRITICAL"}],
                                key=lambda item: LEVEL_ORDER[item.level], reverse=True)),
        ("NOT CHECKED / UNCERTAIN", [item for item in findings if (item.status or status_for_level(item.level)) in {"unknown", "skipped"}]),
    )
    lines = ["SCAN SUMMARY", ""]
    if isinstance(findings, ScanFindings):
        states = [row["status"] for row in findings.scan["checks"].values()]
        lines += [f"Coverage: {states.count('completed')}/{len(states)} checks completed; "
                  f"{sum(state in {'partial', 'failed'} for state in states)} incomplete; "
                  f"{sum(state in {'skipped', 'not_applicable'} for state in states)} skipped / not applicable.", ""]
    if not findings:
        return "SCAN SUMMARY\nNo results available; protection status could not be assessed."
    for title, items in groups:
        lines.append(f"{title} ({len(items)})")
        for item in items[:5]:
            label = f"[{item.level}] " if title == "NEEDS REVIEW" else ""
            lines.append(f"  {label}{item.title}")
        if len(items) > 5:
            lines.append(f"  + {len(items) - 5} more in the full report")
        if not items:
            lines.append("  None reported.")
        lines.append("")
    inventory = sum(item.status in {"info", "not_applicable"} for item in findings)
    lines.append(f"{inventory} inventory / not-applicable results available in the full report.")
    lines.append("Results cover the checks performed; they do not guarantee the whole Mac is secure.")
    return "\n".join(lines)


def format_findings(findings: list[Finding]) -> str:
    unknown = sum((item.status or status_for_level(item.level)) == "unknown" for item in findings)
    categories = sorted({item.category for item in findings})
    score = f"{security_score(findings)}/100" if findings else "unavailable (no findings)"
    lines = [f"Security score: {score} (heuristic)",
             "Scoring: starts at 100; WARNING -8, ERROR -10, CRITICAL -25; minimum 0.",
             f"Reported categories: {', '.join(categories) or 'none'}",
             f"Results: {len(findings)} total, {unknown} unknown. Unknown results do not lower the score.",
             "This score applies only to the reported findings, not the whole Mac.",
             f"Summary: {summary(findings)}", ""]
    if isinstance(findings, ScanFindings):
        lines.insert(1, "Coverage: " + coverage_text({"scan": findings.scan}))
    for item in sorted(findings, key=lambda value: LEVEL_ORDER[value.level], reverse=True):
        lines.append(f"[{item.level}] {item.category} - {item.title}")
        if item.detail:
            lines.append(indent(limit_lines(item.detail, 8)))
        if item.remediation:
            lines.append(indent(f"Fix: {item.remediation}"))
    return "\n".join(lines).strip()


def launch_plists() -> list[Path]:
    roots = [Path.home() / "Library/LaunchAgents", Path("/Library/LaunchAgents"), Path("/Library/LaunchDaemons")]
    paths: list[Path] = []
    for root in roots:
        if root.exists():
            paths.extend(sorted(path for path in root.iterdir() if path.suffix == ".plist"))
    return paths


def suspicious_plist(path: Path) -> bool:
    with path.open("rb") as stream:
        payload = plistlib.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("Launch item must contain a dictionary.")
    arguments = payload.get("ProgramArguments", [])
    if not isinstance(arguments, list):
        raise ValueError("ProgramArguments must be a list.")
    text = " ".join(str(value) for value in [payload.get("Program", ""), *arguments])
    return bool(SUSPICIOUS_PLIST.search(text))


def shell_startup_files() -> list[Path]:
    home = Path.home()
    return [home / ".zshrc", home / ".zprofile", home / ".bash_profile", home / ".bashrc", home / ".profile"]


class InspectedPaths(list[Path]):
    incomplete = False


def world_writable_paths() -> list[Path]:
    roots = [Path.home(), Path("/Library/LaunchAgents"), Path("/Library/LaunchDaemons")]
    found = InspectedPaths()
    def unreadable(error: OSError) -> None:
        found.incomplete = True
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, _ in os.walk(root, onerror=unreadable):
            current = Path(dirpath)
            try:
                depth = len(current.relative_to(root).parts)
                if depth >= 2:
                    dirnames[:] = []
                if current.stat().st_mode & stat.S_IWOTH:
                    found.append(current)
            except OSError:
                found.incomplete = True
                continue
            if len(found) >= 50:
                found.incomplete = True
                return found
    return found


def mode_owner(path: Path) -> str:
    try:
        info = path.stat()
    except OSError:
        return "inaccessible"
    return f"mode={stat.S_IMODE(info.st_mode):o} uid={info.st_uid} gid={info.st_gid}"


def numeric_column(line: str, index: int) -> float:
    parts = line.split(maxsplit=4)
    try:
        return float(parts[index])
    except (IndexError, ValueError):
        return 0.0


def limit_lines(text: str, limit: int) -> str:
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    return "\n".join(lines[:limit] + [f"... {len(lines) - limit} hidden lines"])


def indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())
