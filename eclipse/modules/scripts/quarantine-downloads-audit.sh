#!/usr/bin/env bash
# eclipse: description: List downloaded files that still have the macOS quarantine attribute.
# eclipse: tags: security, quarantine, downloads
# eclipse: param: --folder <folder> folder to inspect, default ~/Downloads

set -euo pipefail

FOLDER="${HOME}/Downloads"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --folder)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --folder" >&2; exit 2; }
      FOLDER="${2/#\~/$HOME}"
      shift 2
      ;;
    -h|--help)
      printf '%s\n' "Usage: quarantine-downloads-audit.sh [--folder <folder>]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ -d "$FOLDER" ]] || { printf 'Folder not found: %s\n' "$FOLDER" >&2; exit 1; }

found=0
while IFS= read -r -d '' file; do
  if quarantine="$(xattr -p com.apple.quarantine "$file" 2>/dev/null)"; then
    found=1
    printf '%s\n' "$file"
    printf '  quarantine: %s\n' "$quarantine"
  fi
done < <(find "$FOLDER" -type f -maxdepth 2 -print0)

[[ "$found" -eq 1 ]] || printf '%s\n' "No quarantined download found."
