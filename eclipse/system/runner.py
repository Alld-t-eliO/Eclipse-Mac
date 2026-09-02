from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass

from eclipse.audit import record
from eclipse.errors import EclipseError


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str


def require_program(program: str) -> None:
    if shutil.which(program) is None:
        raise EclipseError(f"Required command not found: {program}")


def run_local(command: list[str], *, capture: bool = False, event: str = "command") -> Result:
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=capture,
        )
    except OSError as error:
        record(event, success=False, details={"program": command[0], "error": str(error)})
        raise EclipseError(f"Unable to launch {command[0]}: {error}") from error
    record(event, success=completed.returncode == 0, details={"program": command[0], "code": completed.returncode})
    return Result(completed.returncode, completed.stdout or "", completed.stderr or "")


def shell_display(command: list[str]) -> str:
    return shlex.join(command)
