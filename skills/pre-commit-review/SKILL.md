---
name: pre-commit-review
description: >-
  Pre-commit review gate that runs diff-scope-auditor, then test-scrutinizer
  plus the test suite, then Bugbot, applies in-scope fixes, and loops with
  hard caps until the gates pass or human intervention is required. Always
  ends with a one-line suggested commit message matching repo conventions.
  Use when the user asks to commit, create a git commit, or run pre-commit
  review / commit gate; also before opening a PR when they want the same
  gate. Do not commit until the gates are green or the user explicitly waives.
---

# Pre-commit review

Run this gate **before** creating a commit (or before a PR when the user asks for the same check). Subagents audit; **you** apply fixes. Do not implement auditor ticket-backlog items in this loop.

## Budget (hard)

- Max **2 full cycles** (auditor → fix → Bugbot → fix → …)
- Max **4** total subagent runs (**auditor + Bugbot combined**). Test-scrutinizer shards do **not** count against this 4.
- Test-scrutinizer + test suite run **once**, on the first pass only (after the first auditor, before the first Bugbot)
- Hit the cap without the gates green → **stop and ask the user** (see Escalation)

Track: `auditor_runs`, `bugbot_runs`, `cycle`.

## Pass criteria

**diff-scope-auditor passes** when:

- Verdict is **Approve as-is**, or **Approve with trims** with every **Critical** and **Should fix** resolved
- **Consider** items are optional — do not loop on them
- Ticket backlog is noted for the user, **not** implemented now

**test-scrutinizer passes** when:

- There were no added/changed tests, or
- Every **Critical** and **Should fix** on those tests is resolved (test-suite edits only)
- **Minor** items are optional — do not loop on them

**Test suite passes** when the project's tests covering the change exit 0, and — if the repo has a known coverage rule — tests were run **with coverage** and that threshold is **met**.

**Bugbot passes** when:

- No remaining **must-fix** findings that are in scope for the **original task**
- Findings that need redesign, new dependencies, or out-of-scope work → escalate (do not expand the diff to silence Bugbot)

**Gates green** = auditor + test-scrutinizer (if tests) + test suite + Bugbot pass with no further required changes → proceed to commit per the user's git commit rules.

## Scope anchor

Before any subagent:

1. Restate the **original user task / ticket** in 1–3 bullets (the scope anchor).
2. Snapshot rough diff size (`git status`, file count; optional line stats). Use later for loop detection.

If there is nothing to commit (clean tree / nothing staged that the user asked to commit), stop and say so.

## Flow

```text
User asks to commit (or pre-commit review)
  → scope anchor
  → diff-scope-auditor
  → fix only required auditor items (shrink/correct scope)
  → if Reject/redo or escalation triggers → human
  → test-scrutinizer over tests added (shard by file or test if large)
  → fix only Critical/Should-fix test-suite items
  → run the test suite (with coverage if the repo has a known coverage rule)
  → if tests fail or coverage is unmet after one in-scope fix → human
  → Bugbot
  → fix only in-scope must-fix bugs (smallest patch)
  → re-run auditor (catch Bugbot-driven bloat)
  → if needed, one more Bugbot pass
  → gates green → commit
  → else after budget → human
```

Do **not** re-run test-scrutinizer or the test suite on later auditor/Bugbot cycles unless you changed tests again to satisfy a must-fix — then re-run only the affected tests before the next Bugbot.

### 1. Run diff-scope-auditor

Launch the `**diff-scope-auditor**` custom subagent (`~/.cursor/agents/diff-scope-auditor.md`).

If it cannot be launched by name, start a `generalPurpose` Task whose prompt includes: the full contents/instructions of that agent file, the scope anchor, repo path, and a request to audit the current change set.

Prompt must include:

- Scope anchor (original task)
- Absolute repo root
- Whether to focus on uncommitted changes vs full branch diff (match what will be committed)

Instruct it to return its normal structured report (Verdict, Findings, Recommended trims, Ticket backlog, etc.).

### 2. Apply auditor fixes (parent only)

Do:

- Resolve **Critical** and **Should fix** (delete, condense, revert formatting, split only if still required for the same commit request)
- Leave **Consider** unless trivial and clearly helpful
- Record ticket backlog for the user — **do not** implement those items here

Do not:

- Add dependencies, drive-by refactors, or unrelated cleanups to “pass”
- Grow scope because the auditor suggested a larger rewrite unless Verdict is Reject/redo and the user approved that path

