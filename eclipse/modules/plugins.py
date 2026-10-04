from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from eclipse.system.errors import EclipseError
from eclipse.system.storage import atomic_write


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


def user_plugins_root() -> Path:
    return Path(os.environ.get("ECLIPSE_PLUGINS_HOME", str(Path.home() / "Library" / "Application Support" / "Eclipse" / "plugins"))).expanduser()


def load_plugin(path: Path) -> PluginInfo:
    manifest = plugin_manifest(path)
    data: dict[str, Any] = {}
    if manifest.exists():
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise EclipseError(f"Invalid plugin manifest: {manifest} ({error})") from error
        if isinstance(raw, dict):
            data = raw
        else:
            raise EclipseError(f"Invalid plugin manifest: {manifest}: expected an object.")
        if not isinstance(data.get("enabled", True), bool):
            raise EclipseError(f"Invalid plugin enabled value: {manifest}")
    return PluginInfo(
        name=str(data.get("name") or path.name),
        path=path.resolve(),
        description=str(data.get("description") or ""),
        enabled=bool(data.get("enabled", True)),
    )


def list_plugins(root: Path | None = None) -> list[PluginInfo]:
    if root is None:
        plugins = {plugin.name: plugin for plugin in list_plugins(plugins_root())}
        plugins.update({plugin.name: plugin for plugin in list_plugins(user_plugins_root())})
        return sorted(plugins.values(), key=lambda plugin: plugin.name)
    folder = (root or plugins_root()).resolve()
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise EclipseError(f"Invalid plugins directory: {folder}")
    return [load_plugin(path) for path in sorted(folder.iterdir(), key=lambda item: item.name) if path.is_dir()]


def create_plugin(name: str, *, description: str = "", root: Path | None = None) -> PluginInfo:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
        raise EclipseError("Invalid plugin name.")
    folder = (root or user_plugins_root()) / name
    manifest = plugin_manifest(folder)
    if folder.exists() or folder.is_symlink():
        raise EclipseError(f"Plugin already exists: {name}")
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    payload = {"name": name, "description": description, "enabled": True}
    atomic_write(manifest, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return load_plugin(folder)
