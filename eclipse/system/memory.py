from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from eclipse.system.errors import EclipseError


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
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry.to_record(), ensure_ascii=False) + "\n")
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
        target.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise EclipseError(f"Unable to export memory: {error}") from error
    return target


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
