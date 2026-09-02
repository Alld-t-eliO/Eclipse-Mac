from __future__ import annotations

import json
import getpass
import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from eclipse.system.errors import EclipseError


LEVEL_ORDER = {"OK": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
SUSPICIOUS_PLIST = re.compile(r"curl|wget|nc |netcat|base64|osascript|python|perl|ruby|chmod \+x|/tmp/|/var/tmp/", re.I)
DEFAULT_CHECKS = ("security", "firewall", "sharing", "network", "persistence", "services", "updates", "filesystem", "processes", "docker")
PASSWORD_ROTATION_DAYS = 183


@dataclass(frozen=True)
class Finding:
    level: str
    category: str
    title: str
    detail: str = ""
    remediation: str = ""

    def to_record(self) -> dict[str, str]:
        return {
            "level": self.level,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "remediation": self.remediation,
        }


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
    confirmed = data.get("passwords_changed_at")
    if not confirmed:
        return PasswordStatus(False, True, None, str(data.get("user") or user), None)
    try:
        confirmed_at = datetime.fromisoformat(str(confirmed))
    except ValueError:
        return PasswordStatus(False, True, None, str(data.get("user") or user), None)
    due_at = confirmed_at + timedelta(days=PASSWORD_ROTATION_DAYS)
    current = now or datetime.now(timezone.utc)
    return PasswordStatus(True, current >= due_at, confirmed_at.isoformat(), str(data.get("user") or user), due_at.isoformat())


def confirm_password_rotation(path: Path | None = None, *, user: str | None = None) -> PasswordStatus:
    state_path = path or default_security_state_path()
    payload = {
        "passwords_changed_at": datetime.now(timezone.utc).isoformat(),
        "user": user or getpass.getuser(),
    }
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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


def run_text(command: list[str], *, timeout: int = 10) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, "", str(error)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def available(program: str) -> bool:
    return shutil.which(program) is not None


def finding(level: str, category: str, title: str, detail: str = "", remediation: str = "") -> Finding:
    if level not in LEVEL_ORDER:
        raise EclipseError(f"Invalid finding level: {level}")
    return Finding(level, category, title, detail, remediation)


def check_filevault() -> list[Finding]:
    code, stdout, stderr = run_text(["fdesetup", "status"])
    text = stdout or stderr
    if "FileVault is On" in text:
        return [finding("OK", "security", "FileVault enabled", stdout)]
    if "FileVault is Off" in text:
        return [finding("WARNING", "security", "FileVault disabled", text, "Enable FileVault in System Settings > Privacy & Security.")]
    _, apfs, _ = run_text(["diskutil", "apfs", "list"], timeout=20)
    encrypted = [line for line in apfs.splitlines() if "FileVault" in line or "Encrypted:" in line]
    if encrypted:
        return [finding("INFO", "security", "FileVault needs review", "\n".join(encrypted[:10]))]
    if code:
        return [finding("INFO", "security", "FileVault could not be verified", text)]
    return [finding("INFO", "security", "FileVault needs review", text)]


def check_gatekeeper() -> list[Finding]:
    code, stdout, stderr = run_text(["spctl", "--status"])
    if code:
        return [finding("ERROR", "security", "Gatekeeper could not be verified", stderr)]
    if "assessments enabled" in stdout:
        return [finding("OK", "security", "Gatekeeper enabled", stdout)]
    return [finding("WARNING", "security", "Gatekeeper disabled", stdout, "Re-enable Gatekeeper with spctl after reviewing the configuration.")]


def check_sip() -> list[Finding]:
    code, stdout, stderr = run_text(["csrutil", "status"])
    if code:
        return [finding("ERROR", "security", "SIP could not be verified", stderr)]
    if "enabled" in stdout.lower():
        return [finding("OK", "security", "System Integrity Protection enabled", stdout)]
    return [finding("CRITICAL", "security", "System Integrity Protection disabled", stdout, "Re-enable SIP from recoveryOS with csrutil enable.")]


def check_xprotect() -> list[Finding]:
    bundle = Path("/Library/Apple/System/Library/CoreServices/XProtect.bundle")
    if not bundle.exists():
        return [finding("INFO", "security", "XProtect not detected at the standard path")]
    _, version, _ = run_text(["defaults", "read", str(bundle / "Contents/Info"), "CFBundleShortVersionString"])
    return [finding("OK", "security", "XProtect detected", version)]


def check_firewall() -> list[Finding]:
    tool = Path("/usr/libexec/ApplicationFirewall/socketfilterfw")
    if not tool.exists():
        return [finding("ERROR", "firewall", "Firewall utility not found")]
    results: list[Finding] = []
    _, state, _ = run_text([str(tool), "--getglobalstate"])
    if "enabled" in state.lower():
        results.append(finding("OK", "firewall", "Application firewall enabled", state))
    else:
        results.append(finding("WARNING", "firewall", "Application firewall disabled", state, "Enable the firewall in System Settings > Network > Firewall."))
    _, stealth, _ = run_text([str(tool), "--getstealthmode"])
    level = "OK" if "enabled" in stealth.lower() else "INFO"
    results.append(finding(level, "firewall", "Stealth mode", stealth))
    _, apps, _ = run_text([str(tool), "--listapps"], timeout=20)
    if apps:
        results.append(finding("INFO", "firewall", "Application firewall rules", limit_lines(apps, 20)))
    return results


def check_sharing() -> list[Finding]:
    _, listeners, _ = run_text(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], timeout=15)
    selected = [line for line in listeners.splitlines() if re.search(r"screensharing|sshd|smbd|sharingd|rapportd|remoted", line, re.I)]
    if not selected:
        return [finding("OK", "sharing", "No monitored remote sharing service detected")]
    return [finding("WARNING", "sharing", "Remote sharing services need review", "\n".join(selected[:20]), "Review enabled services in System Settings > General > Sharing.")]


