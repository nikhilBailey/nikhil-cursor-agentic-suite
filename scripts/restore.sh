#!/usr/bin/env bash
# Restore user-level Cursor agentic files from this repo into ~/.cursor.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${CURSOR_HOME:-$HOME/.cursor}"

mkdir -p "$DEST/agents" "$DEST/hooks" "$DEST/skills"

if [[ -d "$REPO_ROOT/agents" ]]; then
  rsync -a --exclude '.DS_Store' "$REPO_ROOT/agents/" "$DEST/agents/"
fi
if [[ -d "$REPO_ROOT/hooks" ]]; then
  rsync -a --exclude '.DS_Store' --exclude '__pycache__' --exclude '*.pyc' \
    "$REPO_ROOT/hooks/" "$DEST/hooks/"
fi
if [[ -f "$REPO_ROOT/hooks.json" ]]; then
  cp "$REPO_ROOT/hooks.json" "$DEST/hooks.json"
fi
if [[ -d "$REPO_ROOT/skills" ]]; then
  rsync -a --exclude '.DS_Store' "$REPO_ROOT/skills/" "$DEST/skills/"
fi
if [[ -f "$REPO_ROOT/permissions.json" ]]; then
  cp "$REPO_ROOT/permissions.json" "$DEST/permissions.json"
fi
if [[ -f "$REPO_ROOT/LICENSE" ]]; then
  cp "$REPO_ROOT/LICENSE" "$DEST/LICENSE"
fi

chmod +x "$DEST"/hooks/*.sh "$DEST"/hooks/*.py 2>/dev/null || true

if [[ -f "$REPO_ROOT/mcp.json.example" && ! -f "$DEST/mcp.json" ]]; then
  cp "$REPO_ROOT/mcp.json.example" "$DEST/mcp.json"
  echo "Installed mcp.json from example. Replace <REDACTED> values before use."
elif [[ -f "$DEST/mcp.json" ]]; then
  echo "Left existing $DEST/mcp.json in place (not overwritten)."
fi

echo "Restored agentic files to $DEST"
echo "Re-add user rules from $REPO_ROOT/rules/user-rules.md in Cursor Settings → Rules."
echo "Restart Cursor so hooks and skills reload."
