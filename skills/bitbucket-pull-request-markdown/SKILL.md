---
name: bitbucket-pull-request-markdown
description: >-
  Generate copy-paste Bitbucket pull request Markdown from an agentic chat that
  implemented a feature. Use when the user asks for a Bitbucket PR description,
  Bitbucket pull request markdown, PR body, PR summary/test plan from this chat,
  or wants text to paste into a Bitbucket Cloud or Data Center pull request.
---

# Bitbucket pull request markdown

## When to use

Apply whenever the user wants **Bitbucket pull request markdown** — including "bitbucket PR", "PR body", or "turn this work into a bitbucket pull request".

Primary use case: **distill an agentic chat that implemented a feature** into a reviewer-ready PR description (and optional title).

## Output rules (mandatory)

1. Put the **entire** PR body in **one** fenced code block for copy/paste.
2. Use language tag `markdown` on the outer fence. When the body contains fenced code blocks, wrap the deliverable in a **four-backtick** outer fence.
3. No arbitrary HTML — Bitbucket escapes it.
4. A one-line intro is fine; the copy-paste block is the deliverable.
5. Always offer a **PR title** outside the block (plain text, one line). Include a Jira key when known (`TRID-11888: Short imperative summary`).
6. Keep the description **review-oriented** — what changed, why, how to verify. Not a chat transcript or ticket repro write-up.

## Writing rules

- **One fact, one place** — Summary states what shipped and why; Changes lists specifics. Do not preview every bullet in Summary.
- **Bullets over paragraphs** — Summary: 1–2 sentences. Changes: one line per item.
- **Omit empty sections** — no filler, no boilerplate checklists.
- **Word budget** — Test plan: 3–6 checkboxes. Follow-ups: max 2 bullets.

## Extraction (follow silently — do not print these steps)

1. **Diff story** — concrete behaviors, APIs, UI, configs touched; group by area if large.
2. **No chat noise** — no tool logs, false starts, or agent narration.
3. **Align with git** — when context exists, match bullets to the actual diff; do not invent files or ticket IDs.

## Bitbucket Markdown

Use GitHub-flavored Markdown — **not** Jira wiki (`h2.`, `{code}`, `{{inline}}`).

- Headings: `## Section`
- Code: fenced \`\`\`lang blocks or `` `inline` ``
- Links: `[text](url)`
- Task lists: `- [ ]` / `- [x]`

Put the Jira key in the title and first line of Summary when known. Do not invent reviewers, build URLs, or ticket IDs.

## Default sections

Include what fits; omit the rest. Prefer this order:

```markdown
## Summary
<!-- 1–2 sentences: what + why. Jira key once if known. -->

## Changes
<!-- One line per change; sub-bullets only for file areas or non-obvious tradeoffs -->

## Test plan
- [ ] ...
<!-- 3–6 checkboxes; user-visible flows a human can run in <10 min -->

## Follow-ups
<!-- Optional; max 2 bullets -->
```

Do **not** include Risk/impact, Design notes, Checklist, or Out of scope as separate sections unless the user explicitly asks. Fold non-obvious decisions into Changes as sub-bullets.

### Title (outside the fence)

Imperative, specific, ≤ ~70–90 characters when practical.

Pattern: `KEY-123: Add domain conflict check before verify`

## Example response shape

Brief intro (optional) + plain-text **Title:** line, then:

````markdown
## Summary
TRID-11888: OIDC auth replaces legacy wiring so the portal can sign in via Trimble Identity.

## Changes
- Add AuthProvider, callback, and logout routes under `src/auth/`
- Bootstrap protected routes through new client config
- Stage-specific OIDC env vars

## Test plan
- [ ] Local login → IdP → `/callback` → home
- [ ] Logout clears session
- [ ] Staging env keys match IdP registration

## Follow-ups
- Token refresh UX
````

(Use a four-backtick `markdown` outer fence when the body contains code fences; three backticks when it does not.)