def check_network() -> list[Finding]:
    results: list[Finding] = []
    _, listeners, _ = run_text(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], timeout=15)
    if listeners:
        count = max(0, len(listeners.splitlines()) - 1)
        results.append(finding("INFO", "network", f"Listening TCP ports: {count}", limit_lines(listeners, 20)))
    else:
        results.append(finding("INFO", "network", "No listening TCP port detected"))
    _, connections, _ = run_text(["lsof", "-nP", "-iTCP", "-sTCP:ESTABLISHED"], timeout=15)
    if connections:
        count = max(0, len(connections.splitlines()) - 1)
        results.append(finding("INFO", "network", f"Established TCP connections: {count}", limit_lines(connections, 20)))
    else:
        results.append(finding("INFO", "network", "No established TCP connection detected"))
    _, proxy, _ = run_text(["scutil", "--proxy"])
    if proxy:
        enabled_proxy = [line for line in proxy.splitlines() if re.search(r"Enable\s*:\s*1", line)]
        level = "WARNING" if enabled_proxy else "OK"
        results.append(finding(level, "network", "Proxy configuration", limit_lines(proxy, 20), "Review configured proxies if you did not add them intentionally."))
    return results


def check_persistence() -> list[Finding]:
    results: list[Finding] = []
    plist_paths = launch_plists()
    if plist_paths:
        results.append(finding("INFO", "persistence", f"Third-party LaunchAgents/Daemons: {len(plist_paths)}", "\n".join(str(path) for path in plist_paths[:30])))
    else:
        results.append(finding("OK", "persistence", "No third-party LaunchAgent/Daemon detected"))
    suspicious = [path for path in plist_paths if suspicious_plist(path)]
    if suspicious:
        results.append(finding("WARNING", "persistence", "Suspicious commands in plist files", "\n".join(str(path) for path in suspicious[:30]), "Inspect ProgramArguments, owner, and referenced binary signatures."))
    startup = [path for path in shell_startup_files() if path.exists()]
    if startup:
        details = "\n".join(f"{path} | {mode_owner(path)}" for path in startup)
        results.append(finding("INFO", "persistence", "Shell startup files present", details))
    return results


def check_services() -> list[Finding]:
    if not available("brew"):
        return [finding("INFO", "services", "Homebrew not installed")]
    results: list[Finding] = []
    _, services, _ = run_text(["brew", "services", "list"], timeout=20)
    if services:
        results.append(finding("INFO", "services", "Homebrew services", limit_lines(services, 30)))
    _, taps, _ = run_text(["brew", "tap"], timeout=20)
    custom = [tap for tap in taps.splitlines() if tap and tap not in {"homebrew/core", "homebrew/cask", "homebrew/services"}]
    if custom:
        results.append(finding("WARNING", "services", "Non-standard Homebrew taps", "\n".join(custom), "Remove taps you do not recognize or no longer use."))
    else:
        results.append(finding("OK", "services", "Standard Homebrew taps"))
    return results


def check_updates(*, deep: bool = False) -> list[Finding]:
    if not deep:
        return [finding("INFO", "updates", "Update check not run", "Use --deep to run softwareupdate -l.")]
    code, output, stderr = run_text(["softwareupdate", "-l"], timeout=120)
    text = output or stderr
    if code and not text:
        return [finding("ERROR", "updates", "Unable to check for updates")]
    if "No new software available" in text:
        return [finding("OK", "updates", "No macOS update available", limit_lines(text, 20))]
    return [finding("INFO", "updates", "macOS updates need review", limit_lines(text, 40))]


