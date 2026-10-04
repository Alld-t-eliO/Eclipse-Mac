#!/usr/bin/env bash
# eclipse: description: Verify that a .tar.gz backup is readable and list its content without extraction.
# eclipse: tags: backup, verify, recovery
# eclipse: param: --file <backup.tar.gz> backup archive to verify
# eclipse: param: --limit <count> number of entries to list, default 120

set -euo pipefail

BACKUP=""
LIMIT=120

while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --file" >&2; exit 2; }
      BACKUP="${2/#\~/$HOME}"
      shift 2
      ;;
    --limit)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --limit" >&2; exit 2; }
      LIMIT="$2"
      shift 2
      ;;
    -h|--help)
      printf '%s\n' "Usage: verify-backup.sh --file <backup.tar.gz> [--limit <count>]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ -n "$BACKUP" && -f "$BACKUP" ]] || { printf '%s\n' "Backup archive not found." >&2; exit 1; }
[[ "$LIMIT" =~ ^[0-9]+$ && "$LIMIT" -gt 0 ]] || { printf '%s\n' "--limit must be a positive number" >&2; exit 2; }

printf 'Backup: %s\n' "$BACKUP"
printf 'Size: %s bytes\n' "$(stat -f '%z' "$BACKUP")"
printf 'SHA256: %s\n' "$(shasum -a 256 "$BACKUP" | awk '{print $1}')"
printf '\nIntegrity:\n'
tar -tzf "$BACKUP" >/dev/null
printf '%s\n' "  readable"
printf '\nContent preview:\n'
tar -tzf "$BACKUP" | sed -n "1,${LIMIT}p"
