---
name: relevant-tests-selector
description: >-
  Select and run automation/regression tests influenced by the current code
  via the relevant-tests-selector subagent. The subagent picks tests and
  returns commands; this skill runs them and reports pass/fail counts. Use
  when the user asks to run relevant tests, automation/regression sanity
  checks, or when pre-commit review needs post-gate test verification.
---

# Relevant tests selector

When relevant automation/regression tests should run, **do not select tests or draft commands in the parent agent**. Your **first tool call** must be the Task launch below. Do not Grep, Read, Glob, or Shell the codebase first.

## Launch

Use the Task tool with:

- `subagent_type: "relevant-tests-selector"`
- `description: "Relevant tests selector"` (or a short concrete title)
- `run_in_background: false` unless the user explicitly asks to run in background

Pass the diff basis and any context in the Task `prompt`. Include the absolute workspace/repository path when known.

Prompt shape:

```text
Select automation and regression tests influenced by the current code change. Produce the structured selector report with runnable commands only. Do not run tests.

Full Repository Path: <absolute repository path if known>

Diff basis: <uncommitted changes | branch changes>

Scope anchor (if any):
<original task / ticket in 1–3 bullets>

Extra context from the user (if any):
<optional>
```

### Diff basis selection

- Committing current working tree / staged set → `uncommitted changes`
- Branch commits are part of the same task → `branch changes`
- Unspecified → `uncommitted changes` if local dirty work; otherwise `branch changes`

## Parent-agent constraints

- Do **not** pick tests, draft commands, or read test docs in the parent turn before or instead of Task.
- After the subagent finishes, **run each command** from the report exactly as specified.
- Do **not** rewrite commands, re-pick tests, or add commands the subagent did not emit.
- Do **not** auto-fix failing tests unless the user explicitly asks for that next step.

## Run commands

For each numbered command in the subagent report:

1. `cd` to the specified `cwd` (use Shell `working_directory` when supported).
2. Run the `command` via Shell.
3. Pass `required_permissions` when the report says `all`; otherwise use default sandbox.
4. Set `block_until_ms` to the report value (or at least `120000` if missing).
5. Wait for completion before starting the next command unless the user asked for parallel runs.

If **Nothing to run: yes**, skip Shell runs. Report that no relevant automation/regression tests were identified.

## Parse results

After all commands finish, extract pass/fail counts:

- **pytest**: parse summary line (`N passed`, `M failed`, `X error`)
- **jest / vitest**: parse `Tests:` or `Test Suites:` summary
- **go test**: parse `PASS` / `FAIL` and package counts
- **npm/pnpm/yarn test**: parse the runner's final summary when present
- **No parseable summary**: non-zero exit → at least 1 failed; zero exit → treat as passed (note that counts are unknown)

Report per command when there is more than one, then **totals**: `N passed, M failed`.

If a command could not run (missing deps, connection refused, permission error), count it as failed and include the error in the summary.

## Output to the user

Present:

1. The subagent's **Selection** and **Command source** (brief)
2. Each command label and outcome (passed/failed/error + counts when known)
3. **Totals: N passed, M failed**
4. If anything failed, list failing test names or error snippets when the runner output includes them

When invoked from **pre-commit review**, return the counts to the caller; pre-commit decides escalation. Do not commit.

When invoked standalone, stop after the summary unless the user asks to investigate failures.

## Retries

- Bad invocation (wrong type, empty prompt): correct once and retry.
- Other transient Task failures: retry once with the same prompt.
- If Task rejects `relevant-tests-selector` as unknown/unregistered: retry **once** as `generalPurpose` whose prompt starts with the full contents of `~/.cursor/agents/relevant-tests-selector.md`, then the prompt shape above. Tell the user a **Developer: Reload Window** (or restart Cursor) will register the subagent for later chats.
- If that fallback also fails, stop. Do not select tests in the parent unless they explicitly ask you to proceed without the subagent.
