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

rsync_excludes_for() {
  local subdir="$1"
  local -n _out=$2
  _out=(--exclude '.DS_Store')
  if [[ ! -d "$SRC/$subdir" ]]; then
    return
  fi
  while IFS= read -r name; do
    _out+=(--exclude "$name")
  done < <(python3 "$REPO_ROOT/scripts/workplace-adapters.py" backup-excludes "$subdir")
}

if [[ -d "$SRC/agents" ]]; then
  agent_excludes=()
  rsync_excludes_for agents agent_excludes
  rsync -a --delete "${agent_excludes[@]}" "$SRC/agents/" "$REPO_ROOT/agents/"
fi
if [[ -d "$SRC/hooks" ]]; then
  rsync -a --delete --exclude '.DS_Store' --exclude '__pycache__' --exclude '*.pyc' \
    --exclude 'state/' --exclude 'first-party.json' \
    "$SRC/hooks/" "$REPO_ROOT/hooks/"
fi
if [[ -f "$SRC/hooks.json" ]]; then
  cp "$SRC/hooks.json" "$REPO_ROOT/hooks.json"
fi
if [[ -d "$SRC/skills" ]]; then
  skill_excludes=()
  rsync_excludes_for skills skill_excludes
  rsync -a --delete "${skill_excludes[@]}" "$SRC/skills/" "$REPO_ROOT/skills/"
fi
if [[ -f "$SRC/permissions.json" ]]; then
  cp "$SRC/permissions.json" "$REPO_ROOT/permissions.json"
fi
if [[ -f "$SRC/LICENSE" ]]; then
  cp "$SRC/LICENSE" "$REPO_ROOT/LICENSE"
fi
# Always-apply user rules (*.mdc). Do not --delete: rules/ also holds user-rules.md.
if [[ -d "$SRC/rules" ]]; then
  mkdir -p "$REPO_ROOT/rules"
  rule_excludes=(--exclude 'user-rules.md')
  rsync_excludes_for rules rule_excludes
  rsync -a "${rule_excludes[@]}" "$SRC/rules/" "$REPO_ROOT/rules/"
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
