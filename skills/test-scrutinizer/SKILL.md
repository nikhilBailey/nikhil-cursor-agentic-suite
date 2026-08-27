---
name: test-scrutinizer
description: >-
  Quick-audit agentic tests via the test-scrutinizer subagent. Reviews named
  tests, tests in the current diff, or tests in the most recent pull request
  for robustness, flakiness, positive and negative cases, path coverage,
  importable constants, and redundancy or split issues. Recommendations are
  scoped to the test suite only. Use when the user asks to scrutinize tests, audit
  tests, review test quality, check AI-written tests, or run test-scrutinizer.
---

# Test scrutinizer

When the user wants tests audited, **do not review tests in the parent agent**. Your **first tool call** must be the Task launch below. Do not Grep, Read, Glob, or Shell the codebase first.

## Launch

Use the Task tool with:

- `subagent_type: "test-scrutinizer"`
- `description: "Test scrutinizer"` (or a short concrete title)
- `run_in_background: false` unless the user explicitly asks to run in background

Pass the target and any user notes in the Task `prompt`. Include the absolute workspace/repository path when known.

Prompt shape:

```text
Audit these tests. Produce the structured scrutinizer report only. Recommendations must be scoped to the test suite alone — do not recommend production-code changes. Do not implement fixes.

Explicitly look for obvious flakes: timing/race assumptions, uncontrolled randomness or clocks, order-dependent or shared mutable state, real network or external I/O, brittle polling/timeouts, and other patterns likely to pass locally but fail intermittently in CI.

Full Repository Path: <absolute repository path if known>

Target: <one of: named tests | current diff | most recent pull request>
Named tests (only if Target is named tests):
<files, classes, or test names the user pointed at>

Extra context from the user (if any):
<optional>
```

### Target selection

- User named files / classes / tests → `named tests` and list them.
- User said current diff, uncommitted, staged, or dirty → `current diff`.
- User said PR, pull request, or most recent PR → `most recent pull request`.
- Unspecified → `current diff` if they have been talking about local/uncommitted work; otherwise `most recent pull request`.

## Parent-agent constraints

- Do **not** implement, edit test files, or draft a rewrite yourself.
- Do **not** Grep/Read/Glob/Shell the product or test codebase in the parent turn before or instead of Task.
- Do **not** expand the audit into a production-code review.
- After the subagent finishes, present its report. Prefer the subagent's structure; do not rewrite it into an implementation plan.
- Do **not** apply findings unless the user explicitly asks for that next step.

## Retries

- Bad invocation (wrong type, empty prompt): correct once and retry.
- Other transient Task failures: retry once with the same prompt.
- If Task rejects `test-scrutinizer` as unknown/unregistered: retry **once** as `generalPurpose` whose prompt starts with the full contents of `~/.cursor/agents/test-scrutinizer.md`, then the prompt shape above. Tell the user a **Developer: Reload Window** (or restart Cursor) will register the subagent for later chats.
- If that fallback also fails, stop. Do not audit in the parent unless they explicitly ask you to proceed without the subagent.
