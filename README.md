# Nikhil Cursor Agentic Suite

Private backup of user-level Cursor hooks, skills, subagents, and related
config from `~/.cursor`. Restore this onto a new machine if the laptop dies.

Remote: `git@github.com:nikhilbailey/nikhil-cursor-agentic-suite.git`

## History

This project was theory-crafted during my last 2 years at CU Boulder. As AI evolved, the ability to run a complex suite of agents tailored to an individual contributor's personal preferences became possible. This is my personal suite tailored to how I code, and I am happy to share it with the world.

Any code or references specific to a workplace or project are omitted from this repo. These are stored in local workplace-specific folders and are available at the request of the organization that owns that folder.

## Workplace adapters

Committed skills under `skills/` stay **workplace-agnostic**. Each employer plugs in locally under `workplace-specific/<id>/` (gitignored except `.gitkeep`). No script in this repo hard-codes an employer id.

### Layout

| Path | Role |
| --- | --- |
| `workplace-specific/<id>/adapter.json` | Optional manifest: where skills, agents, references, and hooks live |
| `workplace-specific/<id>/<skill>/SKILL.md` | Legacy flat skill (no adapter required) |
| `workplace-specific/<id>/hooks/first-party.json` | Optional library gate policy (at most one workplace may supply this) |

`adapter.json` may set `root` to a directory outside this repo (for example a clone of an internal toolkit). Paths in the manifest are relative to `root`, or to the adapter file when `root` is omitted.

### `adapter.json` contract

```json
{
  "root": "/path/to/external/toolkit",
  "user": {
    "skillGlobs": ["skills/*/*"],
    "agentGlobs": ["cursor/*/agents/*.md"]
  },
  "project": {
    "skillGlobs": ["skills/*/*"],
    "agentGlobs": ["cursor/*/agents/*.md"],
    "referenceGlobs": ["skills/*/references/**"],
    "ruleGlobs": ["cursor/*/rules/*.mdc"]
  },
  "hooks": {
    "firstParty": "hooks/first-party.json"
  }
}
```

- **user.*** — `restore.sh` symlinks matching skills and agents into `~/.cursor/` beside your personal skills. Skill globs match directories that contain `SKILL.md`; the symlink name is that directory’s basename.
- **project.*** — not applied by restore. Run `./scripts/link-project-adapters.sh /path/to/work/repo` to symlink skills, agents, references, and rules into that repo’s `.cursor/`. The linker refuses this suite repo as a target.
- **hooks.firstParty** — copied to `~/.cursor/hooks/first-party.json` during restore. Only one workplace may define a policy (including a legacy `hooks/first-party.json` file).

Collisions (two workplaces or an adapter vs a committed skill name) fail restore with an error instead of overwriting.

### Commands

```bash
./scripts/restore.sh
./scripts/link-project-adapters.sh /path/to/work/repo
./scripts/backup.sh
```

`backup.sh` skips symlinks under `~/.cursor/skills`, `agents`, and `rules`, and does not follow symlinks into `workplace-specific/`, so employer toolkit files are not copied into the committed tree.

### Example: new employer `acme`

On disk only (nothing to commit except the existing `workplace-specific/acme/.gitkeep`):

1. Add `workplace-specific/acme/adapter.json` pointing at your local Acme toolkit clone.
2. Optionally add `workplace-specific/acme/my-skill/SKILL.md` for a one-off skill without an external root.
3. Run `./scripts/restore.sh`, then link a work repo if the toolkit expects project-level `.cursor/` paths.

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
| `rules/*.mdc` | `~/.cursor/rules/` (always-apply user rules) |

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
git clone git@github.com:nikhilbailey/nikhil-cursor-agentic-suite.git
cd nikhil-cursor-agentic-suite
./scripts/restore.sh
```

Then:

1. Copy `mcp.json.example` to `~/.cursor/mcp.json` if needed and fill in secrets.
2. Paste rules from `rules/user-rules.md` into Cursor Settings → Rules.
   (`backup.sh` does not refresh that file; edit it when Settings rules change.)
   Always-apply `*.mdc` rules restore into `~/.cursor/rules/`.
3. Restart Cursor.

## Secrets

Do not commit live `mcp.json`. The backup script redacts keys whose names look
like tokens, secrets, passwords, or credentials.

## License

All resources in this repository were created and are owned by Nikhil Bailey.
They are licensed under the [MIT License](LICENSE).
