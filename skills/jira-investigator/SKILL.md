---
name: jira-investigator
description: >-
  Investigate a Jira ticket by launching the jira-investigator subagent for a
  read-only codebase report (files of interest, potential causes, cautions,
  clarifying questions). Use when the user pastes a Jira ticket, ticket key,
  summary/description, or asks to investigate / triage a ticket. Do not
  implement or plan fixes in the parent agent—delegate and return the report.
---

# Jira investigator

When the user wants a Jira ticket investigated, **do not investigate in the parent agent**. Your **first tool call** must be the Task launch below. Do not Grep, Read, Glob, or Shell the codebase first.

## Launch

Use the Task tool with:

- `subagent_type: "jira-investigator"`
- `description: "Jira ticket investigation"` (or a short concrete title)
- `run_in_background: false` unless the user explicitly asks to run in background

Pass the full ticket material in the Task `prompt`. Include everything the user provided: key, summary, description, comments, links, environment, reproduction steps, and any constraints. Also include the absolute workspace/repository path when known.

Prompt shape:

```text
Investigate this Jira ticket read-only. Produce the structured investigation report only—do not implement or plan fixes.

Full Repository Path: <absolute repository path if known>

Ticket:
<paste the full ticket summary/description/comments/links the user provided>

Extra context from the user (if any):
<optional>
```

## Parent-agent constraints

- Do **not** implement, edit files, or draft a fix plan yourself.
- Do **not** Grep/Read/Glob/Shell the product codebase in the parent turn before or instead of Task.
- Do **not** substitute `explore` / `generalPurpose` / parent investigation when `jira-investigator` fails or is missing.
- If Task rejects `jira-investigator` as unknown/unregistered, **stop immediately**. Tell the user verbatim that the subagent is not registered in this window's session catalog (often a stale subagent cache) and ask them to **Developer: Reload Window** (or restart Cursor), then retry in a new chat. Do not investigate yourself unless they explicitly ask you to proceed without the subagent.
- After the subagent finishes, present its report. Prefer the subagent's structure; do not rewrite it into an implementation plan.
- Surface the consolidated follow-ups / clarifying questions prominently.

## Retries

- Bad invocation (wrong type, empty prompt): correct once and retry.
- Other transient Task failures: retry once with the same prompt.
- Unknown/unregistered `jira-investigator`: do **not** retry with a different subagent type; stop per the constraints above.
