from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from eclipse.system.errors import EclipseError

HOST_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
USER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
REMOTE_PATH_RE = re.compile(r"^[A-Za-z0-9_./~@%+=:,-]+$")
CONFIG_KEYS = {
    "ECLIPSE_VPS_HOST": "host",
    "ECLIPSE_VPS_USER": "user",
    "ECLIPSE_VPS_REMOTE_PATH": "remote_path",
    "ECLIPSE_VPS_PORT": "port",
    "ECLIPSE_VPS_IDENTITY": "identity",
}


def default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "config.sh"


def unquote_config_value(value: str) -> str:
    clean = value.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {"'", '"'}:
        return clean[1:-1]
    return clean


def load_config(path: Path | None = None) -> dict[str, str]:
    config_path = path or default_config_path()
    if not config_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in config_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, raw_value = clean.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        mapped = CONFIG_KEYS.get(key)
        if mapped:
            values[mapped] = unquote_config_value(raw_value)
    return values


def merge_config(
    *,
    host: str | None = None,
    remote_path: str | None = None,
    user: str | None = None,
    port: int | None = None,
    identity: Path | None = None,
    config_path: Path | None = None,
) -> tuple[str, str, str | None, int | None, Path | None]:
    config = load_config(config_path)
    final_host = host or config.get("host")
    final_remote_path = remote_path or config.get("remote_path")
    final_user = user or config.get("user")
    final_port = port
    if final_port is None and config.get("port"):
        try:
            final_port = int(config["port"])
        except ValueError as error:
            raise EclipseError("Invalid VPS port in config.") from error
    final_identity = identity
    if final_identity is None and config.get("identity"):
        final_identity = Path(config["identity"])
    if not final_host:
        raise EclipseError("Missing VPS host. Pass --host or set ECLIPSE_VPS_HOST in vps/config/config.sh.")
    if not final_remote_path:
        raise EclipseError("Missing VPS remote path. Pass --remote-path or set ECLIPSE_VPS_REMOTE_PATH in vps/config/config.sh.")
    return final_host, final_remote_path, final_user, final_port, final_identity


@dataclass(frozen=True)
class UploadResult:
    source: Path
    destination: str
    dry_run: bool
    returncode: int
    stdout: str
    stderr: str

    def to_record(self) -> dict[str, object]:
        return {
            "source": str(self.source),
            "destination": self.destination,
            "dry_run": self.dry_run,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def validate_remote(host: str, remote_path: str, user: str | None = None) -> tuple[str, str]:
    clean_host = host.strip()
    clean_user = (user or "").strip()
    clean_path = remote_path.strip()
    if not clean_host or not HOST_RE.fullmatch(clean_host):
        raise EclipseError("Invalid VPS host.")
    if clean_user and not USER_RE.fullmatch(clean_user):
        raise EclipseError("Invalid VPS user.")
    if not clean_path or not REMOTE_PATH_RE.fullmatch(clean_path):
        raise EclipseError("Invalid VPS remote path.")
    login = f"{clean_user}@{clean_host}" if clean_user else clean_host
    return login, clean_path


def ssh_options(*, port: int | None = None, identity: Path | None = None) -> list[str]:
    options: list[str] = []
    if port is not None:
        if port < 1 or port > 65535:
            raise EclipseError("Invalid SSH port.")
        options.extend(["-p", str(port)])
    if identity is not None:
        key = identity.expanduser()
        if not key.is_file():
            raise EclipseError(f"SSH identity file not found: {key}")
        options.extend(["-i", str(key)])
    return options


def rsync_ssh_option(*, port: int | None = None, identity: Path | None = None) -> str | None:
    options = ssh_options(port=port, identity=identity)
    if not options:
        return None
    return "ssh " + " ".join(shlex.quote(option) for option in options)


def upload_path(
    source: Path,
    *,
    host: str | None = None,
    remote_path: str | None = None,
    user: str | None = None,
    port: int | None = None,
    identity: Path | None = None,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> UploadResult:
    local_source = source.expanduser().resolve()
    if not local_source.exists():
        raise EclipseError(f"Source path not found: {local_source}")
    host, remote_path, user, port, identity = merge_config(
        host=host,
        remote_path=remote_path,
        user=user,
        port=port,
        identity=identity,
        config_path=config_path,
    )
    login, clean_remote_path = validate_remote(host, remote_path, user)
    destination = f"{login}:{clean_remote_path.rstrip('/')}/"
    ssh_args = ssh_options(port=port, identity=identity)
    rsync_command = ["rsync", "-az"]
    ssh_arg = rsync_ssh_option(port=port, identity=identity)
    if ssh_arg:
        rsync_command.extend(["-e", ssh_arg])
    if dry_run:
        rsync_command.append("--dry-run")
    rsync_command.extend([str(local_source), destination])

    if dry_run:
        completed = subprocess.run(rsync_command, check=False, text=True, capture_output=True)
        return UploadResult(local_source, destination, True, completed.returncode, completed.stdout or "", completed.stderr or "")

    mkdir_command = ["ssh", *ssh_args, login, "mkdir", "-p", clean_remote_path]
    mkdir = subprocess.run(mkdir_command, check=False, text=True, capture_output=True)
    if mkdir.returncode:
        return UploadResult(local_source, destination, False, mkdir.returncode, mkdir.stdout or "", mkdir.stderr or "")
    completed = subprocess.run(rsync_command, check=False, text=True, capture_output=True)
    return UploadResult(local_source, destination, False, completed.returncode, completed.stdout or "", completed.stderr or "")


def format_upload_result(result: UploadResult) -> str:
    lines = [
        f"Source: {result.source}",
        f"Destination: {result.destination}",
        f"Dry-run: {result.dry_run}",
        f"Return code: {result.returncode}",
    ]
    if result.stdout.strip():
        lines.extend(("", result.stdout.strip()))
    if result.stderr.strip():
        lines.extend(("", result.stderr.strip()))
    return "\n".join(lines)


def upload_result_json(result: UploadResult) -> str:
    return json.dumps(result.to_record(), ensure_ascii=False, indent=2)
