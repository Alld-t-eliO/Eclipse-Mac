from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .errors import EclipseError


def local_files(folder: Path, limit: int = 20) -> list[str]:
    path = folder.expanduser().resolve()
    if not path.exists():
        return []
    if not path.is_dir():
        raise EclipseError(f"Ce chemin local n'est pas un dossier : {path}")
    entries = sorted(path.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
    result = []
    for item in entries[:limit]:
        stat = item.stat()
        stamp = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        kind = "dossier" if item.is_dir() else f"{stat.st_size} o"
        result.append(f"{stamp}  {kind:>10}  {item.name}")
    return result
