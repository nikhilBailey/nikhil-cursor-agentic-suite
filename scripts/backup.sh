#!/usr/bin/env bash
# Copy user-level Cursor agentic files from ~/.cursor into this repo.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${CURSOR_HOME:-$HOME/.cursor}"

if [[ ! -d "$SRC" ]]; then
  echo "Source directory not found: $SRC" >&2
  exit 1
fi

mkdir -p "$REPO_ROOT/agents" "$REPO_ROOT/hooks" "$REPO_ROOT/skills" "$REPO_ROOT/rules"

if [[ -d "$SRC/agents" ]]; then
  rsync -a --delete --exclude '.DS_Store' "$SRC/agents/" "$REPO_ROOT/agents/"
fi
if [[ -d "$SRC/hooks" ]]; then
  rsync -a --delete --exclude '.DS_Store' --exclude '__pycache__' --exclude '*.pyc' \
    --exclude 'state/' \
    "$SRC/hooks/" "$REPO_ROOT/hooks/"
fi
if [[ -f "$SRC/hooks.json" ]]; then
  cp "$SRC/hooks.json" "$REPO_ROOT/hooks.json"
fi
if [[ -d "$SRC/skills" ]]; then
  # Skip skills that are symlinks (workplace-specific, not in skills/).
  rsync_excludes=(--exclude '.DS_Store')
  while IFS= read -r name; do
    rsync_excludes+=(--exclude "$name")
  done < <(find "$SRC/skills" -mindepth 1 -maxdepth 1 -type l -exec basename {} \;)
  rsync -a --delete "${rsync_excludes[@]}" "$SRC/skills/" "$REPO_ROOT/skills/"
fi
if [[ -f "$SRC/permissions.json" ]]; then
  cp "$SRC/permissions.json" "$REPO_ROOT/permissions.json"
fi
if [[ -f "$SRC/LICENSE" ]]; then
  cp "$SRC/LICENSE" "$REPO_ROOT/LICENSE"
fi

python3 - "$SRC/mcp.json" "$REPO_ROOT/mcp.json.example" <<'PY'
import json, sys
from pathlib import Path

src, dest = Path(sys.argv[1]), Path(sys.argv[2])
if not src.exists():
    raise SystemExit(0)

def redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = k.lower()
            if any(s in key for s in ("token", "secret", "password", "key", "credential", "auth")):
                out[k] = "<REDACTED>"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj

dest.write_text(json.dumps(redact(json.loads(src.read_text())), indent=2) + "\n")
PY

echo "Backed up user Cursor files into $REPO_ROOT"
echo "Review the diff, then snapshot and upload from your own terminal (agent git writes are blocked)."
