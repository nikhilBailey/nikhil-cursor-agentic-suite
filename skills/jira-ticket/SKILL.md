---
name: jira-ticket
description: >-
  Generate copy-paste Jira wiki markup for bug/feature tickets. Use when the user
  asks for a Jira ticket, Jira markdown, Jira description, ticket draft, or
  wants issue text to paste into Jira. Applies Jira wiki syntax and safe
  Cursor codeblock wrapping.
---

# Jira ticket markdown

## When to use

Apply whenever the user wants ticket text for Jira — even if they only say "jira ticket" or "track this in jira".

## Output rules (mandatory)

1. Put the **entire** Jira body in **one** fenced code block (`text` tag on the outer fence).
2. **Never** put triple backticks inside the Jira body — use `{code}` / `{code:lang}` instead.
3. Do not wrap the block in extra prose unless the user asked for a title separately. A one-line intro is fine.
4. If the user only needs a **summary/title**, give that outside the block; offer the full description in the block when useful.

## Writing rules

- **One fact, one place** — do not restate the title or summary in the body.
- **Bullets over paragraphs** — default to short bullets; one sentence only when context is required.
- **Omit empty sections** — if a section would be thin or duplicate another, leave it out.
- **Word budget** — What: ≤ 2 sentences. Done when: 2–4 checkboxes. Each bullet: ≤ 1 line.

## Jira wiki syntax (not GitHub markdown)

| Element | Syntax |
|---------|--------|
| Heading | `h2. Section` |
| Bold | `*bold*` |
| Bullet list | `*` at line start |
| Numbered list | `#` at line start |
| Code block | `{code:lang}` ... `{code}` |
| Inline code | `{{like_this}}` |

Do **not** use `# Heading`, `**bold**`, or GitHub-style fenced code inside the Jira body.

## Default sections

Include what fits; omit the rest.

| Section | When | Content |
|---------|------|---------|
| **What** | Always | Symptom or goal — ≤ 2 sentences |
| **Environment** | When it matters | Prod/staging, service, version |
| **Repro** | Bugs | Numbered steps (`#`) |
| **Cause & fix** | When known | One bullet each for cause and fix |
| **Done when** | Always | 2–4 testable checkboxes |

Do **not** include Impact, suggested labels, priority, or a catch-all Notes section unless the user explicitly asks.

## Example response shape

Brief intro (optional), then:

```text
h2. What
Login fails after KMS encrypt fallback returns null.

h2. Repro
# Sign in with a key that triggers fallback encrypt
# Observe 500 on /api/session

h2. Cause & fix
* Cause: {{CiphertextBlob}} not checked before use
* Fix: Guard null and surface a clear error

h2. Done when
* Fallback path returns 4xx with message, not 500
* Existing happy-path login unchanged
```
