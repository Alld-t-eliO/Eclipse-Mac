from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .errors import EclipseError


@dataclass(frozen=True)
class FileEntry:
    path: Path
    name: str
    kind: str
    size: int
    modified_at: str
    hidden: bool = False


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve()


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


def write_text(path: Path, text: str, *, append: bool = False, overwrite: bool = False) -> Path:
    target = path.expanduser()
    if target.exists() and not append and not overwrite:
        raise EclipseError(f"Le fichier existe déjà : {target}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with target.open(mode, encoding="utf-8") as handle:
            handle.write(text)
            if text and not text.endswith("\n"):
                handle.write("\n")
    except OSError as error:
        raise EclipseError(f"Impossible d'écrire le fichier : {error}") from error
    return target.expanduser().resolve()


def make_directory(path: Path) -> Path:
    target = path.expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise EclipseError(f"Impossible de créer le dossier : {error}") from error
    return target.resolve()


def copy_path(source: Path, destination: Path, *, overwrite: bool = False) -> Path:
    src = resolve_path(source)
    dst = destination.expanduser()
    if not src.exists():
        raise EclipseError(f"Chemin introuvable : {src}")
    if dst.exists() and not overwrite:
        raise EclipseError(f"Destination déjà existante : {dst}")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists() and overwrite:
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    except OSError as error:
        raise EclipseError(f"Impossible de copier : {error}") from error
    return dst.resolve()


def move_path(source: Path, destination: Path, *, overwrite: bool = False) -> Path:
    src = resolve_path(source)
    dst = destination.expanduser()
    if not src.exists():
        raise EclipseError(f"Chemin introuvable : {src}")
    if dst.exists() and not overwrite:
        raise EclipseError(f"Destination déjà existante : {dst}")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and overwrite:
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        shutil.move(str(src), str(dst))
    except OSError as error:
        raise EclipseError(f"Impossible de déplacer : {error}") from error
    return dst.resolve()


def rename_path(source: Path, name: str, *, overwrite: bool = False) -> Path:
    if not name or "/" in name:
        raise EclipseError("Nom invalide pour le renommage.")
    src = resolve_path(source)
    return move_path(src, src.with_name(name), overwrite=overwrite)


def trash_path(path: Path, *, trash_dir: Path | None = None) -> Path:
    target = resolve_path(path)
    if not target.exists():
        raise EclipseError(f"Chemin introuvable : {target}")
    trash = (trash_dir or Path.home() / ".Trash").expanduser()
    destination = trash / target.name
    index = 2
    while destination.exists():
        destination = trash / f"{target.stem}-{index}{target.suffix}"
        index += 1
    try:
        trash.mkdir(exist_ok=True)
        shutil.move(str(target), str(destination))
    except OSError as error:
        raise EclipseError(f"Impossible de déplacer vers la Corbeille : {error}") from error
    return destination.resolve()


def open_path(path: Path) -> Path:
    target = resolve_path(path)
    if not target.exists():
        raise EclipseError(f"Chemin introuvable : {target}")
    try:
        subprocess.run(["open", str(target)], check=False)
    except OSError as error:
        raise EclipseError(f"Impossible d'ouvrir avec macOS : {error}") from error
    return target
