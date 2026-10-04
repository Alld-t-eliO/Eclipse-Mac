"""Private, atomic persistence for Eclipse's operational data."""
from __future__ import annotations

import os
import tempfile
import fcntl
from functools import wraps
from pathlib import Path


def atomic_write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def serialized(path_for):
    """Serialize read/modify/write operations using a stable sidecar lock."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            path = path_for(kwargs)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                return function(*args, **kwargs)
        return wrapped
    return decorate
