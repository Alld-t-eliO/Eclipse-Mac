from __future__ import annotations
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatch
import os
from pathlib import Path
from typing import Iterable
from zipfile import BadZipFile, ZipFile
from eclipse.audit import record
from eclipse.errors import EclipseError


@dataclass(frozen=True)
class FileEntry:
    path: Path
    name: str
    kind: str
    size: int
    modified_at: str
    hidden: bool = False


@dataclass(frozen=True)
class FilePreview:
    path: Path
    kind: str
    details: tuple[str, ...]
    content: str | None = None


PROTECTED_PATHS = (
    Path("/Applications"),
    Path("/Library"),
    Path("/System"),
    Path("/bin"),
    Path("/etc"),
    Path("/opt"),
    Path("/sbin"),
    Path("/usr"),
    Path.home() / ".config",
    Path.home() / ".gnupg",
    Path.home() / ".ssh",
    Path.home() / "Library",
)


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve()


def is_protected_path(path: Path) -> bool:
    target = resolve_path(path)
    for protected in PROTECTED_PATHS:
        area = protected.expanduser().resolve()
        if target == area or area in target.parents:
            return True
    return False


def require_write_confirmation(paths: Iterable[Path], *, confirmed: bool = False) -> None:
    protected = [str(resolve_path(path)) for path in paths if is_protected_path(path)]
    if protected and not confirmed:
        raise EclipseError("Protected path. Explicitly confirm the action before modifying it.")


