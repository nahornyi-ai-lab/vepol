# Multibot operations runbook

Standard operations for the multibot agent runtime (see [methodology/multibot-agent-runtime.md](methodology/multibot-agent-runtime.md)).

## Five commands

```
kb-multibot-setup       # one-time first setup (auth + group)
kb-multibot-supervisor  # main daemon (runs under a LaunchAgent; you don't call it by hand)
kb-multibot-add         # add an agent whose bot already exists
kb-multibot-remove      # deactivate an agent
kb-multibot-list        # show the state of all agents
```

---

## First-time setup

1. **Telegram credentials, login and group:**
   ```bash
   kb-multibot-setup
   ```
   It asks for `TG_API_ID` and `TG_API_HASH` (from my.telegram.org → API development tools), logs in with Telethon (Telegram sends you a code), asks for the group's @username or invite link, and writes `~/.orchestrator/multibot.env` (chmod 600). `kb-multibot-setup --check` shows the current state without changing anything.

2. **Install the LaunchAgent.** `install.sh` does not install this one. From your Vepol checkout:
   ```bash
   sed "s|__HOME__|$HOME|g" launchd/com.knowledge.multibot-supervisor.plist.template \
     > ~/Library/LaunchAgents/com.knowledge.multibot-supervisor.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.knowledge.multibot-supervisor.plist
   ```

> **Long runs are stopped.** A run that prints nothing for `watchdog_silence_sec` (900 seconds by default) is stopped, and `claude -p --output-format json` prints nothing until it finishes. For an agent that runs long jobs, set `watchdog_silence_sec` in the `telegram:` block of its `.orchestration.yaml` to more than its longest expected run. A stop, from the watchdog or `/stop`, signals only that agent's own process. Details: [status of the code](methodology/multibot-agent-runtime.md#status-of-the-code).

---

## Add an agent

**Prerequisite:** the project already exists and has `<project>/knowledge/` + `.orchestration.yaml`. If not, run `/init-kb` in the project first.

1. **Create the bot in @BotFather:**
   - `/newbot` → display name → username
   - `/setprivacy` → Disable
   - `/setjoingroups` → Enable
   - Copy the token, format `12345:ABC...`

2. **Register it with one command:**
   ```bash
   kb-multibot-add 12345:ABC...
   ```
   The script works out on its own:
   - the bot (through `getMe`)
   - the slug (from `bot_username`)
   - the workdir (through the `~/knowledge/projects/<slug>` symlink)
   - the parent (from the existing yaml; default `hub`)

   It also:
   - saves the token to `~/.claude/channels/bots/<slug>.env` (chmod 600)
   - writes the `telegram:` block in `.orchestration.yaml`
   - adds the bot to the group through Telethon (best-effort; `--no-group-add` skips it)
   - sets `enabled: true` by default (production rollout; `--no-enable` registers the agent disabled)
   - restarts the supervisor so it picks up the new agent (`--no-kickstart` skips it)

3. **If the slug is not inferred** automatically (for example, the username does not contain the project slug):
   ```bash
   kb-multibot-add 12345:ABC... --slug my-project
   ```

4. **Check:**
   ```bash
   kb-multibot-list
   ```
   A new row should appear with `enabled` = `True` and `token` = `present`.

5. **Test** in the `<your_group>` group:
   ```
   @<bot_username> hello
   ```
   You should get a 👀 reaction, then a reply from the bot within 5–30 s.

---

## Remove an agent

**Three levels:**

```bash
# soft — the supervisor stops calling the agent; the bot stays in the group and on disk
kb-multibot-remove <slug>

# medium — also kick the bot from the group
kb-multibot-remove <slug> --kick

# hard — also archive the token (it is not deleted for good; it moves to _archive/)
kb-multibot-remove <slug> --kick --archive
```

`--kick` and `--archive` are independent; combine them as you need. `--kick` works for supergroups; in a basic group, remove the bot by hand.

Every variant restarts the supervisor automatically (`--no-kickstart` skips it).

**Deleting the bot fully on the Telegram side** — only by hand, through `@BotFather` → `/deletebot`. The script does NOT do this (it needs a human to confirm).

---

## Check the state

```bash
kb-multibot-list                 # table of all agents
kb-multibot-list --only-enabled  # active agents only
kb-multibot-list --json          # for scripts
```

Columns: slug, bot, parent, enabled, token (present/missing), last_run. `--json` also includes `children`.

---

## Troubleshooting

### The supervisor does not answer in the group

1. Check the process:
   ```bash
   launchctl list com.knowledge.multibot-supervisor
   ```
   If `LastExitStatus` is not 0, read the log:
   ```bash
   tail -50 ~/knowledge/logs/multibot-supervisor.err.log
   ```

2. Full restart:
   ```bash
   launchctl kickstart -k gui/$(id -u)/com.knowledge.multibot-supervisor
   ```

3. If it does not start at all, check the config:
   ```bash
   kb-multibot-supervisor --check
   ```

### Telethon session invalid

If the logs show `SessionPasswordNeededError` or auth errors:

```bash
kb-multibot-setup --auth   # log in again
launchctl kickstart -k gui/$(id -u)/com.knowledge.multibot-supervisor
```

### A bot does not answer (but the supervisor runs)

1. `kb-multibot-list` — is `enabled` true?
2. Is the bot really in the group? Open Telegram → the group → members.
3. Was there a spawn?
   ```bash
   ls -lt ~/.orchestrator/multibot/runs/ | head
   ```

### BotFather hit the creation cap

Hard cap: 20 bots (free) / 40 (Premium). Options:
- `/mybots` → delete bots you no longer use
- Telegram Premium ($5/month) → 40 cap
- Create bots from another user account (tokens are portable)

---

## Files

```
~/.orchestrator/multibot.env                 # TG_API_ID, TG_API_HASH, KB_MULTIBOT_GROUP_CHAT_ID
~/.orchestrator/multibot-supervisor.session  # Telethon session
~/.orchestrator/multibot/queues/<slug>.json  # task queue per agent
~/.orchestrator/multibot/runs/<run_id>.json  # active + recent runs
~/.orchestrator/multibot/watchdog/<slug>.lock # flock
~/.orchestrator/multibot/cache/<chat>.json   # rolling buffer (reserved; the cache lives in memory)
~/.claude/channels/bots/<slug>.env           # bot tokens (0600)
~/.claude/channels/bots/_archive/            # tokens archived by --archive
~/Library/LaunchAgents/com.knowledge.multibot-supervisor.plist
~/knowledge/logs/multibot-supervisor.{out,err}.log
```
