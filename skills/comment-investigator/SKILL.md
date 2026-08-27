---
name: comment-investigator
description: >-
  Investigate a code-review comment via the comment-investigator subagent.
  Accepts a link, id, or pasted text; reads cited code read-only; recommends
  one action to take or consider: correct a misunderstanding, follow-up
  ticket, nice-to-have now, readability/bug fix, or ask the commenter for
  clarification. Use when the user pastes comment feedback or asks to
  triage/investigate a comment.
---

# Comment investigator

When the user wants a comment investigated, **do not investigate in the parent agent**. Your **first tool call** must be the Task launch below. Do not Grep, Read, Glob, or Shell the codebase first.

## Launch

Use the Task tool with:

- `subagent_type: "comment-investigator"`
- `description: "Comment investigation"` (or a short concrete title)
- `run_in_background: false` unless the user explicitly asks to run in background

Pass everything the user provided in the Task `prompt`. Include the absolute workspace/repository path when known.

Prompt shape:

```text
Investigate this comment read-only. Produce the structured investigator report only—pick one recommendation and one action to take or consider. Do not implement or plan fixes.

Full Repository Path: <absolute repository path if known>

Comment source (one or more):
<comment URL, comment id, or pasted comment with author/body/file/line>

Extra context from the user (if any):
<optional — e.g. "change is already huge", "I think they're wrong about X">
```

### What to pass

- **URL**: full link including `#r…` or `#discussion_r…` when available.
- **Pasted comment**: include author, body, file path, and line if available.
- **Change context**: branch name, ticket id, or diff notes if the user mentioned them.

Do **not** pre-fetch the comment in the parent agent unless Task fails and the user explicitly asks you to proceed without the subagent.

## Parent-agent constraints

- Do **not** implement, edit files, or draft a fix plan yourself.
- Do **not** Grep/Read/Glob/Shell the product codebase in the parent turn before or instead of Task.
- Do **not** substitute `explore` / `generalPurpose` / parent investigation when `comment-investigator` fails or is missing—except the fallback below.
- After the subagent finishes, present its report. Prefer the subagent's structure; do not rewrite it into an implementation plan.
- Surface **Recommendation** and **Action to take or consider** prominently.

## Retries

- Bad invocation (wrong type, empty prompt): correct once and retry.
- Other transient Task failures: retry once with the same prompt.
- If Task rejects `comment-investigator` as unknown/unregistered: retry **once** as `generalPurpose` whose prompt starts with the full contents of `~/.cursor/agents/comment-investigator.md`, then the prompt shape above. Tell the user a **Developer: Reload Window** (or restart Cursor) will register the subagent for later chats.
- If that fallback also fails, stop. Do not investigate in the parent unless they explicitly ask you to proceed without the subagent.
