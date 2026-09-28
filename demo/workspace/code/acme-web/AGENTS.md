# acme-web — agent instructions

The storefront of Acme, a small online shop for hand tools (a fictional sample
project). TypeScript, server-rendered pages, feature flags in `config/flags.json`.

## Project memory

The knowledge base for this project lives in `knowledge/`. Read it before you
start and write back before you finish:

- `knowledge/state.md` — where the project is right now. Read it first; when the
  current situation changes, replace the outdated lines (it is not a history).
- `knowledge/log.md` — append one dated entry per meaningful result or decision:
  `## [YYYY-MM-DD] <category> | acme-web | "<summary>"` plus a short body.
- `knowledge/backlog.md` — the task board. Change it only through `kb-board`
  (claim, request-review, close); never edit statuses by hand.
- `knowledge/decisions/` — one page per decision with `title`, `date` and
  `status` frontmatter. Record why, not only what.
- `knowledge/incidents.md` — what broke and the prevention rules. Check the
  rules before touching checkout or payments.

## Working rules

- Prices, tax and payments come from billing-api; the storefront never computes them.
- Every new checkout behaviour ships behind a flag in `config/flags.json`.
- Run `npm test` before asking for review.
