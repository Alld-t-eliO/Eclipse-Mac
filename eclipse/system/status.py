from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskUsage:
    total: int
    used: int
    free: int
    percent: float


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
