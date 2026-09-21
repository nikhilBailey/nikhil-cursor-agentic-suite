---

## name: exploratory-quiz

description: >-
  Run an evidence-based exploratory quiz over a user-given scope (one repo,
  folder, feature, or multiple repos). Use when the user says exploratory
  quiz, run an exploratory quiz, or equivalent with a scope. Asks how many
  budgeted questions, researches, publishes a quiz plan, then quizzes one item
  per turn via AskQuestion. Escalations, miss variants, and clarifications do
  not count toward N. Pauses only for debug-now work; handles opinion and
  remind-later asides without implementing. Do not use for Cursor /onboard or
  generic onboarding without an explicit quiz request.

# Exploratory quiz

Parent-only. Do **not** launch a subagent. First user-visible tool call is the **count** `AskQuestion`.

## Hard rules

- Exactly **one** `AskQuestion` per assistant message, and exactly **one** quiz item in it (never a batch of 2–3).
- Back-and-forth is the point. Comments, judgments, and “we should fix X” are **asides**, not work orders. Classify them (step 6). Do not implement, ticket, or pause unless the aside is **debug now**.
- Help/wrong follow-ups, **escalations**, and **clarifications you need from the user** do **not** consume N. A follow-up **variant after a miss** is a follow-up, not a new budgeted item.
- Ground every item in files you read. Do not dump the answer key.
- Option shape: see [examples.md](examples.md). Rotate the correct index (`itemIndex % 4`). Never default to first. Equal length and tone — the right answer must not be the long, path-packed one.

## Flow

### 1. Count

If scope is missing, ask for it in the same count question’s freeform path, or ask scope first.

`AskQuestion` prompt: `How many questions before the final review?`

Options: `8` / `12` / `20` / `I will type a number`.

Do not research before N is known.

### 2. Research (bounded)

One parallel wave: README, package/manifest scripts, CI workflows, top-level layout, then the named focus (grep/read). Optional second wave only to fill holes in that focus. No Jira/Confluence/MCP unless the scope includes it.

Inspect scripts/CI/layout. You **may** run the entire test suite when you know it will run **quickly** and you will use the result for a **quiz question** or to **escalate** something. Do not run it as a teaching demo that turns into classifying every failure.

**Discovered issues** (failing tests, missing CI gate, misnamed module): keep them. They get an **escalation** quiz item (does not consume N) plus `followUps[]`. Not a derailment, not a fix. See step 3.

### 3. Publish the quiz plan

Show a compact plan **once**, then keep it as working state. Allocate **N** across: map, run, find, change, confusable terms, plus the scoped focus.

List escalations separately. They do **not** count toward N. Same for AskQuestion turns that only clarify how to treat an aside.

```text
Quiz plan (N=10)  scope: payments-api / refund flow
1. [map] service boundaries and main HTTP entrypoints
2. [run] unit-test command from package manifest
3. [find] where refund routes are registered
4. [change] handler vs service layer for refund logic
…
10. [confusable] refund id vs charge id in logs
Escalations (not in N):
E1. [escalate] whether CI runs the test suite on merge
followUps: local tests mostly pass but workflow deploys without a test job
```

Then ask item 1. Do not reprint the full plan every turn.

### 4. Run

One item per turn. Track misses (id + what they mixed up).

After a miss or **I need help**: 2–5 sentences with paths, then **one follow-up variant** on the same distinction. That variant does **not** consume N. Then continue the plan at the next budgeted item.

Ask an **escalation** item when you have the fact (interleave is fine). Then return to the next N item. Do not follow an escalation with a forensic streak.

### 5. New information — pause and think

When the user corrects a claim or returns from exploring with new facts, **do not ask the next planned item in that turn**.

Think: does this invalidate one upcoming item, or is the remaining curriculum the wrong course?

**Stay the course (default).** Rewrite **one** remaining item so the new fact is accurate. Do not add a streak of questions on the new topic. One line: `Plan: stayed the course — replaced item 7. Next is still <category>.` Then ask the next **original-category** item (or the rewritten one if it is next).

**Rework remaining.** Only if they say the quiz is on the wrong track, rework the plan, this is not what I wanted to learn, or equivalent. Keep N and already-asked items. Replace the rest. Show the new remaining list once, then ask the next item.

A single factual correction (e.g. “there is no queue — refunds are synchronous”) is stay-the-course material, not a new topic curriculum. See [examples.md](examples.md).

### 6. Asides — classify, then stay on the quiz

Learning here is a conversation. A comment is one of:


| Intent           | Signals                                                                                       | Do                                                                                                                                                                                                                                                                                                                                                        |
| ---------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Debug now**    | take a break, debug this right now, set that and run it, implement, fix it in the repo        | Pause. One line: `Quiz paused (k of N remaining). Say back to quiz to continue.` Do the work they asked. Resume only on **back to quiz**.                                                                                                                                                                                                                 |
| **Opinion now**  | restating knowledge, is that right, your take, this is a bad stack, that has to be priority 1 | Give feedback: agree, disagree, or point out relevant info (**short**, from what you already know or one small read). Then the **next quiz item in the same turn**. Do not ticket or edit. If the fact also invalidates a planned item, apply step 5 (one rewrite) in that same turn. If answering would take a long investigation, you are unsure — ask. |
| **Remind later** | after the quiz, remind me, we should follow up, ticket this later                             | One-line ack. Store in `followUps[]`. Next quiz item same turn. Surface at close. Do not ticket unless they asked for ticket text.                                                                                                                                                                                                                        |


If unsure, one `AskQuestion` (this is the quiz-turn question — do not also ask a quiz item):

Prompt: `How should I treat that?`

- `We need to take a break to debug this right now`
- `I need clarification / confirmation / opinions on this`
- `After the quiz is over remind me to follow up on this`

“That has to be priority number 1” with no “fix it now” is **opinion now** or **remind later** — never implement. A fork to go look at something is **debug now** and is useful.

### 7. Close

Close only after all **N** budgeted items are asked.

**Order:**

1. **Leftover escalations** — if any `Escalations (not in N)` were never asked, ask them now (one per turn, same option rules). If you already asked them during the run, skip.
2. **Review round** — variations on **misses only** (items they got wrong or chose **I need help** on). Same option rules: one item per turn, equal-length options, rotated key. Re-test the distinction, not the exact same wording. Stop when every miss has had at least one variant, or they have answered correctly on retry.
3. **Knowledge-gap summary** — prose only (no AskQuestion). Keep it short and actionable:

```text
## What you have down
- 2–4 bullets: categories or skills they answered confidently

## Gaps to revisit
- One bullet per miss: what they confused, the correct mental model, and where to look (file, command, or doc)

## Next time in this scope
- 2–3 concrete habits: what to grep, which command to run first, which layer to open before changing code

## Follow-ups
- Every entry from followUps[] (discovered issues, remind-later asides). One line each; say whether it is awareness vs work to schedule later.
```

If there were no misses, say so briefly and still give **Next time** and **Follow-ups**. No canvas unless they ask for a durable artifact.

## AskQuestion shape

- Stem carries shared evidence / file names. Smoking-gun paths do not live only on the correct label.
- 4 content options + last option exactly: `I need help — explain this, then quiz me again.`
- Content labels: one sentence, same grammar, lengths within ~20%. Plausible nearby files/commands as distractors, not jokes.
- `allow_multiple` off.

## State to keep

`scope`, `N`, `plan[]` (id, category, target, asked, countsTowardN), `nextIndex`, `misses[]`, `followUps[]`, `paused`.