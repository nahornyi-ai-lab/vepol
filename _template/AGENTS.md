# {{PROJECT_NAME}} — локальная схема вики

> Наследует мастер: [`~/knowledge/AGENTS.md`](~/knowledge/AGENTS.md). Здесь — только специфика проекта.

## О проекте

_(1–3 предложения: что это, зачем, для кого, в каком статусе)_

## Структура проекта

```
{{PROJECT_SLUG}}/
├── AGENTS.md                # этот файл (canonical; читается Codex/Claude Code/Antigravity CLI)
├── CLAUDE.md                # Claude Code adapter → AGENTS.md (≤30 строк)
├── knowledge/               # ВСЯ вика проекта (изолирована от кода)
│   ├── README.md            # короткое описание
│   ├── index.md             # каталог страниц
│   ├── log.md               # лог
│   ├── state.md             # текущее состояние
│   ├── raw/                 # immutable источники
│   │   └── assets/          # картинки
│   ├── sources/             # саммари raw-документов
│   ├── agents/              # одна карточка проекта: agent-card.md (общая для всех runtime; identity = роль проекта, не вендор)
│   └── <категории>/         # специфичные для проекта
└── <code-dirs>/             # код проекта — сиблинги к knowledge/
```

## Категории (начальный набор)

_(перечислить, какие подпапки в `knowledge/` имеют смысл для этого проекта. Примеры:_
- _для лидген-проекта: `icp/`, `offers/`, `channels/`, `funnel/`, `metrics/`, `experiments/`, `agent-specs/`_
- _для проекта-библиотеки: `api/`, `patterns/`, `decisions/`_
- _для pet-эксперимента: возможно, только `sources/` и `experiments/`)_

## Границы автономии

Что агент может делать без подтверждения, а что — только с ревью.

- **Свободно:** создавать/обновлять страницы в `knowledge/`, апдейтить `log.md`, `state.md`, `index.md`.
- **С подтверждением:** изменения в code-dirs проекта, создание новых категорий в `knowledge/`, удаление страниц.
- **Никогда:** трогать `knowledge/raw/`, пушить в git без команды, удалять чужие файлы вне `knowledge/`.

## Agent card

В проекте — **одна карточка на роль** (не одна на runtime): `knowledge/agents/agent-card.md`. Identity привязана к роли проекта; Claude Code, Codex, Antigravity CLI и будущие runtime работают по одной и той же карточке. Runtime-различия (что доступно Claude, что — Codex, …) живут в секции `## Operating notes` внутри карточки.

