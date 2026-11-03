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

Use when the user asks to **seed** second-pass screenshot stubs **while** another skill is producing a document (a report, a guide, pull-request markdown, or any other write-up). If they only want capture on an existing file, use Capture mode instead.

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

Respect that producer's forbidden content. Do not add material that skill tells the parent to keep out of the prompt.

### After the producer returns

- Locate the written artifact (path from the subagent response or user context).
- If the user asked for stubs and the file contains no fenced `text` block whose first line is `second-pass-screenshot`, **resume the same producer subagent once** with the contract repeated more prominently. HTML comments do not count; plan mode removes them on save. Still only one producer subagent at a time.
- Tell the user capture is a separate step: run this skill in **Capture mode** when ready.

## Capture mode

Use when the user asks to run the **second pass**, **take the seeded screenshots**, or **fill** `second-pass-screenshot` stubs. The producer skill is irrelevant; only the artifact path matters.

Your **first tool call** in capture mode must be Task (unless retrying after failure, or the user gave a replacement origin to write onto stub `url` lines first). Do not open the browser in the parent agent. That includes listing tabs, navigating, snapshotting, and waiting while the user finishes sign-in or MFA. Pass that wait as a user option; the taker reveals the page and polls.

### Launch

Use the Task tool with:

- `subagent_type: "second-pass-screenshot-taker"`
- `description: "Second-pass screenshots"` (or a short concrete title)
- `run_in_background: false` unless the user explicitly asks to run in background
- `model`: non-fast. If the available subagent slugs include a fast/non-fast pair and the parent is the fast slug (for example `composer-2.5-fast`), pass the non-fast sibling (`composer-2.5`). Otherwise pass `inherit`. Never pass a `*-fast` slug unless the user asked for fast.

Prompt shape:

Do not add a capture procedure to the prompt. The agent file is the procedure. User options are only the switches below.

```text
Fill second-pass-screenshot stubs in the artifact below. Follow the agent instructions you were given and skills/second-pass-screenshots/stub-contract.md.

Artifact (absolute path):
<path to markdown file>

User options:
- refresh captured: yes/no
- retry blocked: yes/no
- wait for sign-in or MFA: yes/no
- wait budget: <default four minutes, or what the user asked>
- ids: <all, or a list>
- stop on first failure: yes/no
- replacement origin: <only if the user gave an absolute origin; otherwise omit>
```

Set `retry blocked: yes` when the user asks to restart, retry, or continue after sign-in. Stubs already marked `blocked` are skipped otherwise, including stubs blocked only because sign-in was still up.

Set `wait for sign-in or MFA: yes` when the user says they are signing in or to wait. Do not start that wait in the parent.

If the user gives a different absolute origin, rewrite only the origin on stub `url` lines (keep each path) before launch. Do not crawl a repository for environment hosts, and do not open the browser to discover the host. If they name an environment but no origin, ask for the origin and stop.

### Parent-agent constraints (capture)

- Do **not** call browser tools in the parent turn.
- After the subagent finishes, present the summary (captured vs blocked ids, plus any `capture-note`) and the artifact path.
- The capture result is the PNG at each `image` path and the markdown image immediately after that fence. The fence stays. A preview that does not render local images is not a missing screenshot.
- Surface **blocked** stubs and likely next steps (finish sign-in in the browser pane, allowlist, fix `url`/`ready`/`selector`). A follow-up capture after sign-in uses `retry blocked: yes`.

### Retries (capture)

- Bad invocation (wrong type, empty artifact path): correct once and retry.
- Other transient Task failures: retry once with the same prompt.
- A user-requested restart is a new launch with the latest user options, not this one automatic retry.
- If Task rejects `second-pass-screenshot-taker` as unknown/unregistered: the agent file is not installed under `~/.cursor/agents/`. Read `agents/second-pass-screenshot-taker.md` from the suite that contains this skill (use `~/.cursor/agents/second-pass-screenshot-taker.md` only when that file exists). Retry **once** as `generalPurpose` whose prompt starts with those full contents, then the prompt shape above. Tell the user the named type registers after that file is copied into `~/.cursor/agents/` and they run **Developer: Reload Window**. A reload alone does nothing while the file is absent.
- If that fallback also fails, stop. Do not capture in the parent unless they explicitly ask you to proceed without the subagent.

## What this skill does not do

- Edit producer skills or agent protocols.
- Run capture automatically at the end of seed mode unless the user asked to run both steps in one request (then seed first, then capture).
- Remove stubs, publish the document, or copy figures into another file.
- Camera photos, macOS window capture, or Playwright.
