from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class DiskUsage:
    total: int
    used: int
    free: int
    percent: float


@dataclass(frozen=True)
class GPUStatus:
    names: tuple[str, ...]
    usage_percent: float | None
    detail: str


@dataclass(frozen=True)
class NetworkStatus:
    interface: str
    ip_address: str
    router: str
    wifi: str
    dns: tuple[str, ...]
    firewall: str
    stealth: str


@dataclass(frozen=True)
class LocalStatus:
    hostname: str
    system: str
    release: str
    machine: str
    processor: str
    memory_total: int
    memory_used: int
    memory_percent: float
    disk: DiskUsage
    gpu: GPUStatus
    admin_users: tuple[str, ...]
    network: NetworkStatus
    shell: str
    home: Path


def run_text(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, check=False, text=True, capture_output=True)
    except OSError:
        return ""
    if completed.returncode:
        return ""
    return completed.stdout.strip()


def run_text_timeout(command: list[str], *, timeout: int = 5) -> str:
    try:
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode:
        return ""
    return completed.stdout.strip()


def sysctl_int(name: str) -> int:
    value = run_text(["sysctl", "-n", name])
    try:
        return int(value)
    except ValueError:
        return 0


def vm_pages() -> tuple[int, int]:
    page_size = sysctl_int("hw.pagesize") or 4096
    output = run_text(["vm_stat"])
    values: dict[str, int] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        digits = "".join(character for character in raw_value if character.isdigit())
        if digits:
            values[key.strip()] = int(digits)
    free_pages = values.get("Pages free", 0) + values.get("Pages speculative", 0)
    inactive_pages = values.get("Pages inactive", 0)
    purgeable_pages = values.get("Pages purgeable", 0)
    app_memory = values.get("Pages active", 0) + values.get("Pages wired down", 0) + values.get("Pages occupied by compressor", 0)
    used = max(0, app_memory - purgeable_pages)
    available = free_pages + inactive_pages + purgeable_pages
    return used * page_size, available * page_size


def memory_usage() -> tuple[int, int, float]:
    total = sysctl_int("hw.memsize")
    used, available = vm_pages()
    if total <= 0:
        total = used + available
    if total <= 0:
        return 0, 0, 0.0
    used = min(total, used)
    return total, used, used / total * 100


def disk_usage(path: Path = Path("/")) -> DiskUsage:
    usage = shutil.disk_usage(path)
    percent = usage.used / usage.total * 100 if usage.total else 0.0
    return DiskUsage(total=usage.total, used=usage.used, free=usage.free, percent=percent)


@lru_cache(maxsize=1)
def gpu_status() -> GPUStatus:
    profiler = run_text_timeout(["system_profiler", "SPDisplaysDataType"], timeout=8)
    names: list[str] = []
    for line in profiler.splitlines():
        stripped = line.strip()
        if stripped.startswith("Chipset Model:") or stripped.startswith("Graphics:"):
            value = stripped.split(":", 1)[1].strip()
            if value and value not in names:
                names.append(value)

    metrics = run_text_timeout(["powermetrics", "--samplers", "gpu_power", "-n", "1", "-i", "500"], timeout=4)
    usage = None
    for line in metrics.splitlines():
        lowered = line.lower()
        if "gpu active residency" not in lowered:
            continue
        digits = "".join(character for character in line if character.isdigit() or character == ".")
        try:
            usage = float(digits)
            break
        except ValueError:
            continue
    detail = "available" if usage is not None else "usage unavailable without privileged powermetrics"
    return GPUStatus(tuple(names), usage, detail)


@lru_cache(maxsize=1)
def admin_users() -> tuple[str, ...]:
    output = run_text(["dscl", ".", "-read", "/Groups/admin", "GroupMembership"])
    if ":" not in output:
        groups = run_text(["id", "-Gn"]).split()
        return (os.environ.get("USER") or "",) if "admin" in groups and os.environ.get("USER") else ()
    _, users = output.split(":", 1)
    return tuple(user for user in users.split() if user)


def default_interface() -> str:
    output = run_text(["route", "-n", "get", "default"])
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("interface:"):
            return stripped.split(":", 1)[1].strip()
    return active_interface_from_ifconfig()


def active_interface_from_ifconfig() -> str:
    output = run_text(["ifconfig"])
    current = ""
    has_active_status = False
    has_private_ip = False
    for line in output.splitlines():
        if line and not line.startswith(("\t", " ")):
            if current and has_active_status and has_private_ip:
                return current
            current = line.split(":", 1)[0]
            has_active_status = False
            has_private_ip = False
            continue
        stripped = line.strip()
        if stripped == "status: active":
            has_active_status = True
        if stripped.startswith("inet ") and not stripped.startswith("inet 127."):
            has_private_ip = True
    if current and has_active_status and has_private_ip:
        return current
    return ""


def ip_address_for_interface(interface: str) -> str:
    if not interface:
        return ""
    ip_address = run_text(["ipconfig", "getifaddr", interface])
    if ip_address:
        return ip_address
    output = run_text(["ifconfig", interface])
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("inet ") and not stripped.startswith("inet 127."):
            return stripped.split()[1]
    return ""


def default_router() -> str:
    output = run_text(["route", "-n", "get", "default"])
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("gateway:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def wifi_name(interface: str) -> str:
    if not interface:
        return ""
    output = run_text(["networksetup", "-getairportnetwork", interface])
    if "AuthorizationCreate" in output or output.strip().startswith("-"):
        return ""
    if ":" in output and "not associated" not in output.lower():
        return output.split(":", 1)[1].strip()
    return ""


def dns_servers() -> tuple[str, ...]:
    output = run_text(["scutil", "--dns"])
    servers: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith("nameserver"):
            continue
        _, value = stripped.split(":", 1)
        server = value.strip()
        if server and server not in servers:
            servers.append(server)
    return tuple(servers[:4])


def firewall_value(flag: str) -> str:
    tool = Path("/usr/libexec/ApplicationFirewall/socketfilterfw")
    if not tool.exists():
        return "unavailable"
    output = run_text([str(tool), flag])
    lowered = output.lower()
    if "enabled" in lowered or " is on" in lowered:
        return "enabled"
    if "disabled" in lowered or " is off" in lowered:
        return "disabled"
    return output or "unknown"


def network_status() -> NetworkStatus:
    interface = default_interface()
    ip_address = ip_address_for_interface(interface)
    return NetworkStatus(
        interface=interface or "unknown",
        ip_address=ip_address or "offline",
        router=default_router() or "unknown",
        wifi=wifi_name(interface) or "unknown",
        dns=dns_servers(),
        firewall=firewall_value("--getglobalstate"),
        stealth=firewall_value("--getstealthmode"),
    )


def local_status() -> LocalStatus:
    total, used, percent = memory_usage()
    return LocalStatus(
        hostname=socket.gethostname(),
        system=platform.system() or "macOS",
        release=platform.mac_ver()[0] or platform.release(),
        machine=platform.machine(),
        processor=platform.processor() or run_text(["sysctl", "-n", "machdep.cpu.brand_string"]),
        memory_total=total,
        memory_used=used,
        memory_percent=percent,
        disk=disk_usage(),
        gpu=gpu_status(),
        admin_users=admin_users(),
        network=network_status(),
        shell=os.environ.get("SHELL", ""),
        home=Path.home(),
    )


def common_folders() -> list[Path]:
    home = Path.home()
    return [
        home / "Desktop",
        home / "Downloads",
        home / "Documents",
        home / "Pictures",
        home / "Movies",
        home / "Music",
    ]
