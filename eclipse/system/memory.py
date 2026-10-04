from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from eclipse.system.errors import EclipseError
from eclipse.system.storage import atomic_write, serialized


MAX_TEXT_LENGTH = 20_000
MAX_TAG_LENGTH = 64


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    created_at: str
    text: str
    tags: tuple[str, ...]
    source: str | None = None
    project: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> MemoryEntry:
        tags = record.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        return cls(
            id=str(record.get("id", "")),
            created_at=str(record.get("created_at", "")),
            text=str(record.get("text", "")),
            tags=tuple(str(tag) for tag in tags),
            source=str(record["source"]) if record.get("source") else None,
            project=str(record["project"]) if record.get("project") else None,
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "text": self.text,
            "tags": list(self.tags),
            "source": self.source,
            "project": self.project,
        }


def default_memory_path() -> Path:
    override = os.environ.get("ECLIPSE_MEMORY_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Eclipse" / "memory.jsonl"


def normalize_tags(values: Iterable[str]) -> tuple[str, ...]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for item in raw.split(","):
            tag = item.strip().lower()
            if not tag:
                continue
            if len(tag) > MAX_TAG_LENGTH:
                raise EclipseError(f"Tag is too long: {tag[:24]}...")
            if any(character.isspace() for character in tag):
                raise EclipseError(f"Invalid tag with whitespace: {tag}")
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tuple(tags)


@serialized(lambda options: options.get("path") or default_memory_path())
def add_memory(
    text: str,
    *,
    tags: Iterable[str] = (),
    source: str | None = None,
    project: str | None = None,
    path: Path | None = None,
) -> MemoryEntry:
    cleaned = text.strip()
    if not cleaned:
        raise EclipseError("Memory cannot be empty.")
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise EclipseError(f"Memory is too long: maximum {MAX_TEXT_LENGTH} characters.")
    entry = MemoryEntry(
        id=secrets.token_hex(6),
        created_at=datetime.now(timezone.utc).isoformat(),
        text=cleaned,
        tags=normalize_tags(tags),
        source=source.strip() if source and source.strip() else None,
        project=project.strip() if project and project.strip() else None,
    )
    write_entry(entry, path or default_memory_path())
    return entry


def write_entry(entry: MemoryEntry, path: Path) -> None:
    entries = load_memories(path)
    entries.append(entry)
    write_entries(entries, path)


def write_entries(entries: Iterable[MemoryEntry], path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        content = "".join(json.dumps(entry.to_record(), ensure_ascii=False) + "\n" for entry in entries)
        atomic_write(path, content)
        path.chmod(0o600)
    except OSError as error:
        raise EclipseError(f"Unable to write memory: {error}") from error


def load_memories(path: Path | None = None) -> list[MemoryEntry]:
    memory_path = path or default_memory_path()
    if not memory_path.exists():
        return []
    entries: list[MemoryEntry] = []
    try:
        with memory_path.open("r", encoding="utf-8") as stream:
            for index, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise EclipseError(f"Unreadable memory at line {index}: {error}") from error
                if not isinstance(record, dict):
                    raise EclipseError(f"Unreadable memory at line {index}: expected an object.")
                entry = MemoryEntry.from_record(record)
                if entry.id and entry.text:
                    entries.append(entry)
    except OSError as error:
        raise EclipseError(f"Unable to read memory: {error}") from error
    return entries


def filter_memories(
    entries: Iterable[MemoryEntry],
    *,
    query: str | None = None,
    tag: str | None = None,
    project: str | None = None,
) -> list[MemoryEntry]:
    query_text = query.strip().lower() if query else None
    tag_text = tag.strip().lower() if tag else None
    project_text = project.strip().lower() if project else None
    results: list[MemoryEntry] = []
    for entry in entries:
        if query_text and query_text not in entry.text.lower():
            continue
        if tag_text and tag_text not in entry.tags:
            continue
        if project_text and (entry.project or "").lower() != project_text:
            continue
        results.append(entry)
    return results


def export_json(destination: Path, *, path: Path | None = None) -> Path:
    entries = load_memories(path)
    records = [entry.to_record() for entry in entries]
    target = destination.expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    except OSError as error:
        raise EclipseError(f"Unable to export memory: {error}") from error
    return target


@serialized(lambda options: options.get("path") or default_memory_path())
def update_memory(
    memory_id: str,
    *,
    text: str | None = None,
    tags: Iterable[str] | None = None,
    source: str | None = None,
    project: str | None = None,
    path: Path | None = None,
) -> MemoryEntry:
    target_id = memory_id.strip()
    if not target_id:
        raise EclipseError("Memory id is required.")
    entries = load_memories(path)
    updated: MemoryEntry | None = None
    rewritten: list[MemoryEntry] = []
    for entry in entries:
        if entry.id != target_id:
            rewritten.append(entry)
            continue
        next_text = entry.text if text is None else text.strip()
        if not next_text:
            raise EclipseError("Memory cannot be empty.")
        if len(next_text) > MAX_TEXT_LENGTH:
            raise EclipseError(f"Memory is too long: maximum {MAX_TEXT_LENGTH} characters.")
        updated = MemoryEntry(
            id=entry.id,
            created_at=entry.created_at,
            text=next_text,
            tags=entry.tags if tags is None else normalize_tags(tags),
            source=entry.source if source is None else (source.strip() or None),
            project=entry.project if project is None else (project.strip() or None),
        )
        rewritten.append(updated)
    if updated is None:
        raise EclipseError(f"Memory not found: {target_id}")
    write_entries(rewritten, path or default_memory_path())
    return updated


@serialized(lambda options: options.get("path") or default_memory_path())
def delete_memory(memory_id: str, *, path: Path | None = None) -> MemoryEntry:
    target_id = memory_id.strip()
    if not target_id:
        raise EclipseError("Memory id is required.")
    entries = load_memories(path)
    deleted: MemoryEntry | None = None
    kept: list[MemoryEntry] = []
    for entry in entries:
        if entry.id == target_id:
            deleted = entry
        else:
            kept.append(entry)
    if deleted is None:
        raise EclipseError(f"Memory not found: {target_id}")
    write_entries(kept, path or default_memory_path())
    return deleted


def list_tags(entries: Iterable[MemoryEntry]) -> list[tuple[str, int]]:
    counts = summarize(entries)["tags"]
    if not isinstance(counts, dict):
        return []
    return sorted(((str(tag), int(count)) for tag, count in counts.items()), key=lambda item: (-item[1], item[0]))


def list_projects(entries: Iterable[MemoryEntry]) -> list[tuple[str, int]]:
    counts = summarize(entries)["projects"]
    if not isinstance(counts, dict):
        return []
    return sorted(((str(project), int(count)) for project, count in counts.items()), key=lambda item: (-item[1], item[0]))


def memory_guide() -> str:
    return "\n".join(
        [
            "Local Memory is a private local notebook for useful Eclipse context.",
            "",
            "Good entries:",
            "- decisions you do not want to forget",
            "- project notes and setup details",
            "- security observations and follow-up tasks",
            "- commands or paths you reuse often",
            "",
            "Beginner commands:",
            "eclipse memory add \"Use snapshots before risky changes\" --tag backup,safety --project eclipse",
            "eclipse memory list --limit 10",
            "eclipse memory search snapshot --project eclipse",
            "eclipse memory tags",
            "eclipse memory projects",
            "eclipse memory export ~/Desktop/eclipse-memory.json",
            "",
            "Storage:",
            str(default_memory_path()),
        ]
    )


def summarize(entries: Iterable[MemoryEntry]) -> dict[str, object]:
    items = list(entries)
    tag_counts: dict[str, int] = {}
    project_counts: dict[str, int] = {}
    for entry in items:
        for tag in entry.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if entry.project:
            project_counts[entry.project] = project_counts.get(entry.project, 0) + 1
    return {
        "count": len(items),
        "tags": dict(sorted(tag_counts.items())),
        "projects": dict(sorted(project_counts.items())),
    }
