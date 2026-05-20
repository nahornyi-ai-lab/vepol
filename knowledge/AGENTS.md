# LLM Wiki Hub — мастер-схема

Это центральный хаб персональной базы знаний («второй мозг»). Паттерн — [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): LLM инкрементально строит и поддерживает связный набор markdown-файлов, человек курирует источники и задаёт вопросы.

## Telegram messaging — mention placement (hard rule)

Telegram user mention token (`at` sign + bot username, for example `user_<role>_bot`) ставится **только в конец сообщения**, после полного контекста. Никогда не в начале и не в середине. Причина: Telegram split длинных сообщений → если mention-токен в первом чанке, бот триггерится до того как контекст из последующих чанков дойдёт, и работает на partial context (incident 2026-05-16). Просто упоминание агента в плане/обсуждении без вызова — пиши имя без trigger-токена («project-bot», «hub», «family»). **Правило также применяется к supervisor-prefix:** `_kb_multibot/reply.py::append_user_mention()` теперь ставит mention-токен trigger user в конец reply, а не в начало (фикс 2026-05-17, incident `supervisor-prefix-half-fix`).

## Архитектура

Три слоя:

1. **Raw sources** — immutable источники (статьи, выгрузки, транскрипты, PDF, картинки). LLM читает, не меняет.
2. **Wiki (knowledge)** — markdown, который LLM пишет и поддерживает.
   - **Локальная вика проекта**: `<project>/knowledge/` — физически живёт внутри проекта, рядом с кодом проекта.
   - **Глобальные категории хаба**: `~/knowledge/{concepts,people,companies,solutions}/` — то, что пересекает проекты.
3. **Схема (Universal Agent Entrypoint, 2026-05-19)** — правила:
   - **Canonical, vendor-neutral**: `~/knowledge/AGENTS.md` (этот файл) — hub-level контракт; `<project>/AGENTS.md` — project overlay со специфичными правилами. Полная политика живёт здесь, не в runtime-файлах.
   - **Adapter files (тонкие, ≤ 30 строк)**: `CLAUDE.md` (Claude Code), `GEMINI.md` (Gemini CLI), `.github/copilot-instructions.md` (Copilot), `.cursor/rules/*.mdc` (Cursor), `.windsurf/rules/*.md` (Windsurf), `.clinerules/` (Cline), `.aider.conf.yml` (Aider, через `read: AGENTS.md`). Каждый — bootloader, который только указывает на канонический `AGENTS.md` и держит **только** runtime-specific caveats. Не отдельная политика.
   - **Identity layer (отдельный артефакт)**: `<project>/knowledge/agents/agent-card.md` — карточка роли проекта. Не заменяет AGENTS.md, дополняет.
   - **Полная спецификация** rollout'а — `vepol-dev/knowledge/decisions/universal-agent-entrypoint-2026-05-19.md` + `universal-agent-entrypoint-rollout-spec.md`. Раскатано 2026-05-19, guard — `kb-doctor agent-entrypoint --strict`.

## Структура хаба

```
~/knowledge/
├── AGENTS.md          # мастер-схема (этот файл)
├── registry.md        # реестр всех проектов с путями и статусом
├── index.md           # глобальный тематический индекс
├── log.md             # глобальный лог активности
├── raw/               # хаб-уровневые источники (не привязанные к проекту)
├── concepts/          # кросс-проектные концепты (аутрич, ценообразование, UX, паттерны…)
├── people/            # люди, встречающиеся в разных проектах
├── companies/         # клиенты, партнёры, конкуренты
├── solutions/         # «интересные решения» — сниппеты, находки, реиспользуемые куски
├── projects/          # СИМЛИНКИ в knowledge/ каждого проекта
│   └── <slug> → /absolute/path/to/<project>/knowledge
├── _template/         # шаблон нового проекта
└── bin/
    ├── new-wiki       # скрипт: bootstrap вики в новом проекте
    └── kb-search      # скрипт: ripgrep по всей базе знаний
```

## Структура локальной вики проекта

**Вся вика проекта живёт в одной подпапке `<project>/knowledge/`**, отделённой от кода. Это позволяет симлинку в хабе указывать только на `knowledge/`, не затаскивая `node_modules`, `.git` и прочее.

