# design-system — agent instructions

Shared design tokens and UI components for Acme's storefront and admin pages
(a fictional sample project). Tokens are JSON; components are plain React.

## Project memory

The knowledge base for this project lives in `knowledge/`. Read it before you
start and write back before you finish:

- `knowledge/state.md` — where the project is right now. Read it first; when the
  current situation changes, replace the outdated lines (it is not a history).
- `knowledge/log.md` — append one dated entry per meaningful result or decision:
  `## [YYYY-MM-DD] <category> | design-system | "<summary>"` plus a short body.
- `knowledge/backlog.md` — the task board. Change it only through `kb-board`
  (claim, request-review, close); never edit statuses by hand.
- `knowledge/decisions/` — one page per decision with `title`, `date` and
  `status` frontmatter. Record why, not only what.
- `knowledge/incidents.md` — what broke and the prevention rules. Check the
  rules before publishing tokens.

## Working rules

- Every colour token passes the contrast check before it is published.
- Breaking token changes go into a new major version with a migration note.
