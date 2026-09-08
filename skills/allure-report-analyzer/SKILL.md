---
name: allure-report-analyzer
description: >-
  Download and analyze Allure test reports via the allure-report-analyzer
  subagent. Accepts GitHub Actions run IDs, artifact URLs, local zips, or
  allure-results directories. Emits two separate reports — suite health
  (target only) and PR delta vs baseline — with red-flag checklist and
  parameterized test identity. Use when the user asks to analyze Allure
  reports, compare test runs, investigate CI failures, or run
  allure-report-analyzer.
---

# Allure report analyzer

When the user wants Allure reports analyzed, **do not analyze in the parent agent**. Your **first tool call** must be the Task launch below. Do not Grep, Read, Glob, or Shell the codebase first.

## Launch

Use the Task tool with:

- `subagent_type: "allure-report-analyzer"`
- `description: "Allure report analysis"` (or a short concrete title)
- `run_in_background: false` unless the user explicitly asks to run in background

Pass **only** what the user provided in the Task `prompt`. Include the absolute workspace/repository path when known.

Prompt shape:

```text
Analyze Allure test results. Produce Report A (suite health) and Report B (PR delta) as specified in the subagent protocol. Do not emit Safe to Merge YES.

Full Repository Path: <absolute repository path if known>

Inputs (verbatim from user — do not add counts, classifications, or verdicts):
<GitHub run ID(s), artifact URL(s), local zip/path(s), PR number, or other context>

Extra context from the user (if any):
<optional>
```

### What to pass

- **GitHub run ID**: pass the number only; do not pre-download artifacts.
- **Artifact URL**: pass the full URL.
- **Local path**: pass the absolute path to a zip, HTML report, or `allure-results` directory.
- **PR**: pass PR number or note that current diff should be used.
- **Baseline**: if the user named a baseline run/path, pass it; otherwise let the subagent infer.

Do **not** pass comparison counts, failure classifications, report templates, or phrases like "likely flaky".

## Parent-agent constraints

- Do **not** download artifacts, run compare scripts, or draft verdicts yourself.
- Do **not** Grep/Read/Glob/Shell before or instead of Task.
- Do **not** substitute `explore` / `generalPurpose` / parent analysis when `allure-report-analyzer` fails — except the fallback below.
- After the subagent finishes, present **both reports** as returned. Do not collapse them into a single merge approval.
- Surface **Red flag count** and **Delta verdict** prominently.

## Retries

- Bad invocation (wrong type, empty prompt): correct once and retry.
- Other transient Task failures: retry once with the same prompt.
- If Task rejects `allure-report-analyzer` as unknown/unregistered: retry **once** as `generalPurpose` whose prompt starts with the full contents of `~/.cursor/agents/allure-report-analyzer.md`, then the prompt shape above. Tell the user a **Developer: Reload Window** (or restart Cursor) will register the subagent for later chats.
- If that fallback also fails, stop. Do not analyze in the parent unless they explicitly ask you to proceed without the subagent.
