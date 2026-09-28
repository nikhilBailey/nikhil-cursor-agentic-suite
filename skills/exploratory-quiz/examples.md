# Exploratory quiz examples

Copy the good shapes. The bad ones are from the first payments-api quiz run.

## Option length and tell

**Bad** — correct choice is first, longest, and the only one with paths:

```text
prompt: Where does create vs update start?
A) CreateSsoPage (sso/create): name the domain and prove it with a DNS TXT record (getDNSTXTRecord / ssodomainverification=). UpdateSsoPage (sso/:id): set protocol and mappings.  [len ~340]
B) CreateSsoPage is where you paste OIDC/SAML metadata. UpdateSsoPage is only for deleting domains.
C) There is a single page; create and :id are aliases for the same component.
D) ManageSsoPage contains the create and protocol forms; the other two pages are unused leftovers.
E) I need help — explain this, then quiz me again.
```

**Good** — shared evidence in the stem; four parallel sentences; correct index rotated (`itemIndex % 4` = 2 here):

```text
prompt: New SSO domain vs continue an existing one. Pages live under src/pages/SsoDomainsPage/. Which split is right?
A) CreateSsoPage pastes OIDC/SAML metadata; UpdateSsoPage only deletes.
B) create and :id are aliases; one component handles both jobs.
C) CreateSsoPage names the domain and proves ownership; UpdateSsoPage configures protocol.
D) ManageSsoPage owns create and protocol; the other pages are leftovers.
E) I need help — explain this, then quiz me again.
```

Never default the key to A, instead randomize between all the key options. If the key is the long one, shorten it and lengthen the distractors until they match.

## Miss follow-up variant (not in N)

You miss “SPA `/callback` vs IdP ACS.” Explain in 2–5 sentences, then one **variant** (e.g. a US OIDC testing-step URL). That variant does **not** consume N. Next turn is still the next budgeted plan item, not a replacement for it.

Do not treat the variant as item N+1 of the curriculum. Do not skip a budgeted item because you already asked a variant.

## Discovered issues (escalation, not in N)

Finding “the suite is ~40% red and CI does not run tests” is useful. A **fast** full `npm test` is allowed when you will use that number in a question or an escalation. Do **not** turn the rest of the session into suite forensics or a fix. The escalation item does **not** consume N.

**Good — extra item, then back to the N plan:**

```text
prompt: On this checkout of main, about what fraction of npm test cases failed?
A) None — the suite is green; CI is the only place it is red.
B) About 10% of tests (a couple of page specs).
C) About 40% of tests (roughly half the suites).
D) All of them — Jest does not start on this repo.
E) I need help — explain this, then quiz me again.
```

Then the next **budgeted** item (i18n, callbacks, …). Also store `followUps[]` ← “Jest on main is ~40% red; CI deploy has no test job.”

**Bad:** run the suite as a demo, then spend several turns classifying failures, writing jest.setup.js, or replacing the remaining N with Jest.

## New information: stay the course

**Setup.** Scope: `payments-api` / refund flow. N=10. You are on item 5 of 10. Item 4 asked how a refund is submitted; the correct answer was `POST /v1/refunds` via `RefundHandler`.

**User returns from reading code:** “Refunds are not async here — there is no queue. `RefundHandler` calls `StripeClient` synchronously and returns 201.”

That invalidates **one** upcoming item, not the whole plan.

**Bad** — the correction becomes the next two budgeted items:

```text
6. [run] is there a refund queue or worker?
7. [find] where is the refund consumer deployed?
8. (would have been [change] idempotency key — delayed)
```

**Good** — pause, think, rewrite **one** remaining item, then continue the original categories:

```text
Plan: stayed the course — replaced item 7.
Remaining:
7. [change] where idempotency keys are checked before Stripe is called  (was: “which queue topic receives the refund job”)
8. [find] how to locate refund error codes in OpenAPI
9. [confusable] refund id vs charge id in logs
10. [run] make test for RefundHandler only
```

One line of plan status, then ask item 6 (the next budgeted item you have not asked yet). Do not add a streak on queues, Stripe, or deployment.

## New information: rework remaining

You say the quiz is on the wrong track, rework the plan, or this is not what you wanted to learn (e.g. you asked for SSO navigation and the remaining items are all Jest/CI).

Keep N and already-asked items. Replace the rest. Show the new remaining list once.

```text
Plan reworked (6 of 12 remaining). New remaining:
7. [find] sso axios client vs idp-client
8. [change] OIDC vs SAML save split
9. [find] account uuid for the manage list
10. [run] one-spec Jest path (command only, not suite health)
11. [confusable] Vite module federation vs SSO domain federations
12. [confusable] SPA login callback vs IdP ACS
```

Do not rework because a single fact was corrected. That is stay-the-course.

## Asides: three intents

Back-and-forth is the point. Do not treat a comment as a work order.

**Debug now** — “set that then run locally”, “take a break and debug this”, a fork to go look at the suite. Pause. Wait for `back to quiz`.

**Opinion now** — restating knowledge for a take, then continue. This is what “The Jest suite is in an awful state. That has to be priority number 1” was.

```text
Bad:  write jest.setup.js / jest.config.js / specs; or emit a Jira ticket unasked
Good: “Agreed — specs last moved in the first commit and CI only deploys. I’d treat a green harness as follow-up, not today’s map.” Then AskQuestion for the next planned item.
```

**Remind later** — same sentence if they clearly mean after the quiz (“we should ticket this later”). Ack, store, next item. At close, list it under follow-ups. Still do not implement.

If those two could both fit, AskQuestion:

```text
How should I treat that?
- We need to take a break to debug this right now
- I need clarification / confirmation / opinions on this
- After the quiz is over remind me to follow up on this
```

Do not offer “implement” / “Jira ticket” as the default fork. The user will specify what they want if you are unsure and ask a clarifying question.