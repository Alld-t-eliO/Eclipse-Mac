from __future__ import annotations

import io
import stat
import tempfile
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from eclipse.system.storage import atomic_write
from eclipse.system.inbox import require_disjoint_paths

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
    paths = [p.expanduser() for p in (default_sources() if sources is None else sources)]
    existing = [p for p in paths if p.exists()]
    if len({p.name for p in existing}) != len(existing):
        raise EclipseError("Snapshot sources must have distinct names.")
    for path in existing:
        require_disjoint_paths(path, root)
        validate_tree(path)
    target = None
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = Path(tempfile.mkdtemp(prefix="snapshot-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-", dir=root))
        for path in existing:
            item_target = target / path.name
            if path.is_dir():
                shutil.copytree(path, item_target, symlinks=True)
            else:
                shutil.copy2(path, item_target)
    except OSError as error:
        if target is not None:
            shutil.rmtree(target, ignore_errors=True)
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


ARCHIVE_HEADER = b"ECLIPSE-AESGCM-SCRYPT-V2\n"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


def validate_tree(source: Path) -> None:
    for path in [source, *(source.rglob("*") if source.is_dir() else [])]:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise EclipseError(f"Snapshot contains a link or special file: {path}")


def archive_key(password: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))


def archive_snapshot(source: Path, destination: Path | None = None, *, password: str | None = None) -> Path:
    folder = source.expanduser().resolve()
    if not folder.is_dir():
        raise EclipseError(f"Snapshot not found: {folder}")
    target = (destination or folder.with_suffix(".zip")).expanduser()
    if password is not None:
        if not password:
            raise EclipseError("Archive password must not be empty.")
        target = target.with_suffix(target.suffix + ".enc")
    require_disjoint_paths(folder, target)
    if target.exists() or target.is_symlink():
        raise EclipseError(f"Archive already exists: {target}")
    validate_tree(folder)
    if sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) > MAX_ARCHIVE_BYTES:
        raise EclipseError("Snapshot exceeds the 256 MiB archive limit; use the backup script for larger data.")
    try:
        buffer = io.BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            for path in folder.rglob("*"):
                archive.write(path, path.relative_to(folder))
        raw = buffer.getvalue()
        if password is not None:
            salt, nonce = os.urandom(16), os.urandom(12)
            raw = ARCHIVE_HEADER + salt + nonce + AESGCM(archive_key(password, salt)).encrypt(nonce, raw, ARCHIVE_HEADER)
        atomic_write(target, raw)
    except OSError as error:
        raise EclipseError(f"Unable to export recovery archive: {error}") from error
    return target.resolve()


def restore_snapshot(source: Path, destination: Path | None = None, *, confirmed: bool = False, password: str | None = None) -> Path:
    if not confirmed:
        raise EclipseError("Add --yes to confirm restore.")
    folder = source.expanduser().resolve()
    if not folder.exists():
        raise EclipseError(f"Snapshot not found: {folder}")
    target = (destination or Path.home() / "Library" / "Application Support" / "Eclipse" / "restored").expanduser()
    require_disjoint_paths(folder, target)
    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
        raise EclipseError("Restore destination must be a new or empty directory.")
    if folder.is_dir():
        validate_tree(folder)
    staging = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = Path(tempfile.mkdtemp(prefix=".eclipse-restore-", dir=target.parent))
        if folder.is_dir():
            shutil.copytree(folder, staging, dirs_exist_ok=True, symlinks=True)
            staging.chmod(0o700)
        else:
            if folder.stat().st_size > MAX_ARCHIVE_BYTES + 1024 * 1024:
                raise EclipseError("Archive exceeds the restore size limit.")
            raw = folder.read_bytes()
            if raw.startswith(ARCHIVE_HEADER):
                if not password:
                    raise EclipseError("A password is required for this archive.")
                payload = raw[len(ARCHIVE_HEADER):]
                salt, nonce = payload[:16], payload[16:28]
                try:
                    raw = AESGCM(archive_key(password, salt)).decrypt(nonce, payload[28:], ARCHIVE_HEADER)
                except (InvalidTag, ValueError) as error:
                    raise EclipseError("Incorrect password or damaged encrypted archive.") from error
            elif raw.startswith(b"ECLIPSE-XOR-"):
                raise EclipseError("Legacy XOR archives are unsupported; export the original snapshot again.")
            with ZipFile(io.BytesIO(raw)) as archive:
                members = archive.infolist()
                if sum(item.file_size for item in members) > MAX_ARCHIVE_BYTES:
                    raise EclipseError("Expanded archive exceeds the restore size limit.")
                for item in members:
                    relative = Path(item.filename)
                    mode = item.external_attr >> 16
                    if relative.is_absolute() or ".." in relative.parts or "\\" in item.filename or stat.S_ISLNK(mode):
                        raise EclipseError("Unsafe archive member.")
                    output = staging / relative
                    if item.is_dir():
                        output.mkdir(parents=True, exist_ok=True, mode=0o700)
                    else:
                        atomic_write(output, archive.read(item))
                        if mode & 0o100:
                            output.chmod(0o700)
        if target.exists():
            target.rmdir()
        os.replace(staging, target)
    except (OSError, BadZipFile) as error:
        raise EclipseError(f"Unable to restore snapshot: {error}") from error
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
    record("recovery-restore", success=True, details={"source": str(folder), "destination": str(target)})
    return target.resolve()
