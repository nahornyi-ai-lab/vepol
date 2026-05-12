# Multibot operations runbook

Стандартные операции для multibot-agent-runtime (см. [concepts/multibot-agent-runtime.md](concepts/multibot-agent-runtime.md)).

## Пять команд

```
kb-multibot-setup       # одноразовая первичная настройка (auth + group)
kb-multibot-supervisor  # main daemon (под LaunchAgent, не зовём вручную)
kb-multibot-add         # добавить агента с уже созданным ботом
kb-multibot-remove      # деактивировать агента
kb-multibot-list        # показать состояние всех агентов
```

---

## Добавить агента

**Условие:** проект уже существует, у него есть `<project>/knowledge/` + `.orchestration.yaml`. Если нет — сначала `init-kb`.

1. **Создать бота в @BotFather:**
   - `/newbot` → display name → username
   - `/setprivacy` → Disable
   - `/setjoingroups` → Enable
   - Скопировать token формата `12345:ABC...`

2. **Зарегистрировать одной командой:**
   ```bash
   kb-multibot-add 12345:ABC...
   ```
   Скрипт авто-определит:
   - бота (через `getMe`)
   - slug (из `bot_username`)
   - workdir (через `projects/<slug>` симлинк)
   - parent (из existing yaml, default `hub`)

   Дополнительно делает:
   - сохраняет токен в `~/.claude/channels/bots/<slug>.env` (chmod 600)
   - пишет `telegram:` блок в `.orchestration.yaml`
   - добавляет бота в группу через Telethon (best-effort)
   - `enabled: true` по умолчанию (production rollout)
   - kickstart supervisor (подхватит нового агента)

3. **Если slug не вывелся** автоматически (например username не содержит slug проекта):
   ```bash
   kb-multibot-add 12345:ABC... --slug my-project
   ```

4. **Проверить:**
   ```bash
   kb-multibot-list
   ```
   Должна появиться новая строка с `enabled=True, token=present`.

5. **Тест** в группе `<your_group>`:
   ```
   @<bot_username> привет
   ```
   Должна прийти реакция 👀 → ответ ботом через 5–30 сек.

---

## Удалить агента

**Три уровня:**

```bash
# soft — supervisor перестаёт вызывать, бот остаётся в группе и на диске
kb-multibot-remove <slug>

# medium — также кикаем бота из группы
kb-multibot-remove <slug> --kick

# hard — также архивируем токен (token не удаляется навсегда, перемещается в _archive/)
kb-multibot-remove <slug> --archive
```

Все варианты делают kickstart supervisor автоматически.

**Полное удаление бота на стороне Telegram** — только вручную через `@BotFather` → `/deletebot`. Скрипт это НЕ делает (требует подтверждения от человека).

---

## Посмотреть состояние

```bash
kb-multibot-list                 # таблица всех
kb-multibot-list --only-enabled  # только активные
kb-multibot-list --json          # для скриптов
```

Колонки: slug, bot, parent, enabled, token (present/missing), last_run.

---

## Troubleshooting

### Supervisor не отвечает в группе

1. Проверить процесс:
   ```bash
   launchctl list com.knowledge.multibot-supervisor
   ```
   Если `LastExitStatus != 0` — посмотреть лог:
   ```bash
   tail -50 ~/knowledge/logs/multibot-supervisor.err.log
   ```

2. Полный рестарт:
   ```bash
   launchctl kickstart -k gui/$(id -u)/com.knowledge.multibot-supervisor
   ```

3. Если совсем не стартует — проверить конфиг:
   ```bash
   kb-multibot-supervisor --check
   ```

### Telethon session invalid

Если в логах `SessionPasswordNeededError` или auth errors:

```bash
kb-multibot-setup --auth   # повторная авторизация
launchctl kickstart -k gui/$(id -u)/com.knowledge.multibot-supervisor
```

### Бот не отвечает (но supervisor работает)

1. `kb-multibot-list` — `enabled: true`?
2. Бот действительно в группе? Открой Telegram → группа → members.
3. Был ли spawn?
   ```bash
   ls -lt ~/.orchestrator/multibot/runs/ | head
   ```

### BotFather hit creation cap

Hard cap: 20 ботов (free) / 40 (Premium). Решения:
- `/mybots` → удалить неиспользуемых
- Telegram Premium ($5/мес) → 40 cap
- Создать ботов с другого user-account (токены portable)

---

## Файлы

```
~/.orchestrator/multibot.env                 # TG_API_ID/HASH/group_chat_id
~/.orchestrator/multibot-supervisor.session  # Telethon session
~/.orchestrator/multibot/queues/<slug>.json  # очередь задач per agent
~/.orchestrator/multibot/runs/<run_id>.json  # active + recent runs
~/.orchestrator/multibot/watchdog/<slug>.lock # flock
~/.orchestrator/multibot/cache/<chat>.json   # rolling buffer
~/.claude/channels/bots/<slug>.env           # bot tokens (0600)
~/.claude/channels/bots/_archive/            # архив токенов после --archive
~/Library/LaunchAgents/com.knowledge.multibot-supervisor.plist
~/knowledge/logs/multibot-supervisor.{out,err}.log
```