def default_backup_dir() -> Path:
    override = os.environ.get("ECLIPSE_BACKUP_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "backups"


def backup_path(path: Path, *, backup_dir: Path | None = None) -> Path | None:
    source = resolve_path(path)
    if not source.exists():
        return None
    root = (backup_dir or default_backup_dir()).expanduser()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = root / stamp / source.name
    try:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
    except OSError as error:
        raise EclipseError(f"Unable to create backup: {error}") from error
    return destination.resolve()


def inspect_path(path: Path) -> FileEntry:
    target = resolve_path(path)
    if not target.exists():
        raise EclipseError(f"Path not found: {target}")
    stat = target.stat()
    kind = "directory" if target.is_dir() else "file"
    return FileEntry(
        path=target,
        name=target.name or str(target),
        kind=kind,
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        hidden=target.name.startswith("."),
    )


def favorites() -> dict[str, Path]:
    home = Path.home()
    return {
        "home": home,
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "pictures": home / "Pictures",
        "movies": home / "Movies",
        "music": home / "Music",
        "applications": Path("/Applications"),
        "eclipse": Path(__file__).resolve().parent.parent,
        "dropin-scripts": Path(__file__).resolve().parent.parent / "scripts",
    }


def list_entries(folder: Path, *, limit: int = 50, include_hidden: bool = False) -> list[FileEntry]:
    path = resolve_path(folder)
    if not path.exists():
        return []
    if not path.is_dir():
        raise EclipseError(f"This local path is not a directory: {path}")
    if limit < 1:
        raise EclipseError("Limit must be positive.")
    entries: list[FileEntry] = []
    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError as error:
        raise EclipseError(f"Unable to list directory: {error}") from error
    for item in children:
        if item.name.startswith(".") and not include_hidden:
            continue
        try:
            entries.append(inspect_path(item))
        except OSError:
            continue
        if len(entries) >= limit:
            break
    return entries


def format_entry(entry: FileEntry) -> str:
    kind = "directory" if entry.kind == "directory" else f"{entry.size} B"
    return f"{entry.modified_at}  {kind:>10}  {entry.name}"


def local_files(folder: Path, limit: int = 20) -> list[str]:
    return [format_entry(entry) for entry in list_entries(folder, limit=limit)]


def read_text(path: Path, *, max_bytes: int = 20000) -> str:
    target = resolve_path(path)
    if not target.is_file():
        raise EclipseError(f"This local path is not a file: {target}")
    if max_bytes < 1:
        raise EclipseError("Read size must be positive.")
    try:
        data = target.read_bytes()[:max_bytes]
    except OSError as error:
        raise EclipseError(f"Unable to read file: {error}") from error
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EclipseError("File is not readable as UTF-8 from Eclipse.") from error


def write_text(
    path: Path,
    text: str,
    *,
    append: bool = False,
    overwrite: bool = False,
    confirmed: bool = False,
    create_backup: bool = True,
) -> Path:
    target = path.expanduser()
    require_write_confirmation((target,), confirmed=confirmed)
    if target.exists() and not append and not overwrite:
        raise EclipseError(f"File already exists: {target}")
    backup = backup_path(target) if create_backup and target.exists() else None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with target.open(mode, encoding="utf-8") as handle:
            handle.write(text)
            if text and not text.endswith("\n"):
                handle.write("\n")
    except OSError as error:
        record("file-write", success=False, details={"path": str(target), "error": str(error)})
        raise EclipseError(f"Unable to write file: {error}") from error
    result = target.expanduser().resolve()
    record("file-write", success=True, details={"path": str(result), "backup": str(backup) if backup else None})
    return result


def make_directory(path: Path, *, confirmed: bool = False) -> Path:
    target = path.expanduser()
    require_write_confirmation((target,), confirmed=confirmed)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        record("file-mkdir", success=False, details={"path": str(target), "error": str(error)})
        raise EclipseError(f"Unable to create directory: {error}") from error
    result = target.resolve()
    record("file-mkdir", success=True, details={"path": str(result)})
    return result


def copy_path(
    source: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    confirmed: bool = False,
    create_backup: bool = True,
) -> Path:
    src = resolve_path(source)
    dst = destination.expanduser()
    require_write_confirmation((dst,), confirmed=confirmed)
    if not src.exists():
        raise EclipseError(f"Path not found: {src}")
    if dst.exists() and not overwrite:
        raise EclipseError(f"Destination already exists: {dst}")
    backup = backup_path(dst) if create_backup and dst.exists() else None
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists() and overwrite:
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    except OSError as error:
        record("file-copy", success=False, details={"source": str(src), "destination": str(dst), "error": str(error)})
        raise EclipseError(f"Unable to copy: {error}") from error
    result = dst.resolve()
    record("file-copy", success=True, details={"source": str(src), "destination": str(result), "backup": str(backup) if backup else None})
    return result


def move_path(
    source: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    confirmed: bool = False,
    create_backup: bool = True,
) -> Path:
    src = resolve_path(source)
    dst = destination.expanduser()
    require_write_confirmation((src, dst), confirmed=confirmed)
    if not src.exists():
        raise EclipseError(f"Path not found: {src}")
    if dst.exists() and not overwrite:
        raise EclipseError(f"Destination already exists: {dst}")
    backups = [backup_path(src)] if create_backup else []
    if create_backup and dst.exists():
        backups.append(backup_path(dst))
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and overwrite:
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        shutil.move(str(src), str(dst))
    except OSError as error:
        record("file-move", success=False, details={"source": str(src), "destination": str(dst), "error": str(error)})
        raise EclipseError(f"Unable to move: {error}") from error
    result = dst.resolve()
    record(
        "file-move",
        success=True,
        details={"source": str(src), "destination": str(result), "backups": [str(item) for item in backups if item]},
    )
    return result


def rename_path(source: Path, name: str, *, overwrite: bool = False, confirmed: bool = False, create_backup: bool = True) -> Path:
    if not name or "/" in name:
        raise EclipseError("Invalid rename target.")
    src = resolve_path(source)
    return move_path(src, src.with_name(name), overwrite=overwrite, confirmed=confirmed, create_backup=create_backup)


def trash_path(path: Path, *, trash_dir: Path | None = None, confirmed: bool = False, create_backup: bool = True) -> Path:
    target = resolve_path(path)
    require_write_confirmation((target,), confirmed=confirmed)
    if not target.exists():
        raise EclipseError(f"Path not found: {target}")
    trash = (trash_dir or Path.home() / ".Trash").expanduser()
    destination = trash / target.name
    index = 2
    while destination.exists():
        destination = trash / f"{target.stem}-{index}{target.suffix}"
        index += 1
    backup = backup_path(target) if create_backup else None
    try:
        trash.mkdir(exist_ok=True)
        shutil.move(str(target), str(destination))
    except OSError as error:
        record("file-trash", success=False, details={"path": str(target), "error": str(error)})
        raise EclipseError(f"Unable to move to Trash: {error}") from error
    result = destination.resolve()
    record("file-trash", success=True, details={"path": str(target), "trash": str(result), "backup": str(backup) if backup else None})
    return result


def open_path(path: Path) -> Path:
    target = resolve_path(path)
    if not target.exists():
        raise EclipseError(f"Path not found: {target}")
    try:
        subprocess.run(["open", str(target)], check=False)
    except OSError as error:
        raise EclipseError(f"Unable to open with macOS: {error}") from error
    return target


def edit_line(
    path: Path,
    line_number: int,
    text: str,
    *,
    confirmed: bool = False,
    create_backup: bool = True,
) -> Path:
    if line_number < 1:
        raise EclipseError("Line number must be positive.")
    target = resolve_path(path)
    require_write_confirmation((target,), confirmed=confirmed)
    lines = read_text(target).splitlines()
    if line_number > len(lines):
        raise EclipseError(f"Missing line: {line_number}")
    lines[line_number - 1] = text
    backup = backup_path(target) if create_backup else None
    try:
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as error:
        record("file-edit", success=False, details={"path": str(target), "line": line_number, "error": str(error)})
        raise EclipseError(f"Unable to edit file: {error}") from error
    record("file-edit", success=True, details={"path": str(target), "line": line_number, "backup": str(backup) if backup else None})
    return target


def file_info(path: Path) -> list[str]:
    target = resolve_path(path)
    entry = inspect_path(target)
    stat = target.stat()
    executable = bool(stat.st_mode & 0o111)
    quarantined = False
    try:
        result = subprocess.run(["xattr", "-p", "com.apple.quarantine", str(target)], capture_output=True, text=True, check=False)
        quarantined = result.returncode == 0
    except OSError:
        quarantined = False
    return [
        f"Path: {entry.path}",
        f"Type: {entry.kind}",
        f"Size: {entry.size} bytes",
        f"Modified: {entry.modified_at}",
        f"Permissions: {oct(stat.st_mode & 0o777)}",
        f"Owner UID: {stat.st_uid}",
        f"Group GID: {stat.st_gid}",
        f"Hidden: {entry.hidden}",
        f"Executable: {executable}",
        f"macOS quarantine: {quarantined}",
        f"Protected path: {is_protected_path(target)}",
    ]


def image_dimensions(path: Path) -> str | None:
    data = path.read_bytes()[:32]
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return f"{width}x{height}"
    if data.startswith(b"\xff\xd8"):
        return "JPEG image"
    return None


def preview_path(path: Path, *, max_bytes: int = 20000) -> FilePreview:
    target = resolve_path(path)
    info = tuple(file_info(target))
    if target.is_dir():
        children = list_entries(target, limit=20)
        content = "\n".join(format_entry(entry) for entry in children) or "Empty directory."
        return FilePreview(target, "directory", info, content)
    suffix = target.suffix.lower()
    if suffix == ".zip":
        try:
            with ZipFile(target) as archive:
                names = archive.namelist()[:50]
        except BadZipFile as error:
            raise EclipseError(f"Invalid ZIP archive: {error}") from error
        return FilePreview(target, "zip", info, "\n".join(names) or "Empty archive.")
    if suffix in {".png", ".jpg", ".jpeg"}:
        dimensions = image_dimensions(target)
        details = info + ((f"Dimensions: {dimensions}",) if dimensions else ())
        return FilePreview(target, "image", details, None)
    content = read_text(target, max_bytes=max_bytes)
    if suffix == ".json":
        import json

        try:
            content = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    return FilePreview(target, "text", info, content)


def search_entries(
    root: Path,
    query: str | None = None,
    *,
    name: str | None = None,
    content: str | None = None,
    extension: str | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    modified_after: str | None = None,
    modified_before: str | None = None,
    ignore: Iterable[str] = (),
    max_depth: int = 4,
    limit: int = 50,
    include_hidden: bool = False,
) -> list[FileEntry]:
    base = resolve_path(root)
    if not base.is_dir():
        raise EclipseError(f"This local path is not a directory: {base}")
    results: list[FileEntry] = []
    query_text = (query or "").lower()
    content_text = (content or "").lower()
    after = datetime.fromisoformat(modified_after).timestamp() if modified_after else None
    before = datetime.fromisoformat(modified_before).timestamp() if modified_before else None
    extension_filter = extension.lower().lstrip(".") if extension else None
    for path in base.rglob("*"):
        try:
            relative = path.relative_to(base)
        except ValueError:
            continue
        if len(relative.parts) > max_depth:
            continue
        if any(fnmatch(part, pattern) or fnmatch(str(relative), pattern) for pattern in ignore for part in relative.parts):
            continue
        if not include_hidden and any(part.startswith(".") for part in relative.parts):
            continue
        if name and not fnmatch(path.name, name):
            continue
        if extension_filter and path.suffix.lower().lstrip(".") != extension_filter:
            continue
        if query_text and query_text not in path.name.lower():
            continue
        try:
            stat = path.stat()
            if min_size is not None and stat.st_size < min_size:
                continue
            if max_size is not None and stat.st_size > max_size:
                continue
            if after is not None and stat.st_mtime < after:
                continue
            if before is not None and stat.st_mtime > before:
                continue
            if content_text:
                if not path.is_file():
                    continue
                try:
                    sample = path.read_bytes()[:1_000_000].decode("utf-8", errors="ignore").lower()
                except OSError:
                    continue
                if content_text not in sample:
                    continue
            results.append(inspect_path(path))
        except OSError:
            continue
        if len(results) >= limit:
            break
    return results


def export_entries(entries: list[FileEntry], destination: Path) -> Path:
    target = destination.expanduser()
    payload = [
        {
            "path": str(entry.path),
            "name": entry.name,
            "kind": entry.kind,
            "size": entry.size,
            "modified_at": entry.modified_at,
            "hidden": entry.hidden,
        }
        for entry in entries
    ]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise EclipseError(f"Unable to export search results: {error}") from error
    return target.resolve()


def make_executable(path: Path, *, confirmed: bool = False) -> Path:
    target = resolve_path(path)
    require_write_confirmation((target,), confirmed=confirmed)
    try:
        target.chmod(target.stat().st_mode | 0o100)
    except OSError as error:
        record("file-chmod", success=False, details={"path": str(target), "error": str(error)})
        raise EclipseError(f"Unable to make executable: {error}") from error
    record("file-chmod", success=True, details={"path": str(target), "mode": oct(target.stat().st_mode & 0o777)})
    return target
