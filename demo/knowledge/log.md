# Hub event log

Append-only chronological log of everything significant happening across
the five demo projects. Each line follows the convention:

```
## [YYYY-MM-DD] kind | slug | "headline"
```

Where `kind` is one of: `ingest | query | session | decision | experiment | incident | hub | hypothesis | strategy | review`.

Quick view: `grep "^## \[" log.md | tail -20`

---

## [2026-04-22] hub | hub | "Q2 push update — Acme renewal at week-out, family trip 3 weeks out, health back to 2-3x/week"
End-of-week pulse. Three threads compressing into the next two weeks. State.md updated.

## [2026-04-21] decision | work | "Acme renewal — going in at +18% on the new SOW"
After ten days of weighing, decided on +18% pricing with a stricter scope. Justification in `projects/work/decisions/0003-acme-renewal-pricing.md`.

## [2026-04-21] session | work | "Acme renewal kickoff call with Sarah Mendez (60 min)"
Notes captured in `projects/work/daily/2026-04-21.md`. Action items: send updated SOW by Wednesday, schedule follow-up for Friday.

## [2026-04-20] ingest | learning | "Finished 'Designing Data-Intensive Applications', summary in projects/learning/sources/ddia.md"
Three lessons lifted into `concepts/`: chapter on consensus algorithms is the densest; partition tolerance vs availability tradeoffs framed clearly; the chapter on derived data shifted my thinking about caching strategy.

## [2026-04-19] experiment | health | "start | resuming 3x/week strength training after 8-week hiatus"
Hypothesis: at 3x/week with current sleep average, baseline lifts return within 4 weeks. Tracking in `projects/health/experiments/strength-2026-q2.md`.

## [2026-04-19] hub | family | "Summer trip cabin shortlist down to 3"
Three candidates: lakeside cabin (2 hours away, $$), forest cabin (3 hours, $), beach rental (1.5 hours, $$$). Decision deadline May 15 to lock summer rate.

## [2026-04-18] incident | finance | "Doubled subscription charge on kids' streaming service — refunded after one email"
Logged in `incidents.md` for the prevention rule (audit subscriptions quarterly).

## [2026-04-17] retro | hub | "Week 16 retro — 2 of 3 weekly priorities closed; missed health Friday session"
Reflection note: pattern is that Friday workouts get displaced by client EOW pushes. Considering moving the third weekly slot to Saturday morning. Hypothesis logged in `projects/health/strategies.md`.

## [2026-04-16] session | work | "Beta-Corp deliverable v2 sent for client review (deliverable: API spec rev)"
Two days under the SLA. Reply expected within 5 business days.

## [2026-04-15] decision | family | "Tom's school: switching to bus next year, parent-driven this year"
Rationale: Tom's confidence with the route, less fuel cost, frees morning time for the gym. Decision in `projects/family/decisions/0002-tom-school-transport.md`.

## [2026-04-15] hub | finance | "Subscription audit done — 4 cancelled (saved $47/mo), 12 kept"
Full review in `projects/finance/audits/2026-04-subscriptions.md`.

## [2026-04-14] session | learning | "Started chapter 9 of DDIA — consistency models"
Three pages of notes, two questions for follow-up.

## [2026-04-13] ingest | health | "Lab results from annual check-up — all in range, vitamin D borderline low"
Doc summary in `projects/health/sources/2026-04-labs.md`. Action: D3 supplement starting next week.

## [2026-04-13] strategy | work | "Updated work strategies.md — abandoning the 'open to all client types' hypothesis"
After Q1 data: clients in `enterprise SaaS` paid 40% better and consumed less attention. Tightening focus.

## [2026-04-12] decision | finance | "Emergency fund target raised from 3 to 6 months"
After running the numbers: with two kids and a year of self-employment, 3 months feels thin.

## [2026-04-11] hub | family | "Lily's school recital booking confirmed for May 18"
Calendar updated. Whole family + grandparents.

## [2026-04-10] session | work | "Beta-Corp invoice 0214 sent — 30 day net, due May 10"
Logged in `projects/work/invoices/0214.md`.

## [2026-04-10] hypothesis | health | "Hypothesis: 7.5h sleep correlates with 8% better workout RPE next day"
Tracking with sleep data + post-workout RPE notes. Will revisit at 30 days.

## [2026-04-09] retro | week | "Week 14 retro — closed Acme deliverable v1, lab work, strength baseline"
Three blue items, one yellow (skipped retro on Tuesday).

## [2026-04-08] session | family | "Wednesday parent coffee — Tom's reading speed up 20% per teacher"
Notes in `projects/family/journals/2026-04-08-school-coffee.md`.

## [2026-04-07] ingest | work | "Read 'Pricing Creativity' (Tom Sant) — three takeaways for the renewal"
Source summary in `projects/work/sources/pricing-creativity.md`. Lifted insight: anchor first, justify after.

## [2026-04-06] hub | hub | "Q2 plan locked — three weekly priorities each Monday"
Plan structure: Monday brief sets 3 things; Friday retro reviews them. Strategy file updated.

## [2026-04-05] hub | hub | "Sunday review — first 3 months of Vepol setup"
Demo "user" reflection: the triad pattern is the highest-value piece; brief/retro is second; the cross-linking and lifting are still novel and surprising.

## [2026-04-04] decision | family | "No screens during weekday dinner — trial for 30 days"
Clear pattern from last week: dinner-without-screens conversations are 4-5x richer. Trial in `projects/family/experiments/no-screens-dinner.md`.

## [2026-04-03] session | learning | "DDIA chapter 7 done"
Strong chapter. Linked to existing `concepts/` page on transactions.

## [2026-04-02] session | health | "Strength session — squats 5x5 @ 80kg, deadlift 3x5 @ 100kg"
Both lifts +2.5kg vs last week. Tracking in `projects/health/training-log.md`.

## [2026-04-01] hub | hub | "Month-end review for March, plan for April"
Detailed review in `projects/finance/monthly/2026-03.md`. April plan: complete Acme renewal, start strength rebuild, lock summer trip.

## [2026-03-30] retro | week | "Week 12 retro — all 3 weekly priorities closed, sleep average 7.4h"
Solid week.
