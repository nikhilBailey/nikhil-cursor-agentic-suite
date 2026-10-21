---
name: second-pass-screenshots
description: >-
  Skill-agnostic second-pass browser screenshots. Seed mode passes the stub
  contract into whatever document-producing skill is already being launched so
  that skill writes tags in the same run. Capture mode launches the
  second-pass-screenshot-taker subagent to fill pending stubs later. Use when
  the user asks to seed screenshot stubs, run a second pass for screenshots, or
  fill second-pass-screenshot tags. Do not apply capture launch if you are
  already the screenshot taker subagent.
disable-model-invocation: true
---

# Second-pass screenshots

Screenshots are **skill-agnostic**. Any skill that writes a document can receive the stub contract in its prompt. This skill does **not** replace that producer skill. It provides:

1. **Seed mode** — inject the contract into the producer's Task prompt (same subagent as the producer).
2. **Capture mode** — launch `second-pass-screenshot-taker` to fill stubs in an existing artifact.

If you are already running as `second-pass-screenshot-taker`, or your prompt contains "You are a **second-pass screenshot taker**", **stop**. Follow `~/.cursor/agents/second-pass-screenshot-taker.md` only. Do **not** call Task.

Read the full stub grammar from [stub-contract.md](stub-contract.md) when seeding or when explaining tags to the user.

## Seed mode

Use when the user asks to **seed** second-pass screenshot stubs **while** another skill is producing a document (Allure report, runbook, PR markdown, etc.). If they only want capture on an existing file, use Capture mode instead.

### Parent behavior

1. Identify the **producer skill** the user asked for. Follow that skill's launch exactly (`subagent_type`, required prompt shape, forbidden content).
2. Paste the **Producer obligations** and **Stub grammar** from [stub-contract.md](stub-contract.md) into the producer prompt:
   - If the producer skill has a free-text or extra-context slot, put the contract there.
   - Otherwise append the contract at the **end** of the required prompt without rewriting required sections.
3. Launch **one** Task for the producer. Do **not** launch a second subagent to insert tags.
4. Do **not** edit the producer skill file to add screenshot awareness.

### Injection example (extra-context slot)

When the producer uses a slot like `Extra context from the user (if any):`, fill it with:

```text
Second-pass screenshot seeding (required):

<paste Producer obligations + Stub grammar + Template from stub-contract.md>
```

Respect that producer's forbidden content (e.g. do not add precomputed verdicts or classifications the producer skill forbids in the parent prompt).

### After the producer returns

- Locate the written artifact (path from the subagent response or user context).
- If the user asked for stubs and the file contains no `second-pass-screenshot` comment, **resume the same producer subagent once** with the contract repeated more prominently. Still only one producer subagent at a time.
- Tell the user capture is a separate step: run this skill in **Capture mode** when ready.

## Capture mode

Use when the user asks to run the **second pass**, **take the seeded screenshots**, or **fill** `second-pass-screenshot` stubs. The producer skill is irrelevant; only the artifact path matters.

Your **first tool call** in capture mode must be Task (unless retrying after failure). Do not screenshot in the parent agent.

### Launch

Use the Task tool with:

- `subagent_type: "second-pass-screenshot-taker"`
- `description: "Second-pass screenshots"` (or a short concrete title)
- `run_in_background: false` unless the user explicitly asks to run in background
- `model`: non-fast. If the available subagent slugs include a fast/non-fast pair and the parent is the fast slug (for example `composer-2.5-fast`), pass the non-fast sibling (`composer-2.5`). Otherwise pass `inherit`. Never pass a `*-fast` slug unless the user asked for fast.

Prompt shape:

```text
Fill second-pass-screenshot stubs in the artifact below. Follow ~/.cursor/agents/second-pass-screenshot-taker.md and skills/second-pass-screenshots/stub-contract.md.

Artifact (absolute path):
<path to markdown file>

User options (if any):
<refresh captured stubs, specific stub ids only, stop on first failure, etc.>
```

### Parent-agent constraints (capture)

- Do **not** open the browser or take screenshots in the parent turn.
- After the subagent finishes, present the summary (captured vs blocked ids) and the artifact path.
- Surface **blocked** stubs and likely next steps (login, allowlist, fix `url`/`ready`/`selector`).

### Retries (capture)

- Bad invocation (wrong type, empty artifact path): correct once and retry.
- Other transient Task failures: retry once with the same prompt.
- If Task rejects `second-pass-screenshot-taker` as unknown/unregistered: retry **once** as `generalPurpose` whose prompt starts with the full contents of `~/.cursor/agents/second-pass-screenshot-taker.md`, then the prompt shape above. Tell the user a **Developer: Reload Window** (or restart Cursor) will register the subagent for later chats.
- If that fallback also fails, stop. Do not capture in the parent unless they explicitly ask you to proceed without the subagent.

## What this skill does not do

- Edit producer skills or agent protocols.
- Run capture automatically at the end of seed mode unless the user asked to run both steps in one request (then seed first, then capture).
- Camera photos, macOS window capture, or Playwright.
