#!/usr/bin/env bash
# eclipse: description: Keep only the newest local backup archives and remove older ones.
# eclipse: tags: backup, cleanup, rotation
# eclipse: param: --folder <folder> backup folder, default ~/Desktop/backup
# eclipse: param: --keep <count> number of newest archives to keep, default 5
# eclipse: param: --yes delete old backups
# eclipse: param: --dry-run show old backups without deleting
# eclipse: dry-run-required: true

set -euo pipefail

FOLDER="${HOME}/Desktop/backup"
KEEP=5
YES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --folder)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --folder" >&2; exit 2; }
      FOLDER="${2/#\~/$HOME}"
      shift 2
      ;;
    --keep)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --keep" >&2; exit 2; }
      KEEP="$2"
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
      printf '%s\n' "Usage: rotate-local-backups.sh [--folder <folder>] [--keep <count>] [--dry-run] [--yes]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ "$KEEP" =~ ^[0-9]+$ && "$KEEP" -gt 0 ]] || { printf '%s\n' "--keep must be a positive number" >&2; exit 2; }
[[ -d "$FOLDER" ]] || { printf 'Backup folder not found: %s\n' "$FOLDER" >&2; exit 1; }

OLD_LIST="$(mktemp)"
find "$FOLDER" -maxdepth 1 -type f \( -name '*.tar.gz' -o -name '*.zip' -o -name '*.enc' \) -print0 |
  while IFS= read -r -d '' file; do
    printf '%s\t%s\n' "$(stat -f '%m' "$file")" "$file"
  done |
  sort -rn |
  awk -v keep="$KEEP" 'NR > keep {sub(/^[^\t]*\t/, ""); print}' > "$OLD_LIST"

if [[ ! -s "$OLD_LIST" ]]; then
  rm -f "$OLD_LIST"
  printf '%s\n' "No old backups to rotate."
  exit 0
fi

printf '%s\n' "Old backups:"
sed 's/^/  /' "$OLD_LIST"

if [[ "$DRY_RUN" -eq 1 ]]; then
  rm -f "$OLD_LIST"
  printf '%s\n' "Dry-run only. No backup removed."
  exit 0
fi

[[ "$YES" -eq 1 ]] || { printf '%s\n' "Refusing to remove backups without --yes." >&2; exit 2; }
removed=0
while IFS= read -r file; do
  rm -f -- "$file"
  removed=$((removed + 1))
done < "$OLD_LIST"
rm -f "$OLD_LIST"
printf 'Removed backups: %s\n' "$removed"
