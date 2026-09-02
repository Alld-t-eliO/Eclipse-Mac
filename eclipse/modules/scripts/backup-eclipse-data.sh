#!/usr/bin/env bash
# eclipse: description: Back up only Eclipse local data, scripts, logs, memory, and recovery state.
# eclipse: tags: backup, eclipse, recovery
# eclipse: param: --destination <folder> backup destination, default ~/Desktop/backup
# eclipse: param: --dry-run show included paths without creating an archive
# eclipse: dry-run-required: true

set -euo pipefail

DESTINATION="${HOME}/Desktop/backup"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --destination)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --destination" >&2; exit 2; }
      DESTINATION="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      printf '%s\n' "Usage: backup-eclipse-data.sh [--dry-run] [--destination <folder>]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

DESTINATION="${DESTINATION/#\~/$HOME}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
ARCHIVE="${DESTINATION}/eclipse-data-backup-${STAMP}.tar.gz"
PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

SOURCES=(
  "Library/Application Support/Eclipse"
  ".local/state/eclipse"
)

if [[ -d "${PROJECT_ROOT}/scripts" ]]; then
  SOURCES+=("${PROJECT_ROOT}/scripts")
fi
if [[ -d "${PROJECT_ROOT}/eclipse/modules/scripts" ]]; then
  SOURCES+=("${PROJECT_ROOT}/eclipse/modules/scripts")
fi

EXISTING=()
for source in "${SOURCES[@]}"; do
  if [[ "$source" = /* ]]; then
    [[ -e "$source" ]] && EXISTING+=("$source")
  else
    [[ -e "${HOME}/${source}" ]] && EXISTING+=("$source")
  fi
done

printf 'Backup destination: %s\n' "$ARCHIVE"
printf '%s\n' "Sources:"
printf '  %s\n' "${EXISTING[@]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '%s\n' "Dry-run only. No archive created."
  exit 0
fi

mkdir -p "$DESTINATION"
tar -czf "$ARCHIVE" -C "$HOME" "${EXISTING[@]}"
chmod 600 "$ARCHIVE"
printf 'Backup created: %s\n' "$ARCHIVE"