```
<project>/
├── AGENTS.md                # локальная схема (наследует ~/knowledge/AGENTS.md)
├── GEMINI.md                # Gemini CLI adapter → AGENTS.md
├── knowledge/               # ВСЁ wiki-содержание — изолировано от кода
│   ├── README.md            # 1–2 предложения: что это, в каком статусе
│   ├── index.md             # каталог страниц
│   ├── log.md               # лог проекта
│   ├── state.md             # текущее состояние
│   ├── backlog.md           # задачи от хаба/владельца — проект исполняет
│   ├── escalations.md       # ask-и проекта наверх (к хабу/владельцу)
│   ├── incidents.md         # ошибки, root cause, фиксы, prevention rules, автоматизации
│   ├── strategies.md        # стратегия + активные гипотезы + принципы проекта (обновляется агентом)
│   ├── raw/                 # immutable источники
│   │   └── assets/          # картинки (Obsidian Web Clipper)
│   ├── sources/             # саммари по каждому raw-документу
│   ├── agents/              # одна карточка проекта: agent-card.md (общая для Claude Code / Codex / Gemini CLI / любого будущего runtime; identity привязана к роли проекта, не к вендору)
│   └── <категории>/         # специфичные для проекта: icp/, offers/, channels/, …
└── <code-dirs>/             # site/, … — код проекта, лежит сиблингами к knowledge/
```

**`backlog.md` / `escalations.md` / `incidents.md`** — обязательная триада координации. Мастер-описание формата и правил разграничения живёт в этом `AGENTS.md`; runtime-native файлы (`CLAUDE.md`, `GEMINI.md`) только адаптеры к нему.

**`strategies.md`** — «куда двигаемся и почему» + проверяемые гипотезы о собственной работе агента. Обновляется самим проектом (не хабом): раз в неделю через skill `agent-review` (когда он появится), или при значимом pivot'е. Формат — в `_template/knowledge/strategies.md`. Конвенция лога для стратегии/гипотез/экспериментов: `## [YYYY-MM-DD] strategy | <project> | ...`, `## [YYYY-MM-DD] hypothesis | <project> | ...`, `## [YYYY-MM-DD] experiment | <project> | start|result | ...`.