def check_filesystem() -> list[Finding]:
    results: list[Finding] = []
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        results.append(finding("INFO", "filesystem", "No ~/.ssh directory detected"))
    else:
        loose: list[str] = []
        for path in ssh_dir.iterdir():
            if not path.is_file() or path.name in {"config", "known_hosts"} or path.suffix == ".pub":
                continue
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode > 0o600:
                loose.append(f"{path} | mode={mode:o}")
        if loose:
            results.append(finding("WARNING", "filesystem", "Local keys with broad permissions", "\n".join(loose), "Reduce private key permissions with chmod 600."))
        else:
            results.append(finding("OK", "filesystem", "Local key permissions are restrictive"))
    writable = world_writable_paths()
    if writable:
        results.append(finding("WARNING", "filesystem", "Sensitive world-writable directories", "\n".join(str(path) for path in writable[:30]), "Review owner and permissions for these directories."))
    else:
        results.append(finding("OK", "filesystem", "No sensitive world-writable directory detected"))
    return results


def check_processes() -> list[Finding]:
    results: list[Finding] = []
    _, cpu, _ = run_text(["ps", "-axo", "pid,user,%cpu,%mem,command"], timeout=15)
    if cpu:
        rows = sorted(cpu.splitlines()[1:], key=lambda line: numeric_column(line, 2), reverse=True)
        results.append(finding("INFO", "processes", "Top CPU", "\n".join([cpu.splitlines()[0], *rows[:10]])))
        rows = sorted(cpu.splitlines()[1:], key=lambda line: numeric_column(line, 3), reverse=True)
        results.append(finding("INFO", "processes", "Top memory", "\n".join([cpu.splitlines()[0], *rows[:10]])))
    return results


def check_docker() -> list[Finding]:
    if not available("docker"):
        return [finding("INFO", "docker", "Docker not installed")]
    code, _, _ = run_text(["docker", "info"], timeout=15)
    if code:
        return [finding("WARNING", "docker", "Docker installed but daemon unavailable")]
    results = [finding("OK", "docker", "Docker daemon active")]
    _, containers, _ = run_text(["docker", "ps", "-a", "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}"], timeout=20)
    if containers:
        results.append(finding("INFO", "docker", "Docker containers", limit_lines(containers, 30)))
    return results


def run_checks(checks: Iterable[str] = DEFAULT_CHECKS, *, deep: bool = False) -> list[Finding]:
    dispatch = {
        "security": lambda: check_filevault() + check_gatekeeper() + check_sip() + check_xprotect(),
        "firewall": check_firewall,
        "sharing": check_sharing,
        "network": check_network,
        "persistence": check_persistence,
        "services": check_services,
        "updates": lambda: check_updates(deep=deep),
        "filesystem": check_filesystem,
        "processes": check_processes,
        "docker": check_docker,
    }
    results: list[Finding] = []
    for check in checks:
        try:
            results.extend(dispatch[check]())
        except KeyError as error:
            raise EclipseError(f"Unknown check: {check}") from error
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


def write_report(findings: list[Finding], destination: Path | None = None) -> Path:
    root = (destination or default_report_dir()).expanduser()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"security-{stamp}.json"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user": getpass.getuser(),
        "score": security_score(findings),
        "summary": summary(findings),
        "findings": [item.to_record() for item in findings],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
    except OSError as error:
        raise EclipseError(f"Unable to write security report: {error}") from error
    return path


def format_findings(findings: list[Finding]) -> str:
    lines = [f"Security score: {security_score(findings)}/100", f"Summary: {summary(findings)}", ""]
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
            paths.extend(sorted(root.glob("*.plist")))
    return paths


def suspicious_plist(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(SUSPICIOUS_PLIST.search(text))


def shell_startup_files() -> list[Path]:
    home = Path.home()
    return [home / ".zshrc", home / ".zprofile", home / ".bash_profile", home / ".bashrc", home / ".profile"]


def world_writable_paths() -> list[Path]:
    roots = [Path.home(), Path("/Library/LaunchAgents"), Path("/Library/LaunchDaemons")]
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, _ in os.walk(root):
            current = Path(dirpath)
            try:
                depth = len(current.relative_to(root).parts)
                if depth >= 2:
                    dirnames[:] = []
                if current.stat().st_mode & stat.S_IWOTH:
                    found.append(current)
            except OSError:
                continue
            if len(found) >= 50:
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
