#!/usr/bin/env bash
# eclipse: description: Clean common development cache folders in a project directory.
# eclipse: tags: cleanup, dev, project
# eclipse: param: --path <folder> project folder, default current directory
# eclipse: param: --yes delete cache files
# eclipse: param: --dry-run list cache files without deleting
# eclipse: dry-run-required: true

set -euo pipefail

PROJECT="$(pwd)"
YES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --path" >&2; exit 2; }
      PROJECT="${2/#\~/$HOME}"
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
      printf '%s\n' "Usage: project-clean-cache.sh [--path <folder>] [--dry-run] [--yes]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ -d "$PROJECT" ]] || { printf 'Project folder not found: %s\n' "$PROJECT" >&2; exit 1; }

TARGET_LIST="$(mktemp)"
find "$PROJECT" \
  \( -name '.pytest_cache' -o -name '__pycache__' -o -name '.mypy_cache' -o -name '.ruff_cache' -o -name 'dist' -o -name 'build' -o -name '.DS_Store' \) \
  -not -path '*/.git/*' -print > "$TARGET_LIST"

if [[ ! -s "$TARGET_LIST" ]]; then
  rm -f "$TARGET_LIST"
  printf '%s\n' "No cache target found."
  exit 0
fi

printf '%s\n' "Cache targets:"
sed 's/^/  /' "$TARGET_LIST"

if [[ "$DRY_RUN" -eq 1 ]]; then
  rm -f "$TARGET_LIST"
  printf '%s\n' "Dry-run only. No file removed."
  exit 0
fi

[[ "$YES" -eq 1 ]] || { printf '%s\n' "Refusing to clean without --yes." >&2; exit 2; }
removed=0
while IFS= read -r target; do
  rm -rf -- "$target"
  removed=$((removed + 1))
done < "$TARGET_LIST"
rm -f "$TARGET_LIST"
printf 'Removed cache targets: %s\n' "$removed"
