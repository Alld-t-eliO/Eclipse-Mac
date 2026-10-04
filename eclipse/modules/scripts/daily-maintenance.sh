#!/usr/bin/env bash
# eclipse: description: Run a daily local maintenance pass with security checkup, light cleanup, and a summary report.
# eclipse: tags: maintenance, backup, cleanup, security
# eclipse: param: --security-checkup <path> optional security checkup script to run
# eclipse: param: --destination <folder> report destination, default ~/Desktop/backup
# eclipse: param: --apply remove light cleanup targets, otherwise report only

set -euo pipefail

DESTINATION="${HOME}/Desktop/backup"
SECURITY_CHECKUP="${ECLIPSE_SECURITY_CHECKUP:-}"
APPLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --security-checkup)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --security-checkup" >&2; exit 2; }
      SECURITY_CHECKUP="$2"
      shift 2
      ;;
    --destination)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --destination" >&2; exit 2; }
      DESTINATION="$2"
      shift 2
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    -h|--help)
      printf '%s\n' "Usage: daily-maintenance.sh [--security-checkup <path>] [--destination <folder>] [--apply]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

DESTINATION="${DESTINATION/#\~/$HOME}"
mkdir -p "$DESTINATION"
STAMP="$(date '+%Y%m%d-%H%M%S')"
REPORT="${DESTINATION}/daily-maintenance-${STAMP}.txt"

find_security_checkup() {
  if [[ -n "$SECURITY_CHECKUP" && -f "${SECURITY_CHECKUP/#\~/$HOME}" ]]; then
    printf '%s\n' "${SECURITY_CHECKUP/#\~/$HOME}"
    return 0
  fi
  for candidate in \
    "${HOME}/scripts/system_scanner/mac/security_checkup.sh" \
    "${HOME}/scripts/system_scanner/mac/security-checkup.sh" \
    "${HOME}/scripts/system_scanner/mac/checkup.sh"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

{
  printf 'Eclipse daily maintenance report\n'
  printf 'Created at: %s\n' "$(date)"
  printf 'User: %s\n' "$(id -un)"
  printf 'Host: %s\n\n' "$(hostname)"

  printf 'System summary\n'
  printf 'macOS: %s\n' "$(sw_vers -productVersion 2>/dev/null || true)"
  printf 'Uptime: %s\n' "$(uptime)"
  df -h /
  printf '\n'

  printf 'Security checkup\n'
  if security_script="$(find_security_checkup)"; then
    printf 'Running: %s\n' "$security_script"
    if [[ -x "$security_script" ]]; then
      "$security_script" || printf 'Security checkup exited with code %s\n' "$?"
    else
      sh "$security_script" || printf 'Security checkup exited with code %s\n' "$?"
    fi
  else
    printf '%s\n' "Security checkup not found. Set ECLIPSE_SECURITY_CHECKUP or pass --security-checkup."
  fi
  printf '\n'

  printf 'Light cleanup candidates\n'
  find "${HOME}/Downloads" -maxdepth 1 -type f \( -name '*.download' -o -name '*.crdownload' -o -name '.DS_Store' \) -print 2>/dev/null || true
  find "${HOME}/Desktop" -maxdepth 2 -name '.DS_Store' -print 2>/dev/null || true
  if [[ "$APPLY" -eq 1 ]]; then
    find "${HOME}/Downloads" -maxdepth 1 -type f \( -name '*.download' -o -name '*.crdownload' -o -name '.DS_Store' \) -delete 2>/dev/null || true
    find "${HOME}/Desktop" -maxdepth 2 -name '.DS_Store' -delete 2>/dev/null || true
    printf '%s\n' "Light cleanup applied."
  else
    printf '%s\n' "Report-only mode. Pass --apply to remove candidates."
  fi
} > "$REPORT" 2>&1

chmod 600 "$REPORT"
printf 'Maintenance report: %s\n' "$REPORT"
