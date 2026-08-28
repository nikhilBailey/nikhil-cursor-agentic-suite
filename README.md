# Nikhil Cursor Agentic Suite

Private backup of user-level Cursor hooks, skills, subagents, and related
config from `~/.cursor`. Restore this onto a new machine if the laptop dies.

Remote: `git@github.com:nikhilbailey-trimble/nikhil-cursor-agentic-suite.git`

## What is stored

| Path | Source |
| --- | --- |
| `agents/` | `~/.cursor/agents/` (user subagents) |
| `hooks/` + `hooks.json` | `~/.cursor/hooks/` and `hooks.json` |
| `skills/` | `~/.cursor/skills/` (user skills) |
| `permissions.json` | `~/.cursor/permissions.json` |
| `LICENSE` | `~/.cursor/LICENSE` |
| `mcp.json.example` | Redacted copy of `~/.cursor/mcp.json` |
| `rules/user-rules.md` | Cursor Settings → Rules (user scope; not refreshed by `backup.sh`) |

Layout matches `~/.cursor` so restore is a straight copy.

## What is not stored

These live under `~/.cursor` but are machine-local, Cursor-managed, huge, or secret:

- `mcp.json` — contains API tokens; only the redacted example is committed
- `projects/` — per-workspace caches, transcripts, terminals
- `extensions/` — reinstall from Cursor
- `skills-cursor/` — built-in skills Cursor syncs itself
- `plugins/cache/` — plugin cache
- `plans/`, `ai-tracking/`, `ide_state.json`, `argv.json`, `blocklist`

Editor settings and keybindings live in
`~/Library/Application Support/Cursor/User/` (not this repo).

## Backup (after you change hooks/skills/agents)

From this repo:

```bash
./scripts/backup.sh
```

Then snapshot and upload from your own terminal. Agent shells are blocked from
writing git remotes by `hooks/block-git-writes.sh`.

## Restore (new laptop)

```bash
git clone git@github.com:nikhilbailey-trimble/nikhil-cursor-agentic-suite.git
cd nikhil-cursor-agentic-suite
./scripts/restore.sh
```

Then:

1. Copy `mcp.json.example` to `~/.cursor/mcp.json` if needed and fill in secrets.
2. Paste rules from `rules/user-rules.md` into Cursor Settings → Rules.
   (`backup.sh` does not refresh that file; edit it when Settings rules change.)
3. Restart Cursor.

## Secrets

Do not commit live `mcp.json`. The backup script redacts keys whose names look
like tokens, secrets, passwords, or credentials.

## License

All resources in this repository were created and are owned by Nikhil Bailey.
They are licensed under the [MIT License](LICENSE).
