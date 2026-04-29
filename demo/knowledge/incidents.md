# Hub incidents

What broke, root cause, fix, prevention rule. Every error is an artefact,
not a fleeting frustration.

> Format: timestamped sub-headers, with structured body.

## Prevention rules (active)

- **Subscription audit quarterly** — after the April 2026 doubled-charge
  incident, hub-level recurring task on the last Sunday of every quarter.
- **Friday workout protected** — after 3 missed Fridays in 6 weeks, Friday
  evening workout is treated as a fixed appointment. If a client requires
  Friday EOW push, the workout moves to Saturday morning *that same week*,
  not skipped. (Tracking in projects/health/strategies.md.)
- **Verify SLA on incoming deliverable requests** — after Beta-Corp 2026-04
  scope creep, every new deliverable request gets the SLA confirmed in
  writing before work starts.

## Automated guards (active)

- (No automated guards configured yet at the hub level. The session
  capture pipeline runs automatically for daily extraction; weekly retro
  runs Friday evenings.)

---

## [2026-04-18] Doubled subscription charge — kids' streaming

**Symptom:** monthly streaming subscription charged twice in one billing cycle ($14.99 each, total $29.98 vs expected $14.99).

**Root cause:** the service had migrated billing systems in March and double-billed about 2% of accounts during the transition. Issue acknowledged on their status page after I emailed.

**Fix:** one email to support, refund issued within 24 hours.

**Prevention:** quarterly subscription audit (now in active prevention
rules). Beyond detection, no realistic prevention — it was a vendor-side
billing infrastructure issue.

---

## [2026-04-04] Skipped Friday workout (third in 6 weeks)

**Symptom:** Friday strength session skipped. End-of-week client push displaced it.

**Root cause:** Friday afternoons consistently get crunched by EOW client deliverables. The workout slot is the second-most-elastic thing in my Friday calendar (after the pre-bedtime reading slot, which I'm not willing to give up).

**Fix:** for that week, moved to Saturday morning — but it became a pattern over six weeks.

**Prevention:** moved Friday workout to a *protected* slot (active rule
above). Pattern logged in projects/health/strategies.md as an active
hypothesis: "Friday-afternoon workouts will fail in any week with active
client deliverables; Saturday-morning is the right default."

---

## [2026-03-22] Confused calendar — overlapping doctor appointment + parent meeting

**Symptom:** scheduled both my annual physical and Lily's parent-teacher conference for the same Tuesday at 14:00. Found out morning-of.

**Root cause:** booked the doctor's appointment from a phone (no Vepol calendar context), didn't check the family calendar.

**Fix:** rescheduled the doctor for the next available slot.

**Prevention rule:** all bookings made from any device feed into the
hub calendar. If a Vepol client (Calendar MCP) is wired up, Vepol can
warn at booking time if there's a conflict; otherwise, do not book from
the phone unless the family calendar is open in another tab.
