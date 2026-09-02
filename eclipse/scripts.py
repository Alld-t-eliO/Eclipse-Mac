from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .audit import record
from .errors import EclipseError
from .runner import Result, shell_display


NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
INTERPRETERS = {
    ".py": "python3",
    ".sh": "sh",
    ".bash": "bash",
    ".zsh": "zsh",
    ".js": "node",
}


@dataclass(frozen=True)
class LocalScript:
    name: str
    path: Path
    added_at: str
    description: str | None = None
    tags: tuple[str, ...] = ()
    source: str = "registry"

    @classmethod
    def from_record(cls, record: dict[str, Any], root: Path) -> LocalScript:
        tags = record.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        relative_path = str(record.get("path", ""))
        path = resolve_inside(root, relative_path)
        return cls(
            name=str(record.get("name", "")),
            path=path,
            added_at=str(record.get("added_at", "")),
            description=str(record["description"]) if record.get("description") else None,
            tags=tuple(str(tag) for tag in tags),
            source="registry",
        )

    def to_record(self, root: Path) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path.relative_to(root).as_posix(),
            "added_at": self.added_at,
            "description": self.description,
            "tags": list(self.tags),
        }


def default_scripts_home() -> Path:
    override = os.environ.get("ECLIPSE_SCRIPTS_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "scripts"


def project_scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts"


def package_scripts_dir() -> Path:
    return Path(__file__).resolve().parent / "scripts"


def project_scripts_dirs() -> tuple[Path, ...]:
    return (project_scripts_dir(), package_scripts_dir())


def files_dir(root: Path | None = None) -> Path:
    return (root or default_scripts_home()).expanduser().resolve() / "files"


def registry_path(root: Path | None = None) -> Path:
    return (root or default_scripts_home()).expanduser().resolve() / "registry.json"


def validate_name(name: str) -> str:
    if not NAME_RE.fullmatch(name):
        raise EclipseError("Nom de script invalide. Utilise lettres, chiffres, point, tiret ou underscore.")
    return name


def normalize_tags(values: Iterable[str]) -> tuple[str, ...]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for item in raw.split(","):
            tag = item.strip().lower()
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tuple(tags)


def resolve_inside(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise EclipseError("Chemin de script invalide dans le registre.")
    base = root.resolve()
    target = (root / relative_path).resolve()
    if target != base and base not in target.parents:
        raise EclipseError("Chemin de script hors du dossier Eclipse.")
    return target


def safe_dropin_name(path: Path, used: set[str]) -> str:
    base = path.stem if path.suffix else path.name
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", base).strip(".-")
    if not name or not re.match(r"^[A-Za-z0-9]", name):
        name = f"script-{path.name}"
        name = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-")
    name = name[:64]
    candidate = name
    index = 2
    while candidate in used:
        suffix = f"-{index}"
        candidate = f"{name[:64 - len(suffix)]}{suffix}"
        index += 1
    return validate_name(candidate)


def load_registered_scripts(root: Path | None = None) -> dict[str, LocalScript]:
    home = (root or default_scripts_home()).expanduser().resolve()
    path = registry_path(home)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EclipseError(f"Registre scripts illisible : {error}") from error
    if not isinstance(raw, list):
        raise EclipseError("Registre scripts invalide : liste attendue.")
    scripts: dict[str, LocalScript] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        script = LocalScript.from_record(item, home)
        if script.name:
            scripts[script.name] = script
    return scripts


def load_dropin_scripts(directory: Path | None = None, *, used_names: set[str] | None = None) -> dict[str, LocalScript]:
    folder = (directory or project_scripts_dir()).expanduser().resolve()
    if not folder.exists():
        return {}
    if not folder.is_dir():
        raise EclipseError(f"Dossier scripts invalide : {folder}")
    scripts: dict[str, LocalScript] = {}
    used = set(used_names or set())
    for path in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.name.startswith("."):
            continue
        name = safe_dropin_name(path, used)
        used.add(name)
        try:
            added_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        except OSError:
            added_at = datetime.now(timezone.utc).isoformat()
        scripts[name] = LocalScript(
            name=name,
            path=path,
            added_at=added_at,
            description="Drop-in script",
            tags=("drop-in",),
            source="drop-in",
        )
    return scripts


def load_scripts(root: Path | None = None, *, include_dropins: bool = True) -> dict[str, LocalScript]:
    scripts = load_registered_scripts(root)
    if include_dropins:
        used = set(scripts)
        for directory in project_scripts_dirs():
            dropins = load_dropin_scripts(directory, used_names=used)
            scripts.update(dropins)
            used.update(dropins)
    return scripts


def save_scripts(scripts: dict[str, LocalScript], root: Path | None = None) -> None:
    home = (root or default_scripts_home()).expanduser().resolve()
    path = registry_path(home)
    records = [
        script.to_record(home)
        for script in sorted(scripts.values(), key=lambda item: item.name)
        if script.source == "registry"
    ]
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
    except OSError as error:
        raise EclipseError(f"Impossible d'écrire le registre scripts : {error}") from error


def add_script(
    name: str,
    source: Path,
    *,
    description: str | None = None,
    tags: Iterable[str] = (),
    root: Path | None = None,
    overwrite: bool = False,
) -> LocalScript:
    clean_name = validate_name(name)
    source_path = source.expanduser().resolve()
    if not source_path.is_file():
        raise EclipseError(f"Script introuvable : {source}")
    home = (root or default_scripts_home()).expanduser().resolve()
    target_dir = files_dir(home)
    target = target_dir / f"{clean_name}{source_path.suffix}"
    scripts = load_registered_scripts(home)
    if clean_name in scripts and not overwrite:
        raise EclipseError(f"Script déjà enregistré : {clean_name}")
    try:
        target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(source_path, target)
        target.chmod(0o700)
    except OSError as error:
        raise EclipseError(f"Impossible de copier le script : {error}") from error
    script = LocalScript(
        name=clean_name,
        path=target,
        added_at=datetime.now(timezone.utc).isoformat(),
        description=description.strip() if description and description.strip() else None,
        tags=normalize_tags(tags),
    )
    scripts[clean_name] = script
    save_scripts(scripts, home)
    return script


def remove_script(name: str, *, root: Path | None = None, delete_file: bool = False) -> LocalScript:
    clean_name = validate_name(name)
    home = (root or default_scripts_home()).expanduser().resolve()
    scripts = load_registered_scripts(home)
    try:
        script = scripts.pop(clean_name)
    except KeyError as error:
        if clean_name in load_dropin_scripts(used_names=set(scripts)):
            raise EclipseError("Les scripts du dossier ./scripts se retirent en supprimant le fichier.") from error
        raise EclipseError(f"Script inconnu : {clean_name}") from error
    if delete_file:
        try:
            script.path.unlink(missing_ok=True)
        except OSError as error:
            raise EclipseError(f"Impossible de supprimer le fichier script : {error}") from error
    save_scripts(scripts, home)
    return script


def get_script(name: str, *, root: Path | None = None) -> LocalScript:
    clean_name = validate_name(name)
    try:
        return load_scripts(root)[clean_name]
    except KeyError as error:
        raise EclipseError(f"Script inconnu : {clean_name}") from error


def command_for(script: LocalScript, arguments: list[str]) -> list[str]:
    if not script.path.exists() or not script.path.is_file():
        raise EclipseError(f"Fichier script absent : {script.path}")
    interpreter = INTERPRETERS.get(script.path.suffix.lower())
    if interpreter:
        return [interpreter, str(script.path), *arguments]
    return [str(script.path), *arguments]


def run_script(
    name: str,
    *,
    arguments: list[str] | None = None,
    root: Path | None = None,
    dry_run: bool = False,
) -> Result:
    script = get_script(name, root=root)
    command = command_for(script, arguments or [])
    if dry_run:
        print(shell_display(command))
        return Result(0, "", "")
    try:
        completed = subprocess.run(command, check=False, text=True)
    except OSError as error:
        record("local-script", success=False, details={"script": script.name, "error": str(error)})
        raise EclipseError(f"Impossible de lancer le script : {error}") from error
    record("local-script", success=completed.returncode == 0, details={"script": script.name, "code": completed.returncode})
    return Result(completed.returncode, "", "")
