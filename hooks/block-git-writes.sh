#!/usr/bin/env bash
# Blocks agent shell commands that create/push GitHub PRs or push to remotes.
# Edit this file to adjust which git/gh commands agents may run.
set -euo pipefail

input="$(cat)"
command="$(echo "$input" | jq -r '.command // empty')"

deny() {
  local reason="$1"
  jq -n \
    --arg cmd "$command" \
    --arg reason "$reason" \
    '{
      "permission": "deny",
      "user_message": $reason,
      "agent_message": ("Command blocked by ~/.cursor/hooks/block-git-writes.sh: " + $cmd)
    }'
  exit 0
}

# git write operations
if [[ "$command" =~ (^|[[:space:]])(git[[:space:]]+(-[^[:space:]]+[[:space:]]+)*)(commit|push)([[:space:]]|$) ]]; then
  deny "Blocked: git commit/push must be run manually outside the agent."
fi

# gh auth that wires git credentials for push (gh auth login is allowed)
if [[ "$command" =~ gh[[:space:]]+auth[[:space:]]+setup-git ]]; then
  deny "Blocked: gh auth setup-git enables git push via gh credentials. Run manually if needed."
fi

# gh pr write operations (view/list/diff/checks/status remain allowed)
if [[ "$command" =~ gh[[:space:]]+pr[[:space:]]+(create|merge|close|reopen|edit|review|ready|lock|unlock|comment) ]]; then
  deny "Blocked: gh pr create/merge/edit and other write operations must be run manually."
fi

# other common gh write entry points
if [[ "$command" =~ gh[[:space:]]+repo[[:space:]]+create ]]; then
  deny "Blocked: gh repo create must be run manually."
fi

if [[ "$command" =~ gh[[:space:]]+release[[:space:]]+create ]]; then
  deny "Blocked: gh release create must be run manually."
fi

if [[ "$command" =~ gh[[:space:]]+workflow[[:space:]]+run ]]; then
  deny "Blocked: gh workflow run must be run manually."
fi

echo '{"permission": "allow"}'
