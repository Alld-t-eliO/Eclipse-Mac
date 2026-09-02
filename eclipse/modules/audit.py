from __future__ import annotations
import json
import getpass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_log_path() -> Path:
    return Path.home() / ".local" / "state" / "eclipse" / "audit.jsonl"


def record(event: str, *, success: bool, details: dict[str, Any] | None = None) -> None:
    path = default_log_path()
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": getpass.getuser(),
        "event": event,
        "success": success,
        "details": details or {},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        path.chmod(0o600)
    except OSError:
        pass
