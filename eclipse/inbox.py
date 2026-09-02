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

from .audit import record
from .errors import EclipseError


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
        raise EclipseError("Chemin protégé. Confirme explicitement l'action avant modification.")


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
        raise EclipseError(f"Impossible de créer la sauvegarde : {error}") from error
    return destination.resolve()


def inspect_path(path: Path) -> FileEntry:
    target = resolve_path(path)
    if not target.exists():
        raise EclipseError(f"Chemin introuvable : {target}")
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
        raise EclipseError(f"Ce chemin local n'est pas un dossier : {path}")
    if limit < 1:
        raise EclipseError("La limite doit être positive.")
    entries: list[FileEntry] = []
    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError as error:
        raise EclipseError(f"Impossible de lister le dossier : {error}") from error
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
    kind = "dossier" if entry.kind == "directory" else f"{entry.size} o"
    return f"{entry.modified_at}  {kind:>10}  {entry.name}"


def local_files(folder: Path, limit: int = 20) -> list[str]:
    return [format_entry(entry) for entry in list_entries(folder, limit=limit)]


def read_text(path: Path, *, max_bytes: int = 20000) -> str:
    target = resolve_path(path)
    if not target.is_file():
        raise EclipseError(f"Ce chemin local n'est pas un fichier : {target}")
    if max_bytes < 1:
        raise EclipseError("La taille de lecture doit être positive.")
    try:
        data = target.read_bytes()[:max_bytes]
    except OSError as error:
        raise EclipseError(f"Impossible de lire le fichier : {error}") from error
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EclipseError("Fichier non lisible en UTF-8 depuis Eclipse.") from error


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
        raise EclipseError(f"Le fichier existe déjà : {target}")
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
        raise EclipseError(f"Impossible d'écrire le fichier : {error}") from error
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
        raise EclipseError(f"Impossible de créer le dossier : {error}") from error
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
        raise EclipseError(f"Chemin introuvable : {src}")
    if dst.exists() and not overwrite:
        raise EclipseError(f"Destination déjà existante : {dst}")
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
        raise EclipseError(f"Impossible de copier : {error}") from error
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
        raise EclipseError(f"Chemin introuvable : {src}")
    if dst.exists() and not overwrite:
        raise EclipseError(f"Destination déjà existante : {dst}")
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
        raise EclipseError(f"Impossible de déplacer : {error}") from error
    result = dst.resolve()
    record(
        "file-move",
        success=True,
        details={"source": str(src), "destination": str(result), "backups": [str(item) for item in backups if item]},
    )
    return result


def rename_path(source: Path, name: str, *, overwrite: bool = False, confirmed: bool = False, create_backup: bool = True) -> Path:
    if not name or "/" in name:
        raise EclipseError("Nom invalide pour le renommage.")
    src = resolve_path(source)
    return move_path(src, src.with_name(name), overwrite=overwrite, confirmed=confirmed, create_backup=create_backup)


def trash_path(path: Path, *, trash_dir: Path | None = None, confirmed: bool = False, create_backup: bool = True) -> Path:
    target = resolve_path(path)
    require_write_confirmation((target,), confirmed=confirmed)
    if not target.exists():
        raise EclipseError(f"Chemin introuvable : {target}")
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
        raise EclipseError(f"Impossible de déplacer vers la Corbeille : {error}") from error
    result = destination.resolve()
    record("file-trash", success=True, details={"path": str(target), "trash": str(result), "backup": str(backup) if backup else None})
    return result


def open_path(path: Path) -> Path:
    target = resolve_path(path)
    if not target.exists():
        raise EclipseError(f"Chemin introuvable : {target}")
    try:
        subprocess.run(["open", str(target)], check=False)
    except OSError as error:
        raise EclipseError(f"Impossible d'ouvrir avec macOS : {error}") from error
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
        raise EclipseError("Le numéro de ligne doit être positif.")
    target = resolve_path(path)
    require_write_confirmation((target,), confirmed=confirmed)
    lines = read_text(target).splitlines()
    if line_number > len(lines):
        raise EclipseError(f"Ligne absente : {line_number}")
    lines[line_number - 1] = text
    backup = backup_path(target) if create_backup else None
    try:
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as error:
        record("file-edit", success=False, details={"path": str(target), "line": line_number, "error": str(error)})
        raise EclipseError(f"Impossible d'éditer le fichier : {error}") from error
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
            raise EclipseError(f"Archive ZIP invalide : {error}") from error
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
    max_depth: int = 4,
    limit: int = 50,
    include_hidden: bool = False,
) -> list[FileEntry]:
    base = resolve_path(root)
    if not base.is_dir():
        raise EclipseError(f"Ce chemin local n'est pas un dossier : {base}")
    results: list[FileEntry] = []
    query_text = (query or "").lower()
    for path in base.rglob("*"):
        try:
            relative = path.relative_to(base)
        except ValueError:
            continue
        if len(relative.parts) > max_depth:
            continue
        if not include_hidden and any(part.startswith(".") for part in relative.parts):
            continue
        if name and not fnmatch(path.name, name):
            continue
        if query_text and query_text not in path.name.lower():
            continue
        try:
            results.append(inspect_path(path))
        except OSError:
            continue
        if len(results) >= limit:
            break
    return results


def make_executable(path: Path, *, confirmed: bool = False) -> Path:
    target = resolve_path(path)
    require_write_confirmation((target,), confirmed=confirmed)
    try:
        target.chmod(target.stat().st_mode | 0o100)
    except OSError as error:
        record("file-chmod", success=False, details={"path": str(target), "error": str(error)})
        raise EclipseError(f"Impossible de rendre exécutable : {error}") from error
    record("file-chmod", success=True, details={"path": str(target), "mode": oct(target.stat().st_mode & 0o777)})
    return target
