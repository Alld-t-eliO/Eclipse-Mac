#!/usr/bin/env bash
# eclipse: description: Create a local backup archive of the current user's main folders on the Desktop.
# eclipse: tags: backup, mac, user-system
# eclipse: param: --destination <folder> optional backup root, default ~/Desktop/backup
# eclipse: param: --include-library include ~/Library except common cache folders
# eclipse: param: --dry-run show what would be archived without creating the backup
# eclipse: dry-run-required: true

set -euo pipefail

BACKUP_ROOT="${HOME}/Desktop/backup"
INCLUDE_LIBRARY=0
DRY_RUN=0
ARCHIVE_NAME=""

usage() {
  printf '%s\n' "Usage: user-system-backup.sh [--dry-run] [--destination <folder>] [--include-library] [--name <archive-name>]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --destination)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        printf '%s\n' "Missing value for --destination" >&2
        exit 2
      fi
      BACKUP_ROOT="$2"
      shift 2
      ;;
    --include-library)
      INCLUDE_LIBRARY=1
      shift
      ;;
    --name)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        printf '%s\n' "Missing value for --name" >&2
        exit 2
      fi
      ARCHIVE_NAME="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$ARCHIVE_NAME" ]]; then
  STAMP="$(date '+%Y%m%d-%H%M%S')"
  HOST="$(hostname -s 2>/dev/null || hostname)"
  ARCHIVE_NAME="user-system-backup-${HOST}-${STAMP}.tar.gz"
fi

BACKUP_ROOT="${BACKUP_ROOT/#\~/$HOME}"
ARCHIVE_PATH="${BACKUP_ROOT}/${ARCHIVE_NAME}"

SOURCES=(
  "Desktop"
  "Documents"
  "Downloads"
  "Pictures"
  "Movies"
  "Music"
  "Public"
  ".zprofile"
  ".zshrc"
  ".bash_profile"
  ".bashrc"
  ".profile"
)

if [[ "$INCLUDE_LIBRARY" -eq 1 ]]; then
  SOURCES+=("Library")
fi

EXISTING_SOURCES=()
for source in "${SOURCES[@]}"; do
  if [[ -e "${HOME}/${source}" ]]; then
    EXISTING_SOURCES+=("$source")
  fi
done

if [[ "${#EXISTING_SOURCES[@]}" -eq 0 ]]; then
  printf '%s\n' "No user folders found to back up." >&2
  exit 1
fi

TAR_EXCLUDES=(
  "--exclude=Desktop/backup"
  "--exclude=Desktop/backup/*"
  "--exclude=.Trash"
  "--exclude=.Trash/*"
  "--exclude=Library/Caches"
  "--exclude=Library/Caches/*"
  "--exclude=Library/Logs"
  "--exclude=Library/Logs/*"
  "--exclude=Library/Developer/Xcode/DerivedData"
  "--exclude=Library/Developer/Xcode/DerivedData/*"
  "--exclude=*/node_modules"
  "--exclude=*/node_modules/*"
  "--exclude=*/.venv"
  "--exclude=*/.venv/*"
  "--exclude=*/__pycache__"
  "--exclude=*/__pycache__/*"
)

printf 'Backup destination: %s\n' "$ARCHIVE_PATH"
printf '%s\n' "Sources:"
printf '  %s\n' "${EXISTING_SOURCES[@]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '%s\n' "Dry-run only. No archive created."
  exit 0
fi

mkdir -p "$BACKUP_ROOT"
tar -czf "$ARCHIVE_PATH" -C "$HOME" "${TAR_EXCLUDES[@]}" "${EXISTING_SOURCES[@]}"
chmod 600 "$ARCHIVE_PATH"
printf 'Backup created: %s\n' "$ARCHIVE_PATH"
