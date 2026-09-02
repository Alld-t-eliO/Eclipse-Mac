#!/usr/bin/env bash

set -euo pipefail

APP_NAME="Eclipse"
PACKAGE_NAME="eclipse-mac"
MIN_PYTHON="3.11"
INSTALL_DIR="${HOME}/.local/share/eclipse-venv"
BIN_DIR="${INSTALL_DIR}/bin"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
WHEEL_PATH="${PROJECT_ROOT}/dist/eclipse_mac-0.3.0-py3-none-any.whl"
SOURCE_ARCHIVE="${PROJECT_ROOT}/dist/eclipse_mac-0.3.0.tar.gz"
PROFILE_FILE="${HOME}/.zprofile"
ADD_TO_PATH=1
UPGRADE_PIP=1
INSTALL_MODE="auto"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --install-dir <path>     Virtual environment path, default ~/.local/share/eclipse-venv
  --source                 Install from the current project directory
  --wheel                  Install from dist/eclipse_mac-0.3.0-py3-none-any.whl
  --archive                Install from dist/eclipse_mac-0.3.0.tar.gz
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
      [[ $# -ge 2 ]] || fail "Missing value for --install-dir."
      INSTALL_DIR="$(expand_path "$2")"
      BIN_DIR="${INSTALL_DIR}/bin"
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

command -v python3 >/dev/null 2>&1 || fail "python3 is required. Install Python ${MIN_PYTHON}+ first."

python3 - <<PY
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

log "Creating virtual environment: ${INSTALL_DIR}"
python3 -m venv "$INSTALL_DIR"

if [[ "$UPGRADE_PIP" -eq 1 ]]; then
  log "Upgrading pip"
  "${BIN_DIR}/python" -m pip install --upgrade pip
fi

case "$INSTALL_MODE" in
  auto)
    if [[ -f "$WHEEL_PATH" ]]; then
      INSTALL_TARGET="$WHEEL_PATH"
    elif [[ -f "$SOURCE_ARCHIVE" ]]; then
      INSTALL_TARGET="$SOURCE_ARCHIVE"
    else
      INSTALL_TARGET="$PROJECT_ROOT"
    fi
    ;;
  wheel)
    [[ -f "$WHEEL_PATH" ]] || fail "Wheel not found: ${WHEEL_PATH}"
    INSTALL_TARGET="$WHEEL_PATH"
    ;;
  archive)
    [[ -f "$SOURCE_ARCHIVE" ]] || fail "Source archive not found: ${SOURCE_ARCHIVE}"
    INSTALL_TARGET="$SOURCE_ARCHIVE"
    ;;
  source)
    INSTALL_TARGET="$PROJECT_ROOT"
    ;;
  *)
    fail "Invalid install mode."
    ;;
esac

log "Installing ${PACKAGE_NAME} from ${INSTALL_TARGET}"
"${BIN_DIR}/python" -m pip install --upgrade "$INSTALL_TARGET"

if [[ "$ADD_TO_PATH" -eq 1 ]]; then
  PATH_LINE='export PATH="$HOME/.local/share/eclipse-venv/bin:$PATH"'
  if [[ "$INSTALL_DIR" != "${HOME}/.local/share/eclipse-venv" ]]; then
    PATH_LINE="export PATH=\"${BIN_DIR}:\$PATH\""
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

log "Verifying installation"
"${BIN_DIR}/eclipse" --version
"${BIN_DIR}/eclipse" scripts info backup-eclipse-data >/dev/null
"${BIN_DIR}/eclipse" vps upload --help >/dev/null

cat <<EOF

${APP_NAME} installed successfully.

Run now:
  ${BIN_DIR}/eclipse ui

After opening a new terminal:
  eclipse ui

VPS defaults can be configured in:
  ${PROJECT_ROOT}/eclipse/vps/config/config.sh
EOF
