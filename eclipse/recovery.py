from __future__ import annotations

import base64
import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .audit import default_log_path, record
from .errors import EclipseError
from .memory import default_memory_path
from .scripts import default_scripts_home


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
        raise EclipseError(f"Snapshot impossible : {error}") from error
    record("recovery-snapshot", success=True, details={"path": str(target)})
    return target.resolve()


def archive_snapshot(source: Path, destination: Path | None = None, *, password: str | None = None) -> Path:
    folder = source.expanduser().resolve()
    if not folder.is_dir():
        raise EclipseError(f"Snapshot introuvable : {folder}")
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
        raise EclipseError(f"Export recovery impossible : {error}") from error
    return target.resolve()


def restore_snapshot(source: Path, destination: Path | None = None, *, confirmed: bool = False) -> Path:
    if not confirmed:
        raise EclipseError("Ajoute --yes pour confirmer la restauration.")
    folder = source.expanduser().resolve()
    if not folder.is_dir():
        raise EclipseError(f"Snapshot introuvable : {folder}")
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
        raise EclipseError(f"Restauration impossible : {error}") from error
    record("recovery-restore", success=True, details={"source": str(folder), "destination": str(target)})
    return target.resolve()
