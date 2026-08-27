---
name: github-pull-request-markdown
description: >-
  Generate copy-paste GitHub pull request Markdown from an agentic chat that
  implemented a feature. Use when the user asks for a GitHub PR description,
  GitHub pull request markdown, PR body, PR summary/test plan from this chat,
  or wants text to paste into a GitHub pull request (github.com or GitHub
  Enterprise).
---

# GitHub pull request markdown

## When to use

Apply whenever the user wants **GitHub pull request markdown** — including "github PR", "PR body", "gh pr description", or "turn this work into a github pull request".

Primary use case: **distill an agentic chat that implemented a feature** into a reviewer-ready PR description (and optional title).

For creating the PR via `gh`, follow the user's creating-pull-requests rules; this skill only produces the Markdown body/title.

## Output rules (mandatory)

1. Put the **entire** PR body in **one** fenced code block for copy/paste.
2. Use language tag `markdown` on the outer fence. When the body contains fenced code blocks, wrap the deliverable in a **four-backtick** outer fence.
3. Prefer GitHub Flavored Markdown (GFM). Use HTML only for GitHub-supported constructs (`<details>`, `<summary>`, `<kbd>`, `<br>`). No scripts, styles, or arbitrary tags.
4. A one-line intro is fine; the copy-paste block is the deliverable.
5. Always offer a **PR title** outside the block (plain text, one line). Include a GitHub issue (`#123`) or Jira key when known.
6. Keep the description **review-oriented** — what changed, why, how to verify. Not a chat transcript or ticket repro write-up.

## Writing rules

- **One fact, one place** — Summary states what shipped and why; Changes lists specifics. Do not preview every bullet in Summary.
- **Bullets over paragraphs** — Summary: 1–2 sentences. Changes: one line per item.
- **Omit empty sections** — no filler, no boilerplate checklists.
- **Word budget** — Test plan: 3–6 checkboxes. Follow-ups: max 2 bullets.

## Extraction (follow silently — do not print these steps)

1. **Diff story** — concrete behaviors, APIs, UI, configs touched; group by area if large.
2. **No chat noise** — no tool logs, false starts, or agent narration.
3. **Align with git** — when context exists, match bullets to the actual diff; do not invent files, issue numbers, or ticket IDs.

## GitHub Markdown (GFM)

Use GitHub Flavored Markdown — **not** Jira wiki (`h2.`, `{code}`, `{{inline}}`) and **not** Bitbucket-only macros.

### Core

- Headings: `## Section`
- Code: fenced \`\`\`lang blocks or `` `inline` ``
- Links: `[text](url)`
- Task lists (interactive in PR bodies): `- [ ]` / `- [x]`
- Emphasis: `**bold**`, `_italic_`, `~~strikethrough~~`
- Tables: standard GFM pipe tables when a grid is clearer than bullets

### GitHub-only (use when useful)

**Issue / PR references** — autolink with `#123` (same repo) or `owner/repo#123` (cross-repo). Do not invent numbers.

**Closing keywords** — only when the user wants the PR to close an issue **and** the issue number is known. Put on their own line in Summary (or a short closing line at the end):

```markdown
Closes #123
```

Also valid: `Fixes #123`, `Resolves #123` (and close/fix/resolve variants). Cross-repo: `Fixes owner/repo#100`. Multiple: one keyword per issue (`Closes #10, closes #11`).

Keywords apply only when the PR targets the repository **default branch**. Do not add closing keywords "just in case."

**Mentions** — `@username` or `@org/team` only when the user asked to request review or notify someone. Do not invent handles.

**Alerts** — sparingly (0–1 per PR), for something reviewers must not miss:

```markdown
> [!NOTE]
> Useful context when skimming.

> [!WARNING]
> Breaking change or required manual step.
```

Types: `NOTE`, `TIP`, `IMPORTANT`, `WARNING`, `CAUTION`. Do not nest alerts or stack several in a row.

**Collapsed detail** — for long logs, large file lists, or optional deep-dives:

```markdown
<details>
<summary>Implementation notes</summary>

- Detail one
- Detail two

</details>
```

Blank line after `<summary>` so inner Markdown renders. Prefer this over dumping walls of text in Changes.

**Keyboard** — `<kbd>Ctrl</kbd>+<kbd>S</kbd>` for shortcut callouts in test steps.

### Do not

- Invent reviewers, issue numbers, compare URLs, or CI badge links.
- Put closing keywords inside negated or quoted prose ("does not fix #9") — GitHub may still link/close.
- Rely on raw HTML beyond the tags above.

## Default sections

Include what fits; omit the rest. Prefer this order:

```markdown
## Summary
<!-- 1–2 sentences: what + why. Issue/Jira once if known. Closing keyword on its own line if intentional. -->

## Changes
<!-- One line per change; sub-bullets only for file areas or non-obvious tradeoffs -->

## Test plan
- [ ] ...
<!-- 3–6 checkboxes; user-visible flows a human can run in <10 min -->

## Follow-ups
<!-- Optional; max 2 bullets -->
```

Do **not** include Risk/impact, Design notes, Checklist, or Out of scope as separate sections unless the user explicitly asks. Fold non-obvious decisions into Changes as sub-bullets (or a single `<details>` block).

### Title (outside the fence)

Imperative, specific, ≤ ~70–90 characters when practical.

Patterns:

- `Add domain conflict check before verify`
- `#123: Add domain conflict check before verify`
- `KEY-123: Add domain conflict check before verify`

## Example response shape

Brief intro (optional) + plain-text **Title:** line, then:

````markdown
## Summary
OIDC auth replaces legacy wiring so the portal can sign in via the IdP.

Closes #1842

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