**`agents/`** — карточка роли проекта. Полная схема, имя файла, поведение при старте сессии, иерархия project→baseline→generic, multi-orchestrator edit protocol — в разделе [«Agent self-identification»](#agent-self-identification) ниже. Короткая версия: **один файл `agent-card.md` на проект**, идентичность привязана к роли (а не к runtime), runtime-различия (Claude Code / Codex / Gemini CLI) живут в секции `## Operating notes` внутри карточки.

**Ключевое правило**: всё, что LLM пишет или читает как «знание», живёт внутри `knowledge/`. Всё, что является рабочим кодом/контентом/артефактом — сиблинги к `knowledge/`.

**Почему нельзя смешивать**: Obsidian-вольт хаба через симлинки видит именно `knowledge/`. Если вики-файлы разбросать вне этой папки — Obsidian их не увидит (или увидит вместе с `node_modules`).

## Universal Agent Entrypoint

Канонический контракт принят 2026-05-19 (`vepol-dev/knowledge/decisions/universal-agent-entrypoint-2026-05-19.md`, cross-review у Codex/Claude/Gemini), раскатан там же (`...-rollout-spec.md`, `...-implementation-plan-2026-05-19.md`). Этот раздел — мастер-формулировка для машины.

### Canonical vs adapter

- **Canonical** = `AGENTS.md` (hub + project). Vendor-neutral, держит **всю** общую политику. Любая runtime читает это и подчиняется.
- **Adapter** = runtime-native файл (`CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursor/rules/*.mdc`, `.windsurf/rules/*.md`, `.clinerules/`, `.aider.conf.yml`, …). Тонкий bootloader: ссылается на канонический `AGENTS.md` и содержит **только** runtime-specific caveats. **Не** отдельная политика и **не** дубль AGENTS.md.

### Adapter contract

Adapter валиден только если:

- Существует потому, что runtime имеет native instruction-file convention.
- Указывает на (или импортирует) релевантный канонический `AGENTS.md`.
- Содержит **только** runtime-specific caveats.
- Не дублирует большие блоки политики из AGENTS.md.
- **≤ 30 непустых строк.** Хард-кап, без escape-hatch.

Required adapters прямо сейчас: `CLAUDE.md`, `GEMINI.md`. Опциональные (создаются только когда соответствующий runtime реально используется в проекте): Copilot / Cursor / Windsurf / Cline / Aider — список выше.

### Precedence (6 уровней)

При конфликте инструкций — побеждает более локальная, кроме случаев нарушения safety, KB write-back-дисциплины или явной user direction:

1. Explicit user instruction для текущей задачи.
2. Nearest subdirectory `AGENTS.md`.
3. Project root `AGENTS.md`.
4. Hub `~/knowledge/AGENTS.md`.
5. Runtime adapter caveats (`CLAUDE.md`, `GEMINI.md`, …).
6. Personal/global vendor defaults (`~/.claude/CLAUDE.md`, `~/.config/codex/AGENTS.md`, etc.).

**KB wins**: durable KB-факты (`~/knowledge/`, `<project>/knowledge/`) **всегда** побеждают transient runtime memory. Если recall из памяти runtime конфликтует с тем, что написано в файлах — доверяем файлам и обновляем/удаляем устаревшую память.

### Clean-session probe для нового runtime

Прежде чем подключить новый runtime/CLI к проекту, прогнать probe из cwd проекта:

```text
Before doing any work, answer in one paragraph:
1. What is the durable source of truth?
2. Which project instruction file is canonical?
3. Where do you write durable outcomes before stopping?
4. What should you do if your runtime memory conflicts with the KB?
```

Acceptance — ответ должен содержать все эти подстроки:

- hub `~/knowledge/`
- project `knowledge/`
- `AGENTS.md`
- одна durable write-back точка — `log.md`, `backlog.md` или `incidents.md`
- литерал `KB wins`

Если runtime не установлен — `backlog.md` follow-up. Если установлен и не прошёл — incident в `incidents.md`, **rollout не считается завершённым**.

### Onboarding нового runtime

1. Найти native instruction mechanism в официальной документации runtime.
2. Создать тонкий adapter под contract выше **или** сконфигурировать runtime читать `AGENTS.md` напрямую.
3. Добавить строку в KB adapter registry (см. `~/knowledge/concepts/`, если зарегистрирован).
4. Прогнать clean-session probe.
5. Зафиксировать результат в `log.md` проекта.

### Guard

`kb-doctor agent-entrypoint --strict` — детерминированный лит-чек. Проверяет:

- Adapter существует для enabled runtime в проекте.
- Adapter ≤ 30 строк.
- Adapter ссылается на канонический `AGENTS.md`.
- Нет bare `@`-токенов, которые Gemini может принять за file import.
- Нет дубликатов политики между AGENTS.md и адаптером.

Запускается локально и в `kb-doctor` cron-проходе. **Любой свежий P0/P1 — блокер на merge / запись в log.md `rollout completed`.**

### Failure modes

| Сценарий | Симптом | Mitigation |
|----------|---------|-----------|
| Adapter drift | Runtime-файл растёт в отдельную политику | `kb-doctor agent-entrypoint`: adapter-line-cap + content-check |
| Double-load | `CLAUDE.md` и `AGENTS.md` дублируют одни и те же длинные правила | Adapter contract: не дублировать; политика только в AGENTS.md |
| Missing hub master | Project-файлы ссылаются на `~/knowledge/AGENTS.md`, а его нет | Hub-AGENTS.md создан 2026-05-19; doctor проверяет наличие |
| Gemini at-sign import false positive | Bare at-sign + identifier в AGENTS.md интерпретируется как file import | doctor: regex на bare at-sign-токены вне code-fence; экранировать как `` `@`-mention `` |
| Seed/install drift | Live hub OK, но fresh installs ставят старую `CLAUDE.md`-centric схему | `~/knowledge/_template/`, `vepol-prep/_template/`, `install.sh`, `kb-seed-sync`, `kb-bootstrap-manifest` — все покрыты тестами |
| Silent non-loading | Runtime поддерживает AGENTS.md только в некоторых режимах/версиях | clean-session probe при онбординге; incident при провале |
| Precedence ambiguity | Nested файлы или global memory конфликтуют с project rules | Шесть уровней precedence выше; KB wins при конфликте с runtime memory |

## Параллельная оркестрация

Хаб допускает **нескольких оркестраторов одновременно**: Claude Code, Codex, Gemini CLI и будущие CLI-агенты работают не как отдельные «умы», а как разные интерфейсы к **одной и той же** knowledge-системе.

Из этого следуют жёсткие правила:

- Нет отдельной памяти под каждого оркестратора. Источник правды всегда один: `~/knowledge/` и проектные `knowledge/`.
- Любой агент перед работой читает тот же curated context, который читал бы Claude через SessionStart: `README.md`, `state.md`, `index.md`, свежий `log.md`, при необходимости `backlog.md`, `escalations.md`, `incidents.md`, recent `daily/`.
- Любой агент после значимой работы обязан оставить след в той же системе: `log.md` для событий и решений, `state.md` для изменившегося статуса, тематические страницы для нового знания, `incidents.md` для поломок и ручных обходов.
- Если у конкретного инструмента нет автоматических хуков SessionStart/SessionEnd, агент компенсирует это вручную. Отсутствие автоматики не освобождает от дисциплины памяти.
- Цель — **zero split-brain**: любой второй оркестратор должен уметь продолжить работу только по файлам, без доступа к прошлому чату.

## Agent self-identification

«Карточка агента» = одна Markdown-страница, где описана **роль проекта**: что я тут делаю, на чём специализируюсь, какие у меня скиллы, кого зову как сабагентов, чего не делаю. При старте сессии любой оркестратор обязан прочитать эту карточку до первого ответа; на вопрос «кто ты / представься» отвечает по `## Self-introduction` карточки, а не generic-описанием вендора.

Этот раздел — единственный канон конвенции для всех проектов на машине.

### Где живёт карточка

```
<project>/knowledge/agents/agent-card.md   # фиксированное имя
```

- **Одна карточка на проект, не одна на runtime.** Идентичность привязана к роли в проекте, исполнителей может быть несколько (Claude Code, Codex, Gemini CLI, любой будущий runtime).
- Runtime-различия, если важны, идут в `## Operating notes` внутри карточки. Никаких отдельных per-runtime файлов.
- В `index.md` проекта появляется секция `## Agents` с одной ссылкой на `agents/agent-card.md`.
- `AGENTS.md` проекта **не дублирует** карточку — даёт одно-два предложения и ссылается.

### Frontmatter (обязательные поля)

| Поле | Тип | Назначение |
|------|-----|-----------|
| `name` | string (slug) | id проекта/роли в `knowledge/agents/`, lowercase-kebab, совпадает с `<slug>` или `<slug>-<role>` |
| `display_name` | string | человекочитаемое имя роли («vepol-dev orchestrator», не «Claude Code в vepol-dev») |
| `version` | string | semver карточки, **bump patch при любой правке frontmatter** |
| `description` | string | **routing-trigger**, начинается с глагола («Use proactively when…»). Это не лейбл. |
| `role` | string | позиция в команде (одно предложение) |
| `goal` | string | что достигаем (одно предложение) |
| `boundaries` | string[] | чего **не** делает (явные границы) |
| `skills` | array | `id` / `name` / `description` / `tags` — дискретные способности |
| `subagents` | array | `name` / `purpose` — кого зовём (runtime-specific roster — в Operating notes) |
| `tools` | string[] | инструменты, на которые опирается роль |

Опциональные (для будущей A2A-экспортируемости): `provider.organization`, `provider.url`, `url`, `documentation_url`, `capabilities.*`, `security_schemes`, `default_input_modes`, `default_output_modes`.

### Body (обязательные секции, exact-match заголовки)

```markdown
# <display_name>

## Self-introduction
Одно-два предложения от первого лица: «Я — <role>. Я занимаюсь <goal>». Этим текстом агент представляется при старте сессии или явном вопросе «кто ты?». Явно отметить: «карточка одна, исполнителей может быть несколько; runtime-различия — в Operating notes».

## Specialization
3-7 строк: на чём агент специализируется **именно в этом проекте** (не вообще). Что отличает работу здесь от работы в других проектах на машине.

## Skills
Расширение `frontmatter.skills` — по скиллу абзац: триггер, действие, результат.

## Subagents
Кого зовём и на что. Зеркалит `frontmatter.subagents`. Runtime-specific roster — в Operating notes.

## Boundaries
Расширение `frontmatter.boundaries` — почему именно эти границы и что делать вместо.

## Operating notes
Опциональная. Где живут state/log/incidents, проектные привычки, **runtime-specific notes** (что доступно Claude Code, что — Codex, что — Gemini CLI). Если нечего сказать — секция опускается.
```

Контракт: заголовок секции — ровно `## <Name>`, без суффиксов («(детально)», «(опц.)»). Пометки про опциональность — в теле, не в заголовке. Lint-тест: `^## (Self-introduction|Specialization|Skills|Subagents|Boundaries)$`.

### Иерархия при старте сессии (project → baseline → generic)

1. `<project>/knowledge/agents/agent-card.md` — project-level, **выигрывает**.
2. `~/knowledge/agents/agent-card.md` — baseline для машины (fallback). _Опционально, может отсутствовать._
3. Если ни одного нет — generic-описание вендора **с явным указанием** «В этом проекте карточки нет. Завести?».

Политика — **replace, не merge**: если есть project-level, baseline не подмешивается. Merge-семантика — future.

### Multi-orchestrator edit protocol

Карточку правят только агенты (через `@`-mention соответствующего бота в Telegram; человек руками в файл не лезет). Правила:

1. **Append/patch scope.** Правка — точечная (один скилл, одна граница, одно поле). Не переписывание целиком.
2. **Version bump.** При **любой** правке frontmatter — инкремент `version` (semver patch). Это даёт детектируемость конфликта при diff.
3. **Conflict resolution.** Если два оркестратора правят одновременно и файл показывает конфликт — никто не перезаписывает молча. Конфликт фиксируется в `knowledge/incidents.md` строкой `agent-card conflict: <runtime>, <date>, <fields>`, resolution обсуждается человеком или эскалируется в `escalations.md`.
4. **Ownership.** В первой версии нет formal ownership: любой оркестратор может править карточку. Закреплять «Codex владеет X, Claude — Y» — только при появлении реальных конфликтов, не раньше.

### Reliability escalation

Если хотя бы **одна свежая сессия** регрессит (представляется generic-описанием вендора при наличии карточки) — поднимается обязательный SessionStart-hook, читающий `agent-card.md` и кладущий её содержимое в системный контекст до первого turn'а. До регрессии — мастер-правила здесь и в `~/.claude/CLAUDE.md` достаточно.

### Failure modes

| Сценарий | Симптом | Mitigation |
|----------|---------|-----------|
| Карточка отсутствует | Identity-drift | При старте — агент явно говорит «карточки нет, завести?» |
| `description` — лейбл, не trigger | Auto-delegation не работает | Lint `kb-doctor agent-cards` (future): проверка что `description` начинается с глагола |
| Карточка дублирует `AGENTS.md` | Drift между двумя источниками | `AGENTS.md` ссылается на карточку, не дублирует |
| Per-runtime файлы (legacy) | Split-brain между Claude и Codex | Смержить в `agent-card.md`, удалить старые файлы, version bump, запись в `log.md` |
| Карточка привязана к вендору в `display_name` («Codex — X») | Identity ломается при смене runtime | `display_name` = роль проекта; вендор — только в `## Operating notes` |
| Frontmatter ломает YAML | Карточку не прочитать | `python -c "import yaml; yaml.safe_load(open('....md').read().split('---')[1])"` |

### Когда заводить карточку

- Новый проект через `new-wiki` → `knowledge/agents/_example.md` создаётся автоматически. Первый агент при старте сессии видит «карточки нет» → копирует `_example.md` → `agent-card.md`, заполняет под проект, делает commit-в-вику.
- Существующий проект без карточки → агент при первой содержательной задаче спрашивает: «Завести `agent-card.md` сейчас?». Если да — заполняет; если нет — отмечает в `backlog.md`.

## Операции

### Ingest — положить новый источник

1. Прочитать источник целиком.
2. Обсудить ключевые take-aways (не молча).
3. Написать саммари в `knowledge/sources/<slug>.md` с фронтматтером:
   ```yaml
   ---
   title: "..."
   source: "url или путь к raw/"
   date_ingested: 2026-04-13
   type: article|paper|transcript|dataset|image|conversation
   tags: [...]
   ---
   ```
4. Обновить релевантные страницы (entities, concepts, state). Один источник обычно задевает 5–15 страниц.
5. Если источник касается нескольких проектов → обновить ещё и хаб (`~/knowledge/concepts/`, `companies/`, и т.д.).
6. Записать строку в `knowledge/log.md` (локальный + хаб, если кросс-проект).
7. Обновить `knowledge/index.md` если появилась новая страница.

### Query — ответ на вопрос

1. Прочитать `index.md` (сначала локальный, потом хаб, если вопрос кросс-проектный).
2. Можно использовать `~/knowledge/bin/kb-search "<query>"` для быстрого ripgrep по всей базе.
3. Пройти по найденным страницам, прочитать релевантные, проверить раздел «Sources» на устаревание.
4. Ответить с цитатами (`[[wiki-link]]` или путь + якорь).
5. **Если ответ ценный — зафайлить его обратно в вики** как новую страницу (comparison, synthesis, analysis). Не давать знанию уйти в чат-историю.
6. Обновить `log.md`.

### Lint — периодический хелсчек

По команде пользователя («пролинтуй вики»):

- Найти противоречия между страницами.
- Найти orphan pages (нет входящих ссылок).
- Найти упоминания концептов без своей страницы.
- Найти устаревшие claims.
- Предложить вопросы для исследования и источники, которых не хватает.
- Записать отчёт в `log.md` как `lint`-запись.

## Формат лога

Каждая запись начинается с единого префикса — лог должен быть grep-friendly:

```
## [2026-04-13] ingest | <slug> | "Karpathy LLM Wiki gist"
## [2026-04-13] query | <slug> | "как измерять конверсию аутрича"
## [2026-04-13] experiment | <slug> | start | "Cold email v2 с кейсами"
## [2026-04-13] experiment | <slug> | result | "Cold email v2: reply rate 4.2% (было 1.8%)"
## [2026-04-13] lint | <slug> | "3 orphan pages, 1 противоречие"
## [2026-04-13] hub | hub | "Создан хаб ~/knowledge"
```

Быстрый просмотр: `grep "^## \[" ~/knowledge/log.md | tail -20`

## Реестр проектов

`~/knowledge/registry.md` — единый источник правды о том, **какие проекты существуют и где они лежат**. Поля каждой записи:

- slug (kebab-case, используется в симлинках)
- абсолютный путь
- статус вики: `live` / `seeded` / `no-wiki` / `archived`
- категория: `lab` / `pet` / `order` / `personal`
- одна строчка описания
- теги

Реестр обновляется при каждом новом проекте или изменении статуса.

## Кросс-проектный поиск

Два уровня:

1. **Obsidian vault** в `~/knowledge/`. Благодаря симлинкам в `projects/`, поиск и graph view работают через все проекты. Идеально для визуальной навигации и `[[wiki-links]]` через границы проектов.

2. **CLI**: `~/knowledge/bin/kb-search "<query>"` — ripgrep по markdown во всех симлинкнутых проектах + хаб-уровневые файлы. Быстро, без запуска Obsidian.

   Примеры:
   ```
   kb-search "cold email"            # найти все упоминания
   kb-search "reply rate" --project <slug>   # только в одном проекте
   ```

## Языковая конвенция

- **Содержание страниц** — русский.
- **Пути, имена файлов, идентификаторы, теги, frontmatter keys** — английский, kebab-case для файлов, snake_case для тегов.
- **Термины без хороших русских эквивалентов** — оставляем английскими (ICP, funnel, cold outreach, CTR, MCP, …).
- **Код и технические сниппеты** — английские комментарии.

## Что нельзя

- **Никогда не модифицировать `raw/`.** Источники immutable. Если источник плохой — отметить это на соответствующей вики-странице, но не трогать оригинал.
- **Никаких заявлений без источника.** Каждый факт должен иметь ссылку либо на `raw/`, либо на другую вики-страницу с цепочкой к raw.
- **Не писать в вики спекуляции без пометки.** Если это гипотеза — явно `> [!hypothesis]` или в разделе «Open questions».
- **Не дублировать знание между локальной вики и хабом.** Правило: применимо ≥2 проектам → в хаб (`concepts/`, `people/`, `companies/`, `solutions/`). Только одному → локально.
- **Не смешивать код и вики.** Код проекта лежит сиблингами к `knowledge/`, не внутри него.
- **Не создавать страницы «про запас».** Только если есть что сказать прямо сейчас.

## Новый проект

```
~/knowledge/bin/new-wiki <path-to-project> [slug] [category]
```

Что делает:
1. Создаёт в проекте `AGENTS.md`, `GEMINI.md` (из `_template/`) и `knowledge/` со всей структурой (`README.md`, `index.md`, `log.md`, `state.md`, `raw/assets/`, `sources/`).
2. Добавляет симлинк `~/knowledge/projects/<slug>` → `<project>/knowledge`.
3. Вписывает строчку в лог хаба.
4. Просит вручную обновить `registry.md` (описание, статус).

## Спеки агентов vs код агентов

Важная конвенция для AI-проектов (таких как `<slug>`): спеки агентов (markdown) живут в `knowledge/agent-specs/`, а реальный код агентов (Python/TS) — в корне проекта, например `<project>/agents/`. Имена разные, чтобы не сталкиваться. Причина: спеки — это знание (кто что делает, какие промпты, метрики качества), а код — это инструмент. Они эволюционируют с разной скоростью и по разным правилам (знание ingestible, код тестируемый).

## Obsidian

Vault открывается **на уровне `~/knowledge/`**. Благодаря симлинкам в `projects/`, графовое представление и `[[wiki-links]]` работают через все проекты сразу. Код проектов (`node_modules`, `.git`, исходники) физически недоступен через симлинк — мы указываем на `knowledge/`, а не на корень проекта.

Файл `~/knowledge/.obsidian/app.json` содержит `userIgnoreFilters` как дополнительную гигиену.

## Auto-capture сессий (claude-memory-compiler)

В проектах, где уже есть `<project>/knowledge/log.md`, Codex, Claude Code, Gemini CLI сессии **автоматически захватываются** через [coleam00/claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler):

**SessionStart** — хук `~/knowledge/bin/kb-session-start` читает `README.md`, `state.md`, `index.md`, последние 80 строк `log.md` и последние `daily/YYYY-MM-DD.md`, отдаёт как `additionalContext` в новую сессию. Claude начинает работу, уже «помня» контекст проекта.

**SessionEnd / PreCompact** — хуки `kb-session-end` / `kb-pre-compact` экспортят:
- `CLAUDE_KB_DAILY_DIR=<project>/knowledge/daily`
- `CLAUDE_KB_LOG_FILE=<project>/knowledge/log.md`
- `CLAUDE_KB_NO_COMPILE=1`

Делегируют в `~/claude-memory-compiler/hooks/session-end.py` (upstream), который парсит transcript и спавнит `flush.py` (патчен) фоновым процессом. Flush вызывает Claude Agent SDK (`~$0.02-0.05`), извлекает Context / Decisions / Lessons / Action Items из сессии, и пишет:

1. **Полный extract** → `<project>/knowledge/daily/YYYY-MM-DD.md` (append, one `### Session (HH:MM)` per session)
2. **Одну строку** → `<project>/knowledge/log.md` в формате `## [YYYY-MM-DD HH:MM] session | <summary>` + `Details: [[daily/YYYY-MM-DD]]`

**Что не трогается:** `state.md`, `index.md`, `raw/`, категории (icp/, offers/, channels/, ...) — всё это курируется человеком. `daily/` — raw material, пользователь читает его и сам лифтит важное в категории.

**Opt-in:** существование `<project>/knowledge/log.md` (= вика заведена).
**Opt-out:** `touch <project>/.kb-ignore` — хуки тихо пропустят.

**Patch checklist** (при `git pull` в `~/claude-memory-compiler/`):
1. `scripts/flush.py::maybe_trigger_compilation()` — первая строка `if os.environ.get("CLAUDE_KB_NO_COMPILE"): return`.
2. `scripts/flush.py::append_to_daily_log()` — ветка для `CLAUDE_KB_DAILY_DIR` + cross-ref в `CLAUDE_KB_LOG_FILE`.
3. `scripts/flush.py::main()` — не вызывает `append_to_daily_log` для FLUSH_OK/FLUSH_ERROR когда `CLAUDE_KB_DAILY_DIR` установлен.

**Наблюдение и дебаг:**
- Лог хука: `~/claude-memory-compiler/scripts/flush.log`
- Содержит: `SessionEnd fired`, `Spawned flush.py`, `Result: saved (N chars)`

## Git и вика

**Правило: `knowledge/` НЕ должна трекаться git ни в одном проекте.**

Причины:
- Dailies могут содержать sensitive session-транскрипты
- Вика меняется независимо от кода (log.md обновляется каждую сессию)
- Шум в PR / diff
- Obsidian — это «второй мозг», а не часть кодовой базы

**Конвенция:** в каждом проекте где есть `knowledge/`, `.gitignore` содержит:
```
knowledge/
.kb-ignore
```

Скрипт `bin/new-wiki` **автоматически** добавляет эти строки в `.gitignore` при создании новой вики. Для проектов, где вика заводилась до этого правила — руками добавить.

Если нужна версионирование вики — делать это отдельно (например, `~/knowledge/` может быть своим git-репо, отдельно от проектов).

## Точки расширения

- `~/knowledge/bin/` — можно добавлять CLI-утилиты.
- `raw/` на уровне хаба — для источников, не относящихся ни к одному проекту (общие книги, фундаментальные статьи).
- При росте >100 источников — подключить [qmd](https://github.com/tobi/qmd) (BM25+vector над markdown).
- **Phase 2 для compiler:** подключить `compile.py` для генерации `concepts/`, `connections/`, `qa/` когда daily-captures накопятся и станет ясно, что конкретно хочется компилировать. Потребует кастомизации промпта чтобы не переписывать user's `index.md`.

## Research via Grok (chrome-devtools-mcp)

При research-задачах, где **ценен first-party доступ к X (Twitter) и Reddit** — обсуждения, мнения комьюнити, sentiment, свежие реакции — открывай `https://grok.com/` через MCP-сервер `chrome-devtools`, подключённый к **живому пользовательскому Chrome**, где человек уже залогинен в Grok. Grok первоначально настроен на X+Reddit и читает их живьём; обычные web-tool'ы туда не дотягиваются.

### Important research quorum

Для важных ресерчей используй quorum-pipeline: независимые pass-ы Claude Code + Codex + Gemini CLI когда доступны, **обязательный Grok pass через Chrome DevTools**, затем KB-синтез и только после этого NotebookLM audio. Каноническая процедура: `~/knowledge/concepts/important-research-quorum-pipeline.md`.

Каждый pass пишет durable note в `knowledge/sources/`; итоговый synthesis — в `knowledge/reports/`. NotebookLM — финальный production step для audio, не замена research quorum. Если Grok недоступен, important research blocked/degraded и требует явного waiver пользователя.

**Когда вызывать:**
- «что обсуждают про X», «что говорят в комьюнити», «какие реакции на Y»
- любая research-задача с упоминанием X/Twitter/Reddit
- когда нужна актуальность (последние дни/недели)

**Когда НЕ вызывать:**
- ответ есть в коде / документации / git history
- технический вопрос без community-сентимент-компонента
- быстрый факт, на который хватит обычного web search

**Connection rule (исправлено 2026-05-19):**

- Не использовать Codex in-app browser для Grok research.
- Не позволять `chrome-devtools-mcp` запускать новый Chrome/default profile. Новый profile вроде `~/.cache/chrome-devtools-mcp/chrome-profile*` не содержит пользовательского Grok-login и может получить `x.ai` block page: "Sorry, you have been blocked".
- Использовать уже живой пользовательский Chrome, где человек руками залогинен в `https://grok.com/`.
- `chrome-devtools-mcp` должен подключаться к этому Chrome через `--autoConnect` (validated on this machine) или через `--browserUrl http://127.0.0.1:9222` когда `/json/version` реально отдаёт DevTools discovery JSON, а не создавать отдельный browser profile.
- Целевая поверхность всегда `https://grok.com/`, не прямой `x.ai`.

**Recipe (валидирован 2026-05-19 на Chrome 148):**

Пользователь один раз включает remote debugging — `chrome://inspect/#remote-debugging` → галка «Allow remote debugging for this browser instance» → сервер слушает `127.0.0.1:9222`. После этого:

1. Убедись, что MCP args содержат `--autoConnect` или working `--browserUrl http://127.0.0.1:9222`. Для Claude/Codex/Gemini предпочтительный config на этой машине: `npx -y chrome-devtools-mcp` с актуальной npm-версией, `--autoConnect` и `--experimentalPageIdRouting`.
2. Smoke: `lsof -nP -iTCP:9222 -sTCP:LISTEN` должен показать `Google Chrome`, а MCP Inspector `tools/call list_pages` через `chrome-devtools-mcp` с `--autoConnect` должен увидеть `https://grok.com/`. Не полагайся только на `/json/version`: у текущего Chrome remote-debug endpoint он отдаёт `404`, из-за чего `--browserUrl` падает, хотя `--autoConnect` работает.
3. `navigate_page` → `https://grok.com/` (идемпотентно).
4. `take_snapshot` → найди composer в a11y tree. На grok.com он может быть `textbox "Ask Grok anything"` или `generic value="..."`; всегда работай по свежему snapshot.
5. `fill` с найденным `uid` и текстом промпта.
6. `take_snapshot` ещё раз → submit-кнопка появляется только когда React state видит текст.
7. `click` по submit uid или `requestSubmit()` только если UI-кнопка не экспонируется.
8. Подожди 15-60 сек (long thinking — 6s+ только Grok'овский CoT). `evaluate_script` → `document.querySelectorAll('[data-testid="assistant-message"]')` → последний `.textContent`. Стрипай CoT-prefix `/^Размышление на протяжении \d+\s*s/` (русск.) или `/^Thinking for \d+\s*s/` (англ.).

**Архив:** старый локальный Chrome-extension prototype + MCP-bridge был superseded этим recipe — chrome-devtools-mcp решает ту же задачу через trusted Puppeteer events, отдельный bridge в pipeline не нужен. Prototype оставлен только как architectural reference + DOM-probe knowledge о grok.com selectors.