If Verdict is **Reject / redo with narrower approach**, either apply the **Minimal alternative approach** within budget or escalate.

### 3. Run test-scrutinizer (first pass only)

From the commit diff (same set as the scope snapshot), list **added or changed tests**: new test files, and new or modified test cases in existing test files.

- **None** → skip this step; still run the test suite (step 5)
- Do **not** review those tests in the parent. Identify paths/names from `git status` / `git diff` only, then launch Task.

**Shard if large** so each subagent sees a bounded target:

- **2+ test files** → one Task per file
- **One file that is still large** (roughly more than ~8 test functions/cases, or a large added-test hunk) → one Task per test, or per class/`describe` if that is the natural unit
- **Otherwise** → one Task covering the named added/changed tests

Launch shards in **parallel** (multiple Task calls in one message) when there is more than one.

Each Task:

- `subagent_type: "test-scrutinizer"`
- `description: "Test scrutinizer"` (or a short concrete title such as the file name)
- `run_in_background: false`

Prompt shape:

```text
Audit these tests. Produce the structured scrutinizer report only. Recommendations must be scoped to the test suite alone — do not recommend production-code changes. Do not implement fixes.

Explicitly look for obvious flakes: timing/race assumptions, uncontrolled randomness or clocks, order-dependent or shared mutable state, real network or external I/O, brittle polling/timeouts, and other patterns likely to pass locally but fail intermittently in CI.

Full Repository Path: <absolute repository path>
Target: named tests
Named tests:
<this shard's files, classes, or test names>
```

On failure: retry once (fix prompt shape; if `test-scrutinizer` is unregistered, once as `generalPurpose` whose prompt starts with the full contents of `~/.cursor/agents/test-scrutinizer.md`). If still failing → escalate. Tell the user a **Developer: Reload Window** (or restart Cursor) will register the subagent for later chats.

### 4. Apply scrutinizer fixes (parent only)

- Resolve **Critical** and **Should fix** with the **smallest** test-only edits
- Leave **Minor** unless trivial and clearly helpful
- Do **not** change production code to satisfy the scrutinizer
- Do **not** add large new test files or out-of-scope coverage; a small missing complementary case for behavior this diff already claims to lock down is in scope
- Ticket the rest for the user

### 5. Run the test suite (first pass only)

After scrutinizer (or immediately if there were no tests to audit), run the project's test suite covering the change.

- Use the repo's usual command (`package.json` `test`, `pytest`, `go test`, `cargo test`, `make test`, etc.)
- If the default is a huge monorepo run and the repo has a targeted command for the touched package/module, use that
- Do not invent a one-off subset the project does not use

**Coverage:** If the repo has a **known coverage rule**, tests **must** be run **with coverage**, and that threshold **must** be met.

- A known rule is a threshold or fail-under the project already defines — test config (`package.json` `coverageThreshold`, `pyproject.toml` / `pytest.ini` / `setup.cfg` `fail_under` / `--cov-fail-under`), CI, Makefile/script, Cursor rules, or `AGENTS.md`
- Use the project's coverage-enabled command; do **not** invent a tool or threshold the repo does not use
- If there is no such rule, a passing suite without coverage is enough

If the suite fails **or coverage is below the known rule**: apply **one** in-scope fix (smallest patch; same scope rules as Bugbot), then re-run **with coverage when a coverage rule applies**. Still red → escalate. Do not proceed to Bugbot with a failing suite or unmet coverage.

If there is no test runner / nothing to run, note that and continue to Bugbot.

### 6. Run Bugbot

Launch exactly one `bugbot` subagent:

- `run_in_background: false`
- `description: "Bugbot"`
- `subagent_type: "bugbot"`

Prompt shape:

```text
Full Repository Path: <absolute repository path>
Diff: <uncommitted changes | branch changes>
Custom Instructions: Pre-commit gate for this task: <scope anchor>. Only report real bugs/risks in scope for that task. Do not suggest refactors, formatting, or out-of-scope improvements.
```

Diff selection:

- Default `**uncommitted changes**` when committing the current working tree / staged set
- Use `**branch changes**` when related commits on this branch are part of the same task and should be reviewed together
- Omit `Base Branch` unless the branch was cut from a non-default base you know

On failure: retry once per the usual Bugbot rules (fix prompt shape; if diff cannot be computed, once with `Diff: natural language` + `Change Description`). If still failing → escalate.

