# {{PROJECT_NAME}} — локальная схема вики

> Наследует мастер: [`~/knowledge/CLAUDE.md`](~/knowledge/CLAUDE.md). Здесь — только специфика проекта.

## О проекте

_(1–3 предложения: что это, зачем, для кого, в каком статусе)_

## Структура проекта

```
{{PROJECT_SLUG}}/
├── CLAUDE.md                # этот файл
├── knowledge/               # ВСЯ вика проекта (изолирована от кода)
│   ├── README.md            # короткое описание
│   ├── index.md             # каталог страниц
│   ├── log.md               # лог
│   ├── state.md             # текущее состояние
│   ├── raw/                 # immutable источники
│   │   └── assets/          # картинки
│   ├── sources/             # саммари raw-документов
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
## [2026-04-22] account | created | <slug-a> | dev-account active → vendor.com:user@example.com
## [2026-04-25] publish | created | <slug-a> | v2.1.2 published → store.example.com:com.example.app
## [2026-04-30] subscription | cancelled | <slug-b> | service-name → service.example.com:user@example.com
## [2026-05-01] person | renamed | <slug-c> | alias-a ≡ Alias B (alias merge)
## [2026-05-03] asset | created | <slug-b> | device-model → vendor.com:<device-uuid>
```

**Зачем:** хабовый вечерний cron (`kb-orchestrator-cycle` retro pass) собирает эти строки → апдейтит `~/knowledge/personal/assets.md` / `people/<slug>.md` / `companies/<slug>.md`. Без префикса событие не подхватится. Спека: [`concepts/entity-extraction-cycle-pass.md`](~/knowledge/concepts/entity-extraction-cycle-pass.md).
