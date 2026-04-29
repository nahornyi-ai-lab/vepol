---
name: init-kb
description: Bootstrap a personal knowledge base (knowledge/ wiki) in the current project and register it in the global hub at ~/knowledge/. Use this skill when the user says "заведи вику", "заведи базу знаний", "создай вику", "init knowledge base", "bootstrap wiki", "setup wiki here", "нужна вика", "/init-kb", or indicates they want to start using the personal knowledge system in the current project. The skill analyzes the project, proposes a slug/category/description, confirms with the user, and creates the full knowledge/ structure + hub registration + .gitignore rules + hub symlink.
---

# init-kb — инициализация базы знаний в проекте

Заводит локальную `knowledge/` вику в текущем проекте по мастер-схеме `~/knowledge/CLAUDE.md` и синхронизирует с хабом. После этого проект автоматически начнёт получать SessionStart-инжект контекста и SessionEnd-захват сессий через claude-memory-compiler (хуки уже установлены глобально).

## Когда запускать

- Пользователь явно просит: «заведи вику», «создай базу знаний», «init-kb», «/init-kb», «нужна вика здесь»
- Пользователь работает в проекте, где ещё нет `knowledge/log.md`, и хочет начать системно собирать знание

## Когда НЕ запускать

- В `knowledge/log.md` уже существует → вика заведена, skill должен остановиться и сообщить об этом
- `cwd` — это `$HOME`, `/tmp`, системная папка — откажи и попроси у пользователя корректный путь проекта
- Пользователь случайно упомянул «вика» в другом контексте без явного намерения инициализировать

## Пошаговая процедура

### Шаг 1. Проверки preconditions

1. Определи `cwd` через `pwd` (Bash).
2. Если `cwd/knowledge/log.md` уже существует — **остановись**, сообщи пользователю «вика уже заведена», покажи путь, предложи вместо этого редактировать/дополнять существующую. Не запускай skill.
3. Если `cwd` == `$HOME` или `/tmp` или системная папка (`/usr`, `/opt`, `/etc`) — остановись, попроси у пользователя корректную папку проекта.

### Шаг 2. Анализ проекта

Прочитай ключевые файлы проекта, чтобы понять, что это за проект:

- `README.md` (если есть) — описание проекта
- `CLAUDE.md` (если есть) — может содержать локальные инструкции
- `package.json` — стек (Next.js, React, Vue, Node библиотека, ...)
- `pyproject.toml` / `requirements.txt` — Python проект
- `Cargo.toml` — Rust
- `go.mod` — Go
- `.git/config` (через `cat`) — remote URL → имя репо, организация
- Топ-уровневая структура через Glob или ls — что там за папки (src/, components/, api/, ...)

Сформируй краткое понимание: **«Это <тип> проект на <стеке>, делает <что>»** — 1-2 предложения.

### Шаг 3. Диалог с пользователем

Покажи пользователю:

1. **Найденное понимание** — «Вижу: это Next.js лендинг <work>. Правильно?»
2. **Предложение slug** — по умолчанию `basename($cwd)` в kebab-case
3. **Предложение категории**:
   - Если путь содержит `<work-container>/projects/` → `order` (клиентский заказ)
   - Если путь содержит `<work-container>/` (но не `projects/`) → `lab` (рабочий проект лаборатории)
   - Если путь содержит `PetProjects/` → `pet`
   - Иначе → `personal`
4. **Предложение описания** — 1-2 предложения (пользователь правит)
5. **Предложение категорий вики** (подпапки в `knowledge/`):
   - **Next.js / веб-лендинг**: `features`, `pages`, `components`, `decisions`, `experiments` (A/B тесты)
   - **Лидген проект**: `icp`, `offers`, `channels`, `funnel`, `metrics`, `experiments`, `agent-specs`
   - **Библиотека / SDK**: `api`, `patterns`, `decisions`, `changelog-notes`
   - **Бот / интеграция**: `integrations`, `flows`, `decisions`
   - **Исследовательский**: `experiments`, `findings`, `hypotheses`
   - **Клиентский заказ**: `requirements`, `meetings`, `deliverables`, `decisions`
   - **ML / Data**: `datasets`, `models`, `experiments`, `metrics`
   - **Минимальный (по умолчанию если не ясен тип)**: только `sources/` (уже создаётся) + `experiments/`

Пользователь может принять всё как есть, убрать лишнее, добавить своё.

### Шаг 4. Создание структуры через bash `new-wiki`

Когда пользователь подтвердил, вызови Bash:

