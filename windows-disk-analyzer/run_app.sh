#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe >/dev/null 2>&1; then
  WIN_DIR="$(wslpath -w "$SCRIPT_DIR")"
  exec powershell.exe -NoProfile -Command "Set-Location '$WIN_DIR'; python main.py $*"
fi

exec python3 main.py "$@"
