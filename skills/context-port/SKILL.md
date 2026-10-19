---
name: context-port
description: >-
  Port context from a prior Cursor chat by launching the context-port subagent.
  Use when the user says port context from, rotate context, or cites a
  transcript uuid, [title](uuid) link, jsonl path, or shared-chat URL. The
  subagent reads the old transcript and returns a minimal NOW/NEXT/KEEP/OPEN
  brief so this chat stays clean. Best in a new chat; cannot erase history
  already in the current thread.
---

# Context port

When the user wants context ported from another chat, **do not read the transcript in the parent agent**. Your **first tool call** must be the Task launch below.

A port in a **new** chat keeps the parent clean. Invoking inside a long chat still leaves that history in place.

## Launch

Use the Task tool with:

- `subagent_type: "context-port"`
- `description: "Context port"` (or a short concrete title)
- `run_in_background: false` unless the user explicitly asks to run in background
- `model`: `inherit`, unless your slug ends in `-fast`, then use the listed non-fast sibling (e.g. `composer-2.5`)

Pass everything the user gave in the Task `prompt`. Include the absolute path:

`~/.cursor/skills/context-port/scripts/extract_transcript.py`

(expand `~` to the user’s home directory in the prompt)

Prompt shape:

```text
Port context from this prior chat. Return only the minimal brief—do not implement.

Extract script: <absolute path to extract_transcript.py>

Transcript reference:
<uuid, [title](uuid), path to .jsonl, and/or shared-chat URL the user provided>

Focus (optional):
<phrase if the user narrowed scope; otherwise omit>

Extra from user (optional):
<any other instruction in the user message>
```

## After the subagent returns

- If the reply is `UNREAD: …`, relay that line and **stop**. Do not read the transcript yourself unless the user explicitly asks you to proceed without the subagent.
- Otherwise **do not quote or expand** the brief.
- If the user **only** asked to port: perform `NEXT`. If `NEXT` is `wait`, say in one line what you are ready to continue, then stop.
- If the user **also** gave a next task in the same message, that instruction wins; still honor `KEEP` and `OPEN`.

## Parent-agent constraints

- Do **not** Grep/Read/Glob the transcript JSONL or run the extractor in the parent turn before or instead of Task.
- Do **not** substitute `explore` / parent summarization when `context-port` is available—except the fallback below.
- Do **not** restate the old chat chronology in your reply.

## Retries

- Bad invocation (wrong type, empty prompt): correct once and retry.
- Other transient Task failures: retry once with the same prompt.
- If Task rejects `context-port` as unknown/unregistered: retry **once** as `generalPurpose` whose prompt starts with the full contents of `~/.cursor/agents/context-port.md`, then the prompt shape above. Tell the user **Developer: Reload Window** (or restart Cursor) registers the subagent for later chats.
- If that fallback also fails, stop. Do not read the transcript in the parent unless they explicitly ask you to proceed without the subagent.
