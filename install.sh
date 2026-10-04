#!/usr/bin/env bash

set -euo pipefail

APP_NAME="Eclipse"
PACKAGE_NAME="eclipse-mac"
MIN_PYTHON="3.11"
INSTALL_DIR="${HOME}/.local/share/eclipse-venv"
BIN_DIR="${INSTALL_DIR}/bin"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${ECLIPSE_PYTHON:-python3}"
PROFILE_FILE="${HOME}/.zprofile"
ADD_TO_PATH=1
UPGRADE_PIP=1
INSTALL_MODE="auto"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --install-dir <path>     Virtual environment path, default ~/.local/share/eclipse-venv
  --python <executable>    Python 3.11+ interpreter (default python3)
  --source                 Install from the current project directory
  --wheel                  Install the only eclipse_mac wheel in dist/
  --archive                Install the only eclipse_mac source archive in dist/
  --no-path                Do not update ~/.zprofile
  --no-pip-upgrade         Do not upgrade pip before installing
  -h, --help               Show this help
EOF
}

log() {
  printf '%s\n' "==> $*"
}

warn() {
  printf '%s\n' "Warning: $*" >&2
}

fail() {
  printf '%s\n' "Error: $*" >&2
  exit 1
}

expand_path() {
  case "$1" in
    "~") printf '%s\n' "$HOME" ;;
    "~/"*) printf '%s\n' "${HOME}/${1#"~/"}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      [[ $# -ge 2 && -n "$2" ]] || fail "Missing value for --install-dir."
      INSTALL_DIR="$(expand_path "$2")"
      BIN_DIR="${INSTALL_DIR}/bin"
      shift 2
      ;;
    --python)
      [[ $# -ge 2 && -n "$2" ]] || fail "Missing value for --python."
      PYTHON_BIN="$2"
      shift 2
      ;;
    --source)
      INSTALL_MODE="source"
      shift
      ;;
    --wheel)
      INSTALL_MODE="wheel"
      shift
      ;;
    --archive)
      INSTALL_MODE="archive"
      shift
      ;;
    --no-path)
      ADD_TO_PATH=0
      shift
      ;;
    --no-pip-upgrade)
      UPGRADE_PIP=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "This installer is intended for macOS."
fi

command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "Python ${MIN_PYTHON}+ is required. Install it from python.org, then use --python /path/to/python3 if needed."

"$PYTHON_BIN" - <<PY
import sys
minimum = tuple(int(part) for part in "${MIN_PYTHON}".split("."))
current = sys.version_info[:2]
if current < minimum:
    raise SystemExit(f"Python {minimum[0]}.{minimum[1]}+ is required, found {current[0]}.{current[1]}.")
PY

missing_tools=()
for tool in ssh rsync tar shasum xattr; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing_tools+=("$tool")
  fi
done

if [[ "${#missing_tools[@]}" -gt 0 ]]; then
  warn "Missing optional macOS tools: ${missing_tools[*]}"
  warn "Some Eclipse features may be unavailable until these tools are installed."
fi

case "$INSTALL_MODE" in
  auto)
    INSTALL_TARGET="$PROJECT_ROOT"
    ;;
  wheel)
    shopt -s nullglob
    artifacts=("${PROJECT_ROOT}"/dist/eclipse_mac-*.whl)
    [[ ${#artifacts[@]} -eq 1 ]] || fail "Expected exactly one Eclipse wheel in dist/. Use --source or keep only the desired wheel."
    INSTALL_TARGET="${artifacts[0]}"
    ;;
  archive)
    shopt -s nullglob
    artifacts=("${PROJECT_ROOT}"/dist/eclipse_mac-*.tar.gz)
    [[ ${#artifacts[@]} -eq 1 ]] || fail "Expected exactly one Eclipse source archive in dist/. Use --source or keep only the desired archive."
    INSTALL_TARGET="${artifacts[0]}"
    ;;
  source)
    INSTALL_TARGET="$PROJECT_ROOT"
    ;;
  *)
    fail "Invalid install mode."
    ;;
esac

INSTALL_DIR="$("$PYTHON_BIN" -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$INSTALL_DIR")"
BIN_DIR="${INSTALL_DIR}/bin"

log "Creating virtual environment: ${INSTALL_DIR}"
"$PYTHON_BIN" -m venv "$INSTALL_DIR"

if [[ "$UPGRADE_PIP" -eq 1 ]]; then
  log "Upgrading pip"
  "${BIN_DIR}/python" -m pip install --upgrade pip
fi

log "Installing ${PACKAGE_NAME} from ${INSTALL_TARGET}"
"${BIN_DIR}/python" -m pip install --upgrade "$INSTALL_TARGET"

log "Verifying installation"
"${BIN_DIR}/eclipse" --version
"${BIN_DIR}/eclipse" scripts info backup-eclipse-data >/dev/null
"${BIN_DIR}/eclipse" vps upload --help >/dev/null


if [[ "$ADD_TO_PATH" -eq 1 ]]; then
  PATH_LINE='export PATH="$HOME/.local/share/eclipse-venv/bin:$PATH"'
  if [[ "$INSTALL_DIR" != "${HOME}/.local/share/eclipse-venv" ]]; then
    printf -v QUOTED_BIN '%q' "$BIN_DIR"
    PATH_LINE="export PATH=${QUOTED_BIN}:\$PATH"
  fi
  touch "$PROFILE_FILE"
  if ! grep -Fq "$PATH_LINE" "$PROFILE_FILE"; then
    log "Adding Eclipse to PATH in ${PROFILE_FILE}"
    {
      printf '\n'
      printf '%s\n' "# Eclipse"
      printf '%s\n' "$PATH_LINE"
    } >> "$PROFILE_FILE"
  fi
fi


printf -v LAUNCH_COMMAND '%q ui' "${BIN_DIR}/eclipse"
cat <<EOF

${APP_NAME} installed successfully.

Run now:
  ${LAUNCH_COMMAND}

For future zsh terminals, PATH is configured unless --no-path was used.
For other shells, use the full command above or add ${BIN_DIR} to PATH.

VPS uploads: pass --host, --user and --remote-path to eclipse vps upload.
See README.md for configuration and troubleshooting.
EOF
