#!/usr/bin/env bash
# Fast-path wrapper for gate-library-add.py. Keeps unrelated shell/file
# operations from paying a Python + network round-trip.
set -euo pipefail

INPUT="$(cat)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${SCRIPT_DIR}/gate-library-add.py"
EVENT="$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty')"

allow() {
  echo '{"permission":"allow"}'
  exit 0
}

noop() {
  echo '{}'
  exit 0
}

case "$EVENT" in
  sessionStart)
    printf '%s' "$INPUT" | python3 "$PYTHON"
    exit 0
    ;;
  beforeShellExecution|afterShellExecution)
    CMD="$(printf '%s' "$INPUT" | jq -r '.command // empty')"
    if ! printf '%s' "$CMD" | grep -Eqi '(^|[[:space:];&|])(npm|npx|yarn|pnpm|bun|pip3?|poetry|uv|cargo|composer|bundle|dotnet|gem|go)([[:space:]]|$)'; then
      if [[ "$EVENT" == "beforeShellExecution" ]]; then
        allow
      else
        noop
      fi
    fi
    ;;
  preToolUse)
    TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')"
    PATH_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // empty')"
    BASE="$(basename "$PATH_NAME" | tr '[:upper:]' '[:lower:]')"
    case "$TOOL" in
      Write|StrReplace) ;;
      *) allow ;;
    esac
    case "$BASE" in
      package-lock.json|npm-shrinkwrap.json|yarn.lock|pnpm-lock.yaml|bun.lock|bun.lockb|poetry.lock|uv.lock|cargo.lock|go.sum|composer.lock|gemfile.lock|pipfile.lock)
        allow
        ;;
      package.json|pyproject.toml|pipfile|cargo.toml|go.mod|gemfile|composer.json|pom.xml)
        ;;
      *.csproj|*.fsproj|*.vbproj)
        ;;
      requirements*.txt)
        ;;
      *)
        allow
        ;;
    esac
    ;;
esac

printf '%s' "$INPUT" | python3 "$PYTHON"