### 7. Apply Bugbot fixes (parent only)

- Fix only **in-scope must-fix** issues with the **smallest** correct patch
- Prefer existing project patterns; no new libraries unless unavoidable for a real bug — if unavoidable, escalate
- After fixes, continue the loop (auditor again if budget remains)

### 8. Alternate until stable or budget

After Bugbot fixes, re-run auditor to catch bloat. Then Bugbot again only if needed and budget remains. Stop early when the gates pass with no required changes.

## Conflict precedence (auditor vs Bugbot)

1. **Correctness** wins over pure minimalism — keep the smallest fix that addresses a real Bugbot must-fix
2. **Scope** wins over polish — no features, deps, or refactors to clear either side
3. If Bugbot requires material new surface the auditor would reject → **escalate** with both summaries; do not expand
4. Test-scrutinizer must not expand production scope; test-only Critical/Should-fix edits may land even if they add a few cases

## Escalation (stop and ask the user)

Stop immediately when any of:

- Iteration / subagent budget exhausted
- Same finding returns after a supposed fix
- File count or diff size **grows** across auditor runs without a clear Bugbot correctness reason
- Auditor notes repetitive scope increase, or Verdict is **Reject / redo** and a narrow redo is unclear
- About to add a dependency, broad refactor, or unrelated modules to satisfy a finding
- Oscillation (e.g. auditor removes tests ↔ Bugbot demands them back)
- Bugbot / auditor / test-scrutinizer invocation fails twice
- Test suite still failing after one in-scope fix-and-rerun (including unmet coverage when a coverage rule applies)
- Satisfying a finding would violate the scope anchor

Escalation message (concise):

- Scope anchor
- What passed / failed
- Remaining findings (bullet list)
- Why you stopped (budget, loop, conflict, test failure, etc.)
- Options: waive and commit, apply a specific trim, open tickets, or redo narrowly

Then finish with [Commit message suggestion](#commit-message-suggestion-required--always-last) (required).

## After the gates are green

1. Briefly tell the user the gates passed (one short summary; mention any deferred ticket backlog).
2. Create the commit only if the user asked to commit — follow their git commit rules (status/diff/log, HEREDOC message, no push unless asked). Use the suggested commit message from the final step below when committing.
3. If they only asked for pre-commit review, stop after the summary — do not commit unless they ask.

Then finish with [Commit message suggestion](#commit-message-suggestion-required--always-last) (required).

## Waivers

If the user explicitly waives the gate (“skip review”, “commit anyway”), commit per their rules without further subagent loops. Note the waiver in one line. Note that this style of waiver waives this review but not other rules.

Then finish with [Commit message suggestion](#commit-message-suggestion-required--always-last) (required).

## Commit message suggestion (required — always last)

**Every** pre-commit review run must end with a suggested commit message — including when gates pass, when you escalate, when the user waives, and when they only asked for review (no commit). This is always the **final** thing in your response (after gate summary, escalation, or waiver note).

Skip only when there is nothing to commit (clean tree / nothing staged that the user asked to commit) — say so explicitly instead.

### How to draft the message

1. **Infer repo conventions** — run `git log --oneline -20` in the repo and match the prevailing format (prefix/tag style, separators, tense, casing, punctuation). Do not invent a format; replicate what recent commits use.
2. **Gather context** — `git diff` / `git status`, the scope anchor, branch name (extract issue/ticket key if present, e.g. `dev/IAM-8585-…`), and any Jira/issue key from the user or task. If the commit requires a ticket number and you do not know the ticket number ask.
3. **Write one line** summarizing the **why** of the change (not a file list). Imperative or past-tense should match recent commits in this repo.

### Rules

- **One line only** — no body, no bullets, no multi-line HEREDOC preview.
- **Match repo conventions** — same prefix pattern, ticket placement, dash/colon style, and description casing as `git log` shows for this repo.
- **Ticket key** — include it when the repo format requires it and you know the key (branch name, scope anchor, or user). If the repo always tags commits but the key is unknown, ask the user for the ticket number then rewrite the message.

### Output format

End the response with a short prose lead-in, then a **separate one-line fenced code block containing only the message** — nothing else inside the fence (no label, no prefix). The label must stay outside the code block so copy only grabs the commit line.

Example (note: the fence contains a single line and nothing else):

Suggested commit message:

```text
[IAM-8585] - Refactor Address onto IamPayloadModel with snake_case fields
```
