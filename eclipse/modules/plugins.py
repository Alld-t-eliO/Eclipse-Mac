from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eclipse.system.errors import EclipseError


@dataclass(frozen=True)
class PluginInfo:
    name: str
    path: Path
    description: str = ""
    enabled: bool = True


def plugins_root() -> Path:
    return Path(__file__).resolve().parent.parent / "plugins"


def plugin_manifest(path: Path) -> Path:
    return path / "plugin.json"


def load_plugin(path: Path) -> PluginInfo:
    manifest = plugin_manifest(path)
    data: dict[str, Any] = {}
    if manifest.exists():
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise EclipseError(f"Invalid plugin manifest: {manifest} ({error})") from error
        if isinstance(raw, dict):
            data = raw
    return PluginInfo(
        name=str(data.get("name") or path.name),
        path=path.resolve(),
        description=str(data.get("description") or ""),
        enabled=bool(data.get("enabled", True)),
    )


def list_plugins(root: Path | None = None) -> list[PluginInfo]:
    folder = (root or plugins_root()).resolve()
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise EclipseError(f"Invalid plugins directory: {folder}")
    return [load_plugin(path) for path in sorted(folder.iterdir(), key=lambda item: item.name) if path.is_dir()]


def create_plugin(name: str, *, description: str = "", root: Path | None = None) -> PluginInfo:
    if not name or "/" in name or name.startswith("."):
        raise EclipseError("Invalid plugin name.")
    folder = (root or plugins_root()) / name
    manifest = plugin_manifest(folder)
    if manifest.exists():
        raise EclipseError(f"Plugin already exists: {name}")
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"name": name, "description": description, "enabled": True}
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return load_plugin(folder)
