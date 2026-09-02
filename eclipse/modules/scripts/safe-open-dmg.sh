#!/usr/bin/env bash
# eclipse: description: Inspect a DMG before opening it: signature, quarantine, size, checksum, and image info.
# eclipse: tags: security, dmg, quarantine
# eclipse: param: --file <path.dmg> DMG file to inspect
# eclipse: param: --open open the DMG after inspection

set -euo pipefail

DMG=""
OPEN_AFTER=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)
      [[ $# -ge 2 ]] || { printf '%s\n' "Missing value for --file" >&2; exit 2; }
      DMG="${2/#\~/$HOME}"
      shift 2
      ;;
    --open)
      OPEN_AFTER=1
      shift
      ;;
    -h|--help)
      printf '%s\n' "Usage: safe-open-dmg.sh --file <path.dmg> [--open]"
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ -n "$DMG" && -f "$DMG" ]] || { printf '%s\n' "DMG file not found." >&2; exit 1; }
[[ "${DMG##*.}" = "dmg" ]] || { printf '%s\n' "File does not use the .dmg extension." >&2; exit 2; }

printf 'File: %s\n' "$DMG"
printf 'Size: %s bytes\n' "$(stat -f '%z' "$DMG")"
printf 'SHA256: %s\n' "$(shasum -a 256 "$DMG" | awk '{print $1}')"
printf '\nQuarantine:\n'
xattr -p com.apple.quarantine "$DMG" 2>/dev/null || printf '%s\n' "  none"
printf '\nGatekeeper assessment:\n'
spctl -a -vv -t open "$DMG" 2>&1 || true
printf '\nCode signature:\n'
codesign -dv --verbose=4 "$DMG" 2>&1 || true
printf '\nImage info:\n'
hdiutil imageinfo "$DMG" 2>/dev/null | sed -n '1,40p' || true

if [[ "$OPEN_AFTER" -eq 1 ]]; then
  open "$DMG"
fi
