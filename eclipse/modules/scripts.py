from __future__ import annotations

import json
import getpass
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from eclipse.modules.audit import record
from eclipse.system.errors import EclipseError
from eclipse.system.runner import Result, shell_display


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
    parameters: tuple[str, ...] = ()
    dry_run_required: bool = False
    last_run_at: str | None = None
    last_returncode: int | None = None

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
            parameters=tuple(str(item) for item in record.get("parameters", []) if isinstance(item, str)),
            dry_run_required=bool(record.get("dry_run_required", False)),
            last_run_at=str(record["last_run_at"]) if record.get("last_run_at") else None,
            last_returncode=int(record["last_returncode"]) if record.get("last_returncode") is not None else None,
        )

    def to_record(self, root: Path) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path.relative_to(root).as_posix(),
            "added_at": self.added_at,
            "description": self.description,
            "tags": list(self.tags),
            "parameters": list(self.parameters),
            "dry_run_required": self.dry_run_required,
            "last_run_at": self.last_run_at,
            "last_returncode": self.last_returncode,
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


def history_path(root: Path | None = None) -> Path:
    return (root or default_scripts_home()).expanduser().resolve() / "history.jsonl"


def validate_name(name: str) -> str:
    if not NAME_RE.fullmatch(name):
        raise EclipseError("Invalid script name. Use letters, numbers, dot, dash, or underscore.")
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
        raise EclipseError("Invalid script path in registry.")
    base = root.resolve()
    target = (root / relative_path).resolve()
    if target != base and base not in target.parents:
        raise EclipseError("Script path is outside the Eclipse directory.")
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


def metadata_from_comments(path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {"parameters": [], "tags": []}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:40]
    except OSError:
        return metadata
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("#", "//")):
            comment = stripped.lstrip("#/").strip()
        else:
            continue
        if comment.lower().startswith("eclipse:"):
            comment = comment.split(":", 1)[1].strip()
        lowered = comment.lower()
        if lowered.startswith("description:"):
            metadata["description"] = comment.split(":", 1)[1].strip()
        elif lowered.startswith("tags:"):
            metadata["tags"].extend(item.strip() for item in comment.split(":", 1)[1].split(","))
        elif lowered.startswith("param:") or lowered.startswith("parameter:"):
            metadata["parameters"].append(comment.split(":", 1)[1].strip())
        elif lowered == "dry-run-required: true":
            metadata["dry_run_required"] = True
    return metadata


def append_history(script: LocalScript, returncode: int, *, dry_run: bool, root: Path | None = None) -> None:
    path = history_path(root)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": getpass.getuser(),
        "script": script.name,
        "path": str(script.path),
        "source": script.source,
        "dry_run": dry_run,
        "returncode": returncode,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        path.chmod(0o600)
    except OSError:
        pass


