#!/usr/bin/env bash
# Symlink workplace adapter project overlays into a target repo's .cursor/.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/target-project" >&2
  exit 1
fi

TARGET="$(cd "$1" && pwd)"
exec python3 "$REPO_ROOT/scripts/workplace-adapters.py" link-project "$TARGET"
