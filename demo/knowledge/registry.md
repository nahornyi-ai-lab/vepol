# Registry of demo projects

The single source of truth about what projects exist in this demo wiki,
where they live, and what status their wiki is in.

**Demo note:** all entries below are synthetic. The paths point inside
this repo's `demo/knowledge/projects/` rather than the user's `$HOME` —
that's the only structural difference from a real hub registry.

**Status legend:**
- `live` — wiki is actively being maintained
- `seeded` — skeleton in place, awaiting first ingest
- `archived` — frozen, kept for reference

**Categories:**
- `personal` — life logistics (family, household, hobbies)
- `work` — paid work (clients, deliverables, employer)
- `health` — body, sleep, exercise, medical
- `finance` — money management, savings, expenses
- `learning` — books, courses, certifications

---

| slug | status | category | path | description |
|---|---|---|---|---|
| family | live | personal | `projects/family/` | Household coordination — kids' school, weekend plans, household tasks, recurring family routines. Two children (10 and 7), one car, planning a summer trip. |
| work | live | work | `projects/work/` | Independent consulting practice — three active clients, monthly invoicing, ongoing deliverables. Currently scaling from solo to first-hire stage. |
| health | live | health | `projects/health/` | Personal health tracking — strength training (3x/week), sleep target 7+ hours, lab work twice yearly, nutrition log. |
| finance | live | finance | `projects/finance/` | Monthly budget review, three savings goals (emergency / vacation / kids' education), tracking subscriptions. |
| learning | live | learning | `projects/learning/` | Reading list (currently 3 books in flight + 1 just finished), one online course (system design), tracking takeaways into concept pages. |

---

## How this is generated

In a real hub, `registry.md` is a hybrid file with a derived block (auto-generated from each project's frontmatter via `kb-rebuild-registry`) and a hub-managed block (manual entries for pointer / archived / unwiki'd projects). For this demo, all entries are manual — the projects are flat and fixed.

For the real schema, see the master file at `knowledge/CLAUDE.md` in the repo root.