def load_history(root: Path | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    path = history_path(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def last_status(name: str, root: Path | None = None) -> tuple[str | None, int | None]:
    for item in reversed(load_history(root, limit=1000)):
        if item.get("script") == name:
            code = item.get("returncode")
            return str(item.get("timestamp")) if item.get("timestamp") else None, int(code) if code is not None else None
    return None, None


def load_registered_scripts(root: Path | None = None) -> dict[str, LocalScript]:
    home = (root or default_scripts_home()).expanduser().resolve()
    path = registry_path(home)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EclipseError(f"Unreadable scripts registry: {error}") from error
    if not isinstance(raw, list):
        raise EclipseError("Invalid scripts registry: expected a list.")
    scripts: dict[str, LocalScript] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        script = LocalScript.from_record(item, home)
        if script.name:
            last_run_at, last_returncode = last_status(script.name, home)
            if last_run_at:
                script = LocalScript(
                    script.name,
                    script.path,
                    script.added_at,
                    script.description,
                    script.tags,
                    script.source,
                    script.parameters,
                    script.dry_run_required,
                    last_run_at,
                    last_returncode,
                )
            scripts[script.name] = script
    return scripts


def load_dropin_scripts(directory: Path | None = None, *, used_names: set[str] | None = None) -> dict[str, LocalScript]:
    folder = (directory or project_scripts_dir()).expanduser().resolve()
    if not folder.exists():
        return {}
    if not folder.is_dir():
        raise EclipseError(f"Invalid scripts directory: {folder}")
    scripts: dict[str, LocalScript] = {}
    used = set(used_names or set())
    for path in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.name.startswith("."):
            continue
        name = safe_dropin_name(path, used)
        used.add(name)
        metadata = metadata_from_comments(path)
        last_run_at, last_returncode = last_status(name)
        try:
            added_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        except OSError:
            added_at = datetime.now(timezone.utc).isoformat()
        scripts[name] = LocalScript(
            name=name,
            path=path,
            added_at=added_at,
            description=str(metadata.get("description") or "Drop-in script"),
            tags=normalize_tags([*metadata.get("tags", []), "drop-in"]),
            source="drop-in",
            parameters=tuple(str(item) for item in metadata.get("parameters", [])),
            dry_run_required=bool(metadata.get("dry_run_required", False)),
            last_run_at=last_run_at,
            last_returncode=last_returncode,
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
        raise EclipseError(f"Unable to write scripts registry: {error}") from error


def add_script(
    name: str,
    source: Path,
    *,
    description: str | None = None,
    tags: Iterable[str] = (),
    root: Path | None = None,
    overwrite: bool = False,
    dry_run_required: bool = False,
) -> LocalScript:
    clean_name = validate_name(name)
    source_path = source.expanduser().resolve()
    if not source_path.is_file():
        raise EclipseError(f"Script not found: {source}")
    home = (root or default_scripts_home()).expanduser().resolve()
    target_dir = files_dir(home)
    target = target_dir / f"{clean_name}{source_path.suffix}"
    scripts = load_registered_scripts(home)
    if clean_name in scripts and not overwrite:
        raise EclipseError(f"Script already registered: {clean_name}")
    try:
        target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(source_path, target)
        target.chmod(0o700)
    except OSError as error:
        raise EclipseError(f"Unable to copy script: {error}") from error
    metadata = metadata_from_comments(source_path)
    script = LocalScript(
        name=clean_name,
        path=target,
        added_at=datetime.now(timezone.utc).isoformat(),
        description=description.strip() if description and description.strip() else metadata.get("description"),
        tags=normalize_tags([*tags, *metadata.get("tags", [])]),
        parameters=tuple(str(item) for item in metadata.get("parameters", [])),
        dry_run_required=dry_run_required or bool(metadata.get("dry_run_required", False)),
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
            raise EclipseError("Drop-in scripts from ./scripts are removed by deleting the file.") from error
        raise EclipseError(f"Unknown script: {clean_name}") from error
    if delete_file:
        try:
            script.path.unlink(missing_ok=True)
        except OSError as error:
            raise EclipseError(f"Unable to delete script file: {error}") from error
    save_scripts(scripts, home)
    return script


def get_script(name: str, *, root: Path | None = None) -> LocalScript:
    clean_name = validate_name(name)
    try:
        return load_scripts(root)[clean_name]
    except KeyError as error:
        raise EclipseError(f"Unknown script: {clean_name}") from error


def command_for(script: LocalScript, arguments: list[str]) -> list[str]:
    if not script.path.exists() or not script.path.is_file():
        raise EclipseError(f"Missing script file: {script.path}")
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
    force: bool = False,
) -> Result:
    script = get_script(name, root=root)
    if script.dry_run_required and not dry_run and not force:
        raise EclipseError(f"Dry-run is required for this script: {script.name}. Add --dry-run or --force.")
    command = command_for(script, arguments or [])
    if dry_run:
        print(shell_display(command))
        append_history(script, 0, dry_run=True, root=root)
        return Result(0, "", "")
    try:
        completed = subprocess.run(command, check=False, text=True)
    except OSError as error:
        record("local-script", success=False, details={"script": script.name, "error": str(error)})
        raise EclipseError(f"Unable to run script: {error}") from error
    append_history(script, completed.returncode, dry_run=False, root=root)
    if script.source == "registry":
        scripts = load_registered_scripts(root)
        if script.name in scripts:
            current = scripts[script.name]
            scripts[script.name] = LocalScript(
                current.name,
                current.path,
                current.added_at,
                current.description,
                current.tags,
                current.source,
                current.parameters,
                current.dry_run_required,
                datetime.now(timezone.utc).isoformat(),
                completed.returncode,
            )
            save_scripts(scripts, root)
    record("local-script", success=completed.returncode == 0, details={"script": script.name, "code": completed.returncode})
    return Result(completed.returncode, "", "")
