#!/usr/bin/env bash
# eclipse: description: Search for probable local secrets without printing secret values.
# eclipse: tags: security, secrets, audit
# eclipse: param: --path <folder> folder to scan, default current directory
# eclipse: param: --limit <count> maximum findings, default 100

set -euo pipefail

ROOT="$(pwd)"
LIMIT=100

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --path" >&2; exit 2; }
      ROOT="${2/#\~/$HOME}"
      shift 2
      ;;
    --limit)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --limit" >&2; exit 2; }
      LIMIT="$2"
      shift 2
      ;;
    -h|--help)
      printf '%s\n' "Usage: find-secrets-local.sh [--path <folder>] [--limit <count>]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ -d "$ROOT" ]] || { printf 'Folder not found: %s\n' "$ROOT" >&2; exit 1; }
[[ "$LIMIT" =~ ^[0-9]+$ && "$LIMIT" -gt 0 ]] || { printf '%s\n' "--limit must be a positive number" >&2; exit 2; }

PATTERN='(api[_-]?key|secret|token|password|passwd|private[_-]?key|BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY|AKIA[0-9A-Z]{16})'
count=0

while IFS= read -r -d '' file; do
  while IFS=: read -r line_number _; do
    [[ -n "${line_number:-}" ]] || continue
    printf '%s:%s probable secret pattern\n' "$file" "$line_number"
    count=$((count + 1))
    [[ "$count" -ge "$LIMIT" ]] && exit 0
  done < <(grep -EnI "$PATTERN" "$file" 2>/dev/null || true)
done < <(find "$ROOT" -type f \
  -not -path '*/.git/*' \
  -not -path '*/node_modules/*' \
  -not -path '*/.venv/*' \
  -not -path '*/__pycache__/*' \
  -print0)

[[ "$count" -gt 0 ]] || printf '%s\n' "No probable secret found."
