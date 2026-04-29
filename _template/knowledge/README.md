---
slug: {{PROJECT_SLUG}}
parent: hub
category: {{CATEGORY}}
status: seeded
description: ""
---

# {{PROJECT_NAME}}

_(1–2 предложения: что это, для кого, в каком статусе)_

**Статус:** seeded
**Категория:** {{CATEGORY}}
**Создано:** {{DATE}}

> Полный каталог — [index.md](index.md). Текущее состояние — [state.md](state.md). Хронология — [log.md](log.md).

<!--
The frontmatter (slug/parent/category/status/description) is "managed" by
`kb-rebuild-registry`: when it regenerates `~/knowledge/registry.md` and
`hierarchy.yaml` from per-project metadata, it merges these fields here.
You can edit description and status freely; `kb-rebuild-registry` will
preserve unmanaged keys.

Default `parent: hub` — if this project is a sub-project of another
(e.g. <sub-a> is a child of <umbrella-a>), edit parent to point at the
parent's slug AFTER initial creation. `kb-doctor hierarchy-check` will
validate referential integrity.

Default `status: seeded` — flip to `live` once the wiki has real content,
or `archived` when the project is paused.
-->
