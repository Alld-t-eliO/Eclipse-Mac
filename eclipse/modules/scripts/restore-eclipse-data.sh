#!/usr/bin/env bash
# eclipse: description: Restore an Eclipse data backup into a chosen local folder for review.
# eclipse: tags: restore, eclipse, recovery
# eclipse: param: --backup <archive.tar.gz> backup archive to restore
# eclipse: param: --destination <folder> restore folder, default ~/Desktop/backup/eclipse-restore-<date>
# eclipse: param: --yes confirm extraction
# eclipse: param: --dry-run list archive content without extracting
# eclipse: dry-run-required: true

set -euo pipefail

BACKUP=""
DESTINATION=""
YES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --backup" >&2; exit 2; }
      BACKUP="${2/#\~/$HOME}"
      shift 2
      ;;
    --destination)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --destination" >&2; exit 2; }
      DESTINATION="${2/#\~/$HOME}"
      shift 2
      ;;
    --yes)
      YES=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      printf '%s\n' "Usage: restore-eclipse-data.sh --backup <archive.tar.gz> [--destination <folder>] [--dry-run] [--yes]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ -n "$BACKUP" && -f "$BACKUP" ]] || { printf '%s\n' "Backup archive not found." >&2; exit 1; }

if [[ "$DRY_RUN" -eq 1 ]]; then
  tar -tzf "$BACKUP" | sed -n '1,120p'
  exit 0
fi

[[ "$YES" -eq 1 ]] || { printf '%s\n' "Refusing to restore without --yes." >&2; exit 2; }

if [[ -z "$DESTINATION" ]]; then
  DESTINATION="${HOME}/Desktop/backup/eclipse-restore-$(date '+%Y%m%d-%H%M%S')"
fi

mkdir -p "$DESTINATION"
tar -xzf "$BACKUP" -C "$DESTINATION"
chmod -R go-rwx "$DESTINATION" 2>/dev/null || true
printf 'Backup restored for review: %s\n' "$DESTINATION"
