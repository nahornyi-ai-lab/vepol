# billing-api — agent instructions

Prices, invoices, payments and refunds for Acme's shop (a fictional sample
project). Python, one Postgres database, an append-only ledger.

## Project memory

The knowledge base for this project lives in `knowledge/`. Read it before you
start and write back before you finish:

- `knowledge/state.md` — where the project is right now. Read it first; when the
  current situation changes, replace the outdated lines (it is not a history).
- `knowledge/log.md` — append one dated entry per meaningful result or decision:
  `## [YYYY-MM-DD] <category> | billing-api | "<summary>"` plus a short body.
- `knowledge/backlog.md` — the task board. Change it only through `kb-board`
  (claim, request-review, close); never edit statuses by hand.
- `knowledge/decisions/` — one page per decision with `title`, `date` and
  `status` frontmatter. Record why, not only what.
- `knowledge/incidents.md` — what broke and the prevention rules. Check the
  rules before touching money or the ledger.

## Working rules

- Money is integer cents plus a currency code, everywhere.
- Ledger rows are never updated or deleted; corrections are new rows.
- Run `pytest` before asking for review.