```bash
bash ~/knowledge/bin/new-wiki "<absolute-project-path>" <slug> <category>
```

Это создаст:
- `<project>/CLAUDE.md`
- `<project>/knowledge/README.md`, `index.md`, `log.md`, `state.md`
- `<project>/knowledge/raw/assets/`, `sources/`, `daily/`
- Обновит `<project>/.gitignore` (добавит `knowledge/` и `.kb-ignore`)
- Создаст симлинк `~/knowledge/projects/<slug>` → `<project>/knowledge`
- Append запись в `~/knowledge/log.md`

### Шаг 5. Создать дополнительные категории

`new-wiki` создаёт только базовые папки. Для выбранных пользователем категорий сделай:

```bash
mkdir -p "<project>/knowledge/icp" "<project>/knowledge/offers" "<project>/knowledge/channels" ...
touch "<project>/knowledge/icp/.gitkeep" ...
```

### Шаг 6. Заполнить реальное содержание (через Edit/Write)

`new-wiki` создаёт файлы из шаблонов с плейсхолдерами. Замени их на реальное содержание:

1. **`<project>/knowledge/README.md`** — Edit: убрать плейсхолдер описания, вставить твой анализ из Шага 2 (1-2 предложения: что это, для кого, в каком статусе)
2. **`<project>/knowledge/state.md`** — Edit: «Одной строкой» → твоя оценка статуса. Остальное оставить как в шаблоне (пусто).
3. **`<project>/CLAUDE.md`** — Edit: раздел «О проекте» → реальное описание; раздел «Категории» → перечисление выбранных категорий.

### Шаг 7. Обновить хаб

1. **`~/knowledge/registry.md`** — Edit: найти секцию соответствующую категории (`## lab — <work>`, `## order — клиентские заказы`, `## pet — PetProjects`, или `## personal / прочее`). Найти таблицу `| slug | статус | путь | описание |`. Добавить новую строку:
   ```
   | <slug> | seeded | `<relative-path-from-home>` | <описание из README> |
   ```

2. **`~/knowledge/index.md`** — Edit: найти раздел `## Проекты с живой вики`. Добавить буллет:
   ```
   - **[<slug>](projects/<slug>/README.md)** — <описание>
   ```

### Шаг 8. Итоговое подтверждение

Покажи пользователю:
- Что создано (список путей)
- Где запись в хабе
- Симлинк работает
- Next steps:
  1. «Открой или перезапусти Claude Code в `<project>` — SessionStart автоматически подтянет README/state/log в контекст»
  2. «Начни работать — SessionEnd сам запишет сессию в `knowledge/daily/` + строку в `log.md`»
  3. «По мере работы заполни `state.md` и специфичные категории»

## Автоматизация после bootstrap

Как только skill завершён, дальше всё автоматически через уже установленные хуки (`~/.claude/settings.json`):

- **SessionStart** — `kb-session-start` читает `<project>/knowledge/README.md`, `state.md`, `index.md`, tail `log.md`, recent `daily/*.md` → инжектит в контекст. Claude стартует с знанием о проекте.
- **SessionEnd / PreCompact** — `kb-session-end` / `kb-pre-compact` делегируют в patched `flush.py` → извлекает decisions/lessons/actions через Claude Agent SDK → пишет в `<project>/knowledge/daily/YYYY-MM-DD.md` + 1 строка cross-reference в `log.md`.

Пользователь ничего дополнительного не делает. Просто работает в проекте.

## Правила edge cases

- **Nested project** (например, `parent-project/sub-project/`) — **ок**, такая вложенность допустима. Каждый проект получает свою `knowledge/`, хуки выбирают правильную по `cwd`. Не путай эти wiki, они независимы.
- **Уже есть `.gitignore`** — `new-wiki` append'ит новые строки, не перезаписывая. Безопасно.
- **Уже существует симлинк** в хабе с тем же slug — `new-wiki` предупредит и не перезапишет. Если это коллизия с другим проектом — предложи пользователю другой slug.
- **Проект без git** (нет `.git/`) — ок, `.gitignore` всё равно создаётся preemptively.
- **Пользователь отказался на любом шаге** — остановись, не создавай частичных структур. Если что-то уже создано — откати: удали созданные файлы и симлинк, убери запись из хаба.

## Финальное напоминание

После запуска skill'а сразу проверь, что всё действительно на месте — `ls` по ключевым путям. Не полагайся на «вроде должно быть». Если что-то пошло не так — почини или откати перед тем как вернуть управление пользователю.