При каждом старте новой сессии — до первого содержательного ответа или действия — агент обязан иметь startup context: agent card, `knowledge/state.md`, свежий срез `knowledge/log.md`, active work/open escalations и компактный incident-срез. Нормальный путь — hook-injected `Startup Context Manifest`; если manifest есть, перечисленные в нём срезы считаются прочитанными, и агент не перечитывает `knowledge/index.md`, полный `knowledge/incidents.md` или весь `knowledge/backlog.md` только ради формальности. Если manifest нет (hook-less runtime), запусти `~/knowledge/bin/kb-session-start --print --cwd "$PWD"` или вручную прочитай: карточку по иерархии `knowledge/agents/agent-card.md` → `~/knowledge/agents/agent-card.md` → явный fallback «карточки нет», `knowledge/state.md`, `tail -n 80 knowledge/log.md` (fallback 160 при <3 датированных записей), active work через `kb-board`, открытые эскалации и `## Prevention rules` / `## Ongoing` из `knowledge/incidents.md` при наличии. `knowledge/index.md` и полный `knowledge/incidents.md` — on-demand навигация/диагностика, не startup load. Вопрос «кто ты / представься» не является триггером чтения: отвечать по уже прочитанному `## Self-introduction`, не generic-описанием вендора. Полная схема — в [`~/knowledge/AGENTS.md`](~/knowledge/AGENTS.md#session-startup-context).

Если карточки в проекте ещё нет — агент явно сообщает об этом и предлагает завести. Образец — `~/knowledge/_template/knowledge/agents/_example.md` (после `new-wiki` он автоматически копируется в `knowledge/agents/_example.md`). Первая операция: `cp knowledge/agents/_example.md knowledge/agents/agent-card.md` и заполнить под проект.

## State contract

`knowledge/state.md` — текущая приборная панель проекта, не лог и не архив. Пиши overwrite-only: когда реальность меняется, записывай событие в `knowledge/log.md` (если оно durable), затем заменяй устаревшую строку в `state.md`. Исторические даты, proof, review results, resolved blockers и старые snapshots уходят в `log.md`, `reports/`, `decisions/`, `sources/` или тематические страницы. Текущие дедлайны, активные офферы, метрики, freshness дат и `Last Updated` допустимы.

## Owner-approved spec gate

For non-trivial work, the path is mandatory: research -> owner-approved spec -> `knowledge/spec-approvals.md` with exact `spec-contract` hash -> build plan -> RED tests with mandatory E2E path -> implementation. The owner can approve in chat; the active agent records the decision as scribe. Any material drift after approval returns to spec review and owner approval.

## Cross-orchestrator CLI launch

Агенты на этой машине могут запускать локальные CLI (Claude Code, Codex, Antigravity `agy`, Grok, OpenCode, NotebookLM) через shared matrix: [`~/knowledge/solutions/cli-agent-runtime-launch.md`](~/knowledge/solutions/cli-agent-runtime-launch.md). **Живой ростер** — какие из них реально установлены здесь и когда какой звать — в `knowledge/.active-roster.md` (автогенерится `kb-cli-roster`, инжектится в каждую Claude/Codex-сессию; оркестраторы без хука читают файл сами). Без версий, gitignored.

## Метрики проекта

_(какие цифры меряем, откуда они приходят, как часто обновляются → см. `knowledge/metrics/` если есть)_

## Связанные проекты в хабе

_(симлинки на другие проекты, с которыми есть пересечения — обновлять по мере появления связей)_

## Significant external state changes (entity events)

При любом значимом изменении внешнего состояния проекта — обязательная запись в `knowledge/log.md` строкой с грепабельным префиксом:

```
## [YYYY-MM-DD] <category> | <action> | <project_slug> | <one-line description> [→ <provider>:<external_ref>]
```

- **Categories:** `publish | account | subscription | person | company | asset`
- **Actions:** `created | updated | renamed | deprecated | cancelled | closed | transferred | deleted`
- `<project_slug>` — slug этого проекта (тот, под которым он живёт в `~/knowledge/registry.md`).
- `<provider>:<external_ref>` — опционально, но **сильно** рекомендуется когда есть стабильный внешний референт (домен/handle/bundle-id/url). Это ключ для deterministic upsert при hub-rollup'е.

**Когда писать:**

- `publish` — публикация артефакта (App Store / Play Store / npm / pypi / production-домен), отзыв публикации.
- `account` — регистрация нового developer-аккаунта (Apple Dev, Google Play, Cloudflare, Stripe, Vercel, GitHub Org, etc.), закрытие аккаунта, передача владения.
- `subscription` — новая платная подписка/SaaS (Holded, MS365, OpenAI API, Linear, etc.), смена плана, отписка.
- `person` — появление key-партнёра-человека (клиент, коллега, broker, fundraising-контакт), смена роли, ровно один alias-merge при `renamed`.
- `company` — клиент / партнёр / провайдер / конкурент / target-investor.
- `asset` — hardware (Mac/iPhone/часы/весы/рутер), virtual asset (домен, IP, физический ключ), ключ-токен (только метаданные: provider, scope, location-of-secret-file, rotation-date — **никогда** не значение токена).

**Примеры:**

```
## [2026-04-22] account | created | <slug-a> | dev-account active → vendor.com:user [at] example.com
## [2026-04-25] publish | created | <slug-a> | v2.1.2 published → store.example.com:com.example.app
## [2026-04-30] subscription | cancelled | <slug-b> | service-name → service.example.com:user [at] example.com
## [2026-05-01] person | renamed | <slug-c> | alias-a ≡ Alias B (alias merge)
## [2026-05-03] asset | created | <slug-b> | device-model → vendor.com:<device-uuid>
```

**Зачем:** хабовый вечерний cron (`kb-orchestrator-cycle` retro pass) собирает эти строки → апдейтит `~/knowledge/personal/assets.md` / `people/<slug>.md` / `companies/<slug>.md`. Без префикса событие не подхватится. Спека: [`concepts/entity-extraction-cycle-pass.md`](~/knowledge/concepts/entity-extraction-cycle-pass.md).
