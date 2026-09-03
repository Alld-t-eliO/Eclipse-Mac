from __future__ import annotations

import base64
import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from eclipse.modules.audit import default_log_path, record
from eclipse.system.errors import EclipseError
from eclipse.system.memory import default_memory_path
from eclipse.modules.scripts import default_scripts_home


@dataclass(frozen=True)
class SnapshotInfo:
    name: str
    path: Path
    created_at: str
    files: int
    directories: int
    bytes: int
    entries: tuple[str, ...]


def default_recovery_home() -> Path:
    override = os.environ.get("ECLIPSE_RECOVERY_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "recovery"


def default_sources() -> list[Path]:
    return [
        default_memory_path(),
        default_scripts_home(),
        default_log_path(),
    ]


def snapshot(destination: Path | None = None, *, sources: list[Path] | None = None) -> Path:
    root = (destination or default_recovery_home()).expanduser()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = root / f"snapshot-{stamp}"
    try:
        target.mkdir(parents=True, exist_ok=False)
        for source in sources or default_sources():
            path = source.expanduser()
            if not path.exists():
                continue
            item_target = target / path.name
            if path.is_dir():
                shutil.copytree(path, item_target)
            else:
                shutil.copy2(path, item_target)
    except OSError as error:
        raise EclipseError(f"Unable to create snapshot: {error}") from error
    record("recovery-snapshot", success=True, details={"path": str(target)})
    return target.resolve()


def list_snapshots(root: Path | None = None) -> list[SnapshotInfo]:
    folder = (root or default_recovery_home()).expanduser()
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise EclipseError(f"Recovery folder is not a directory: {folder}")
    snapshots: list[SnapshotInfo] = []
    for path in sorted(folder.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.is_dir() and path.name.startswith("snapshot-"):
            snapshots.append(snapshot_info(path))
    return snapshots


def snapshot_info(source: Path) -> SnapshotInfo:
    folder = source.expanduser().resolve()
    if not folder.is_dir():
        raise EclipseError(f"Snapshot not found: {folder}")
    files = 0
    directories = 0
    total_bytes = 0
    entries: list[str] = []
    for path in sorted(folder.rglob("*"), key=lambda item: item.relative_to(folder).as_posix()):
        relative = path.relative_to(folder).as_posix()
        if path.is_dir():
            directories += 1
            entries.append(f"{relative}/")
        elif path.is_file():
            files += 1
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            total_bytes += size
            entries.append(f"{relative} ({size} bytes)")
    try:
        created_at = datetime.fromtimestamp(folder.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        created_at = ""
    return SnapshotInfo(folder.name, folder, created_at, files, directories, total_bytes, tuple(entries))


def format_snapshot_list(snapshots: list[SnapshotInfo]) -> str:
    if not snapshots:
        return "No snapshots."
    lines: list[str] = []
    for item in snapshots:
        lines.append(f"{item.name}  files={item.files} dirs={item.directories} size={item.bytes} bytes  {item.created_at}")
        lines.append(f"  {item.path}")
    return "\n".join(lines)


def format_snapshot_info(info: SnapshotInfo, *, limit: int = 200) -> str:
    lines = [
        f"Snapshot: {info.name}",
        f"Path: {info.path}",
        f"Created at: {info.created_at}",
        f"Files: {info.files}",
        f"Directories: {info.directories}",
        f"Size: {info.bytes} bytes",
        "",
        "Contents:",
    ]
    if not info.entries:
        lines.append("  empty")
    else:
        for entry in info.entries[:limit]:
            lines.append(f"  {entry}")
        hidden = len(info.entries) - limit
        if hidden > 0:
            lines.append(f"  ... {hidden} hidden entries")
    return "\n".join(lines)


def resolve_snapshot(value: str | Path, *, root: Path | None = None) -> Path:
    raw = Path(value).expanduser()
    if raw.is_absolute() or raw.exists():
        return raw.resolve()
    folder = (root or default_recovery_home()).expanduser()
    direct = folder / raw
    if direct.exists():
        return direct.resolve()
    prefixed = folder / f"snapshot-{raw}"
    if prefixed.exists():
        return prefixed.resolve()
    raise EclipseError(f"Snapshot not found: {value}")


def archive_snapshot(source: Path, destination: Path | None = None, *, password: str | None = None) -> Path:
    folder = source.expanduser().resolve()
    if not folder.is_dir():
        raise EclipseError(f"Snapshot not found: {folder}")
    target = (destination or folder.with_suffix(".zip")).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
            for path in folder.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(folder))
        if password:
            raw = target.read_bytes()
            key = hashlib.sha256(password.encode("utf-8")).digest()
            stream = bytearray()
            counter = 0
            while len(stream) < len(raw):
                stream.extend(hashlib.sha256(key + counter.to_bytes(8, "big")).digest())
                counter += 1
            encrypted_bytes = bytes(value ^ stream[index] for index, value in enumerate(raw))
            encoded = base64.b64encode(encrypted_bytes).decode("ascii")
            encrypted = "\n".join(("ECLIPSE-XOR-BASE64-V1", encoded))
            target.with_suffix(target.suffix + ".enc").write_text(encrypted, encoding="utf-8")
            return target.with_suffix(target.suffix + ".enc").resolve()
    except OSError as error:
        raise EclipseError(f"Unable to export recovery archive: {error}") from error
    return target.resolve()


def restore_snapshot(source: Path, destination: Path | None = None, *, confirmed: bool = False) -> Path:
    if not confirmed:
        raise EclipseError("Add --yes to confirm restore.")
    folder = source.expanduser().resolve()
    if not folder.is_dir():
        raise EclipseError(f"Snapshot not found: {folder}")
    target = (destination or Path.home() / "Library" / "Application Support" / "Eclipse" / "restored").expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
        for path in folder.iterdir():
            item_target = target / path.name
            if item_target.exists():
                if item_target.is_dir():
                    shutil.rmtree(item_target)
                else:
                    item_target.unlink()
            if path.is_dir():
                shutil.copytree(path, item_target)
            else:
                shutil.copy2(path, item_target)
    except OSError as error:
        raise EclipseError(f"Unable to restore snapshot: {error}") from error
    record("recovery-restore", success=True, details={"source": str(folder), "destination": str(target)})
    return target.resolve()
