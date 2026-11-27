# Your daily routine

Turn on scheduled tasks, and Vepol runs your day without being asked. Early
each morning, after a one-time setup, your project pages are brought up to
date. Then a one-minute brief arrives in Telegram, followed by a review of new
arXiv papers and an optional audio version. In the evening a short retro
arrives. You set it all
up in one readable file, `~/knowledge/personal/processes.yaml`. Every run
leaves a plain-text record you can open.

This page covers everything that runs on a schedule. It explains how to switch
each routine on, what it needs from you, and where to look when something does
not arrive.

Commands assume `~/knowledge/bin` is on your PATH
(`export PATH="$HOME/knowledge/bin:$PATH"`). If it is not, type the full path,
for example `~/knowledge/bin/kb-brief`.

## At a glance

| Time | What you get | What it needs |
|---|---|---|
| 06:30 | Project `state.md` pages refreshed from what was logged since the last pass | A one-time `kb-rebuild-registry` run ([details](#nightly-state-refresh)) |
| 07:15 | New mail read and sorted, read-only | Gmail connected in Codex |
| about 07:30–07:50 | **Morning brief** in Telegram | A Telegram bot |
| after the brief | **arXiv learning digest**: up to three new papers explained in your language | A Telegram bot |
| after the digest | **Morning audio**: the brief, the arXiv report and Money Radar as one listen | NotebookLM login, or local Qwen voice |
| 20:30 | Evening mail check | Gmail connected in Codex |
| about 20:45 | **Evening retro** in Telegram | A Telegram bot |
| after the retro | Evening audio of the retro | NotebookLM login, or local Qwen voice |
| off until you switch it on | Money Radar, daily research on a schedule, follow-up reminders, people proposals | See each section |

Vepol checks the schedule every 15 minutes. A step starts on the first check
after its time comes, or after the step it waits for has succeeded. If your Mac
is asleep at that moment, the step runs on the first check after it wakes.
Times follow your Mac's clock.

## Turn on scheduled tasks

Answer **yes** to `Install scheduled tasks?` when you run `./install.sh`. If you
said no, run `./install.sh` again from the repository and say yes; your hub and
files are kept. An agent-driven install turns them on with
`VEPOL_ENABLE_LAUNCHD=1 ./install.sh --apply`.

This adds four LaunchAgents to `~/Library/LaunchAgents`:

| LaunchAgent | What it does |
|---|---|
| `com.knowledge.tick` | Every 15 minutes, runs whatever in `processes.yaml` is due. This is the scheduler. |
| `com.knowledge.planner` | At 00:05, starts a fresh day record in `~/knowledge/logs/today-plan.json`, which tracks what has run today. |
| `com.knowledge.people-review-bot` | Listens for your taps on people-review buttons in Telegram. It stays idle until both Telegram values are set. |
| `com.knowledge.orchestrator-cycle` | Experimental, at 07:30 and 20:45: a multi-project planning and retro cycle. Until `~/knowledge/hierarchy.yaml` exists (see [Nightly state refresh](#nightly-state-refresh)), it logs one line and stops. Once it exists, the 20:45 run also starts the evening retro, adds a cycle summary to the day's note and drafts tomorrow's plan in `daily-plan/`. Project work runs only for projects you opt in with `cycle_enabled: true`. |

The routines need at least one signed-in agent CLI. Claude Code is enough.
The brief and the retro try Codex first and switch to Claude Code by themselves
when Codex is rate-limited, logged out or missing. Mail needs Codex. Vepol
finds both CLIs in `~/.local/bin`, Homebrew and npm locations, even under
launchd.

Everything you get is written in the language set in
`~/knowledge/personal/profile.yaml` (`language: en`, `es`, `de`, …). Change it
any time; the next run uses it.

## Set up Telegram

Telegram is the only delivery channel today. The brief, the retro, the
digests, the follow-up reminders and the people-review buttons all come
through one bot that you create. It takes five minutes.

1. In Telegram, open a chat with **@BotFather**, send `/newbot` and follow the
   prompts. BotFather replies with a token that looks like
   `123456789:AAH…`.
2. Open a chat with your new bot and send it any message, for example `hi`.
   A bot cannot write to you until you have written to it.
3. In a browser, open
   `https://api.telegram.org/bot<token>/getUpdates`, with your token in place
   of `<token>`. Find `"chat":{"id":` in the reply. The number after it is
   your chat id.
4. Open `~/knowledge/personal/.secrets` (the installer created it with mode
   600) and fill in both lines, replacing the placeholders:

   ```
   TELEGRAM_BOT_TOKEN=<token from BotFather>
   TELEGRAM_CHAT_ID=<your chat id>
   ```

   Find the chat id before you save both values. Within about five minutes
   of saving both, Vepol's people-review listener starts reading the bot's
   updates, and the browser page stops showing them.
5. Send yourself a test message:

   ```bash
   kb-channel-send test "Hello from Vepol"; echo $?
   ```

   `0` means it arrived. `3` means a value is still empty. `4` means the send
   failed: check the token, the chat id, and that you messaged the bot first.

Vepol reads `.secrets` as plain data, never runs it as a script, and passes
the token to Telegram without putting it on a command line. Older setups that
use `TELEGRAM_TOKEN` still work; `TELEGRAM_BOT_TOKEN` wins when both are set.
Two optional lines personalize the brief and retro: `USER_NAME=` and
`USER_CITY=`.

**Use a separate bot for Claude Code's Telegram plugin.** The plugin, which
lets you chat with Claude Code from Telegram, keeps its token in
`~/.claude/channels/telegram/.env`. Telegram lets only one program read a
bot's incoming messages at a time. If the plugin and Vepol's review listener
share one bot, they keep knocking each other off. Create a second bot for the
plugin.

### Without Telegram

Nothing breaks. Each routine still does its work and saves the result under
`~/knowledge`; it just is not sent:

- The morning brief is saved to `~/knowledge/briefs/<date>.md` with
  `delivery: not_configured`: nothing was sent and nothing was tried. A manual
  `kb-brief` says it was saved and not delivered, and names the two settings
  to fill in.
- The retro is added to the same day file.
- The arXiv digest, Money Radar and daily research keep their reports on disk.
- Steps that wait on these still run.

After you add Telegram, run `kb-brief`, `kb-retro` or `kb-learning-arxiv
--text-only` the same day. Each one sends what was already saved, with no new
model call; the brief's day file then says `delivery: telegram_ok`. Follow-up
reminders are the exception: they exist only as a Telegram message. When
contacts are due, `people-remind` keeps retrying until Telegram is set.

## The schedule

`~/knowledge/personal/processes.yaml` is the one switchboard. Each routine is
a block of five fields:

```yaml
- id: daily
  enabled: true
  when: after:mail-morning
  run: kb-brief
  outputs: [telegram, file]
```

- `id`: a name in lowercase letters, digits and hyphens, starting with a
  letter.
- `enabled`: `true` or `false`.
- `when`: a time like `"07:15"`, `after:<id>` to run once another step has
  succeeded today, or `on-demand` to never run on a schedule.
- `run`: a command from `~/knowledge/bin`, or an absolute path.
- `outputs`: where results go: `telegram`, `file`, `people`, `calendar`, plus
  `notebooklm_audio` or `telegram_audio` for the two audio digests only.

An optional sixth field, `timeout: <seconds>` (60 to 7200), gives a slow step
more than the default 30 minutes.

The installer writes this file once. Upgrades never overwrite it, so your
changes stay. If the file goes missing, the next check writes the defaults
again.

### Default steps

| `id` | When | Runs | On by default | What it does |
|---|---|---|---|---|
| `consolidate` | `06:30` | `kb-consolidate` | yes | [Nightly state refresh](#nightly-state-refresh) of each project's `state.md` |
| `child-rollup` | `07:00` | `kb-child-rollup` | yes | Copies each sub-project's summary into its parent project's `state.md`, with no model. Matters only if you nest projects. |
| `mail-morning` | `07:15` | `kb-mail-brief --period morning --write` | yes | Reads new mail for the brief ([Mail](#mail)) |
| `daily` | `after:mail-morning` | `kb-brief` | yes | [Morning brief](#morning-brief) |
| `mail-evening` | `20:30` | `kb-mail-brief --period evening --write` | yes | Reads new mail for the retro |
| `retro` | `after:mail-evening` | `kb-retro` | yes | [Evening retro](#evening-retro) |
| `learning` | `after:daily` | `kb-learning-arxiv --text-only` | yes | [arXiv learning digest](#arxiv-learning-digest) |
| `morning-digest` | `after:learning` | `kb-morning-digest` | yes | [Morning audio](#audio-digests) |
| `evening-digest` | `after:retro` | `kb-morning-digest --period evening` | yes | [Evening audio](#audio-digests) |
| `telegram-people` | `after:retro` | `kb-telegram-people --hub ~/knowledge --quiet` | no | Notes who wrote to you in private Telegram chats ([People](#people-reminders-and-proposals)) |
| `people-extract` | `after:retro` | `kb-extract-people --hub ~/knowledge --no-llm --quiet` | no | Proposes new people for review |
| `entity-rollup` | `after:people-extract` | `kb-entity-rollup` | no | Experimental: rolls company and asset mentions up from logs; needs the experimental multi-project cycle |
| `people-remind` | `09:00` | `kb-people-remind --horizon 0` | no | Follow-up reminders |
| `calendar` | `after:retro` | `kb-calendar-sync --days 2` | no | Adds meeting attendees to people review |
| `process-improve` | `on-demand` | `kb-evolution --knowledge-path ~/knowledge parse-ledger` | no | Experimental: checks the self-improvement proposal ledger; never scheduled |
| `money-radar` | `after:learning` | `kb-money-radar --text-only` | no | [Money Radar](#money-radar) |

### How steps run

- Each step runs **at most once a day**. It counts as done only when it
  exits successfully. A step that fails is retried on every 15-minute check
  until it succeeds.
- `after:<id>` waits until that step has succeeded today. If that step keeps
  failing, the ones after it wait too. If that step is `mail-morning`,
  `mail-evening`, `learning` or `money-radar` and you switch it off, the
  waiting step follows its trigger instead. For example, with both mail steps
  off, the brief runs at 07:15 and the retro at 20:30. Switch off any other
  step, such as `daily` or `retro`, and the steps after it do not run that day.
- A time means "at or after". A step you switch on at 15:00 with
  `when: "09:00"` runs on the next check that day.
- Steps due on the same check run one after another, in file order.
- If the file has a mistake, nothing runs, and `~/knowledge/logs/planner.log`
  says why. Check the file after every edit:

  ```bash
  python3 ~/knowledge/bin/_kb_processes.py ~/knowledge/personal/processes.yaml
  ```

  It prints `ok:` with the number of steps, or `invalid:` and the problem.
  Keep the file in its simple shape: blocks start with `- id:`, fields are
  indented two spaces, lists stay on one line like `[telegram, file]`.

### Switch a step on or off

Set `enabled: true` or `enabled: false` and save. The next check picks it up.

**Mail** is on by default but reads nothing until you connect Gmail, and the
brief leaves mail out until a read has worked once. You can leave it on. To
switch it off, either:

- set `enabled: false` on both `mail-morning` and `mail-evening`. The brief
  then runs at 07:15 and the retro at 20:30. Or
- run `kb-mail-migrate --file ~/knowledge/personal/processes.yaml --revert`.
  This removes both mail steps and puts the brief back at a fixed `"07:30"`
  and the retro at `"20:45"`. Run the same command without `--revert` to
  bring mail back.

**Everything at once:** to pause every routine in `processes.yaml`, unload the
scheduler, and load it again to resume.

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.knowledge.tick.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.knowledge.tick.plist
```

### Add your own step

Add a block with a new `id`. The command must live in `~/knowledge/bin` or be
an absolute path. [Daily research](#daily-research) shows a ready example.

## Morning brief

**Needs:** scheduled tasks and Telegram. Calendar, mail and health are
optional inputs.

A brief you can read in one minute on your phone. It is written from your own
knowledge base, so it knows where each project stands.

| Section | What it holds | When it appears |
|---|---|---|
| Header | Weekday, date and the focus of the day | always |
| Body | Last night's sleep, recovery, yesterday's activity and one suggestion | when you set up a health file |
| Day plan | Three to six timed lines, with today's meetings at their exact times | always |
| Main | One to three actions, each ending with a "Done:" condition you can check | always; one honest sentence when nothing needs doing |
| Your decision needed | Decisions only you can make | only when there are some |
| Mail | Every new email, one line each: sender, subject, whether you need to act | when mail arrived |
| Ideas | Up to three ready ideas, each with its next step | when you have ready or promoted ideas |
| Changed | Fresh changes across your projects | always |
| Risks | Warnings, stale pages, open escalations, sources that could not be read | always |
| Quiet | Inputs that were checked and had nothing new | when some were quiet |

Its rules: never drop an email, a meeting or a real decision to stay short,
and never invent a task.

**What it reads.** Every active project in `~/knowledge/registry.md` (status
`live` or `seeded`): its `state.md`, `log.md`, `backlog.md` and
`escalations.md`. It also reads the hub's `log.md`, your latest daily note and,
if you keep them, `personal/goals.md`, `roadmap.md`, `context.md` and
`habits.md`. Then come the inputs below.

- **Calendar.** Connect Google Calendar to Claude Code (the Google Calendar
  connector in your Claude account). The brief then reads today's and the
  coming week's events. It keeps only the date, time and title: no attendees,
  links or descriptions. Follow-ups you approved with `kb-followup approve
  <id>` appear too. Until the calendar is connected, the Risks line says the
  calendar could not be read. `kb-agenda --json` shows what the brief sees.
- **Mail.** See [Mail](#mail).
- **Ideas.** Ideas you triaged as ready or promoted, from `kb-idea`. See
  [Idea intake](modules/idea-intake.md).
- **Health.** If your own sync (a Garmin export, Apple Health, your script)
  writes one small JSON file each morning, as `morning/<date>.json` inside a
  folder you choose, set `KB_HEALTH_METRICS` in `.secrets` to that folder.
  The brief then opens with the Body section. It
  shows sleep, HRV against your baseline, resting pulse, energy at wake and
  yesterday's activity, plus one suggestion: train, rest or go to bed
  earlier. That suggestion also goes into the day plan. Vepol does not read
  devices itself. The brief can wait for your sync to finish. File format and
  settings: [Health in the morning brief](health-in-the-brief.md).

**Where it goes.** The brief is saved to `~/knowledge/briefs/<date>.md` before
it is sent. A long brief goes out in several messages, tracked one by one, so
a crash or a dropped connection never sends a message twice. If Vepol cannot
tell whether a message arrived, it stops instead of guessing and says so in
`~/knowledge/logs/brief.log`. If neither Codex nor Claude Code answers, no
brief is saved and you get one short message in Telegram, at most once a day:
"The brief was not made: no AI agent answered", one line per agent with the
reason (for example "Codex: not installed." or "Claude Code: not signed in —
run `claude` once to sign in."), and the log to check. A manual run prints the
same message, and so does a scheduled run when Telegram is not set up. The
brief retries every 15 minutes. After a sign-in failure Claude Code is paused
for an hour, so a run right after you sign in can still say it is "paused
after an earlier failure (until HH:MM)".

**Run it by hand.**

```bash
kb-brief                        # write and send today's brief
KB_BRIEF_DRY=1 kb-brief         # write it and print it here instead of sending
KB_BRIEF_PROMPT_ONLY=1 kb-brief # print the prompt; nothing is written or sent
kb-brief --help
```

- A manual run **before 06:00** is a preview. It is labeled as one, saved as
  `briefs/<date>-preview-<HHMM>.md` and sent. Your scheduled brief still
  arrives as usual.
- A manual run **after 06:00** is today's brief. The scheduled run then sees
  it was delivered and does nothing.
- A dry run after 06:00 also saves its text as today's brief. The scheduled
  run then sends that saved text instead of writing a new one. For a
  throwaway look, run it before 06:00.

**Plan the day.** In Vepol Desktop, **Plan my day** on the Today card opens a
session where you shape the day with your agent, starting from the brief.
Agreed blocks go into Google Calendar only when you ask. See the
[Vepol Desktop guide](../face/README.md).

## Evening retro

**Needs:** scheduled tasks and Telegram.

Around 20:45, a short retro of up to 900 characters, in six parts:

1. What closed today, taken from your logs, not from the plan.
2. How many items are open, and which projects carry the most.
3. One or two things that are stuck or carried over.
4. One insight from the day.
5. Whether the morning brief matched the day, and one improvement for
   tomorrow's brief.
6. One question to think about before sleep.

It reads today's entries in the hub's and each project's `log.md`, the
morning brief, your agreed day plan if you made one, each project's backlog
and the evening mail. Mail that still waits for your reply is called out. The
retro and its one-line reflection are added to the same day file as the
brief, `~/knowledge/briefs/<date>.md`, so each day keeps one record.

Run it by hand with `kb-retro`. `KB_RETRO_DRY=1 kb-retro` prints it instead
of sending; it still saves the retro into today's file, and the scheduled run
then sends that saved text.

## Mail

**Needs:** Codex, signed in, with its Gmail plugin connected.

Twice a day, at 07:15 and 20:30, Vepol reads the mail that arrived since the
last check, up to 25 inbox threads each time. It sorts each thread: needs
reply, calendar, waiting, receipt, ops alert, newsletter, FYI or noise. It
adds an urgency and a one-line summary. The brief lists every email. The
retro lists what still waits for an answer.

- It is read-only. Vepol never asks Codex to draft, send, label or delete
  anything.
- It never stores an email body or recipient list. The summary the brief
  reads holds no addresses. Sender names and addresses are kept apart, for
  [people proposals](#people-reminders-and-proposals). Both live in private
  files under `~/knowledge/personal/mail/`.
- The brief and retro treat email text as untrusted data. Their rules say
  never to follow instructions found inside a message.
- If a check is missed, the next one catches up, up to three days back.

Until a read has worked once, the brief and retro leave mail out entirely.
After that, a failed check shows as "Mail could not be checked today" with
the reason in the Risks line.

Vepol looks for Codex at `$KB_CODEX_BIN`, `~/.local/bin/codex`, your PATH,
`/opt/homebrew/bin/codex` and `/usr/local/bin/codex`. Test the connection by
hand. `"available": true` in the output means Codex can read your Gmail.

```bash
kb-mail-brief --period morning --json
```

This test does not move the "last read" mark, so the scheduled check still
sees the same mail. To switch mail off, see
[Switch a step on or off](#switch-a-step-on-or-off).

## arXiv learning digest

**Needs:** scheduled tasks and Telegram. Optional: `pdftotext` (from
`brew install poppler`) to read full papers.

After the brief, Vepol picks up to three new arXiv papers posted since
the last digest. The topics are agents, reasoning and planning, memory and
RAG, tools and MCP, evaluation, local models, and safety. It reads the full
paper when `pdftotext` is installed, or the abstract otherwise. Claude Code
explains each paper in your language, with Codex as the fallback.

Telegram gets a short header and then one message per paper. Each message
says why the paper was picked and what it means for your work, what was
studied, how, and what was found. A short glossary of the key terms follows
when it fits in the message; the saved report always has it. When
there are no new papers, you get one short notice instead. The full
breakdown is saved to `~/knowledge/reports/learning-arxiv-summary-<date>.md`.

Settings live in `~/knowledge/personal/daily-research.yaml`. Every key is
optional, and a missing file means the defaults.

```yaml
max_papers: 2                         # 1 to 3; default 3
arxiv_categories: [cs.AI, cs.CL, cs.LG] # default: cs.AI, cs.LG, cs.CL, cs.CV, stat.ML
social_check: grok                    # default off; adds X/Reddit discussion per paper
```

- `social_check: grok` needs the Grok CLI (`~/.grok/bin/grok`). Grok runs
  with writing, editing and shell commands denied.
- `focus_project` and `focus_context` are unset by default. Unset, the "why
  it matters" line speaks to your own work with AI agents. It names one of
  your live projects from `registry.md` when a paper clearly fits. Set
  either key and the analysis switches to a project frame. It then assumes
  you build a local agent setup with Markdown memory, as Vepol is, and adds
  the project and the one-line focus you give. Most setups should leave both
  unset.

Run it by hand with `kb-learning-arxiv --text-only`. Add `--dry-run` to see
what it would do, or `--force` to redo today's digest.

## Audio digests

**Needs:** one of two routes, chosen at install.

The morning digest joins three finished pieces, in order and word for word:
the brief (including the Body section), the arXiv report and the Money Radar
digest. A piece that did not run that day is left out. Code-like lines such
as scores, author lists and links are stripped from the spoken text. The
local voice reads that text aloud as written; NotebookLM uses it as the
source for an Audio Overview in its own words. The evening audio covers the
retro.

| | NotebookLM (default) | Local Qwen voice |
|---|---|---|
| Where you listen | In NotebookLM, as an Audio Overview in a monthly Vepol notebook | An MP3 sent to Telegram |
| What leaves your Mac | The digest text, uploaded to your NotebookLM account | Only the finished MP3, sent to your Telegram; the voice runs on your Mac |
| Setup | `pipx install notebooklm-py`, then `notebooklm login` | Apple Silicon, `uv`, `ffmpeg`, `ffprobe`, `lsof` and about 10 GiB free; then `kb-tts-install` |
| Telegram needed | no | yes |

The voice model loads for one render, writes the MP3 and exits. Nothing stays
running.

Switch routes at any time:

```bash
# local voice
kb-tts-install
kb-digest-migrate --file ~/knowledge/personal/processes.yaml --audio-backend local_qwen

# back to NotebookLM
kb-digest-migrate --file ~/knowledge/personal/processes.yaml --audio-backend notebooklm
```

`kb-tts-render --check` tells you whether the local voice is ready.
`kb-morning-digest --force` (or `--period evening --force`) redoes today's
audio after you fix something. To stop the audio, set `enabled: false` on
`morning-digest` and `evening-digest`. To remove both blocks, run
`kb-digest-migrate --file ~/knowledge/personal/processes.yaml --revert`.

Text, speech and audio files are saved as
`~/knowledge/reports/morning-digest-<date>.md`, `.txt` and `.mp3` (the MP3
only with the local voice), and as `evening-digest-<date>.*` for the evening.

## Daily research

**Needs:** network. The link list goes to Telegram. NotebookLM mode needs
`notebooklm login`.

On demand, two ways:

```bash
kb-daily-research --text-only   # a list of fresh AI-agent links to Telegram
kb-daily-research               # a NotebookLM notebook with an audio recap
```

- `--text-only` collects what is new about AI agents and sends up to eight
  links as a list, each with its title. It draws on Hacker News, Reddit,
  GitHub, the OpenAI, Google and Anthropic news pages, and today's arXiv
  picks. It collects links; it does not summarize them.
- Without `--text-only`, Vepol builds a NotebookLM notebook from those
  sources and starts an audio recap in your language.
- Pin a topic with `kb-daily-research --set-topic "<topic>"`. NotebookLM mode
  then researches that topic on the web. The text-only list carries no links
  for a pinned topic. Go back to the AI-agent radar with
  `kb-daily-research --auto-topic`.

To get the link list every morning, add this block to `processes.yaml`. A
scheduled run must use `--text-only`; NotebookLM mode runs only by hand.

```yaml
- id: research
  enabled: true
  when: after:learning
  run: kb-daily-research --text-only
  outputs: [telegram, file]
```

## Money Radar

**Needs:** switched on by you, Telegram, and at least one agent CLI. It uses
quota on every agent that takes part.

A daily scout for paying opportunities. It starts from pain: complaints,
repeated questions and manual workarounds where people gather in numbers. It
then looks for where money is forming around that pain. Codex, Claude Code,
Grok and Antigravity search the web in parallel; any agent you do not have is
skipped. Their findings are merged and ranked by a fixed formula, with no
extra model pass. The agents are kept from writing your files: Codex works in
a throwaway folder, Claude Code may only read and search, and Grok has
writing and shell commands denied. A check after each run stops delivery if a
sensitive file such as your SSH keys changed, or an unexpected file appeared
in the radar's own folders.

**Switch it on:**

1. Create `~/knowledge/personal/money-radar.yaml`. Every key is optional; text
   after `#` is ignored.

   ```yaml
   location: Lisbon, Portugal
   edge: backend engineer; English and Portuguese; small-business clients
   finds: 2
   lanes:
     - AI/automation services
     - marketplace & arbitrage plays
     - cross-border / regulatory-gap plays
   ```

   - `location` and `edge`: where you are and what gives you an advantage.
     The agents see both.
   - `finds`: 1 (default) or 2 finds per day. With 1, a second find is
     added only when a strong one sits on the other side of the legal line:
     an awareness item next to an opportunity, or the reverse.
   - `lanes`: interest hints, not limits. Leave the key out to use the
     built-in list.
2. Set `enabled: true` on the `money-radar` block in `processes.yaml`.
3. Re-anchor the morning audio so it waits for the radar:

   ```bash
   kb-digest-migrate --file ~/knowledge/personal/processes.yaml
   ```

4. Optional: try it once by hand from your home folder:
   `cd ~ && kb-money-radar --text-only`. A run takes several minutes.

**What it sends.** A "Money radar" message with one or two finds. Each find
has a title and a band: white (legal and mainstream), grey (legal but edgy) or
black (illegal; shown for awareness only, never with steps). Below that come
the money flow, the complaint behind it, how many people share it, who earns,
why now, rough numbers and the risk. White and grey finds also say how to try
them. Up to three proof links follow, with a reminder that this is
intelligence and the decision is yours.
The last line shows which agents answered and a confidence level: high with
three or more, medium with two, low with one. The digest is also read in the
morning audio.

**Where it goes.** `~/knowledge/reports/money-radar/<date>.md` (full report
with the scoring table), `<date>-digest.txt` (what was sent) and
`~/knowledge/sources/money-radar/<date>-context.md`. If the safety check
trips, delivery stops and an entry is added to `~/knowledge/escalations.md`.

## Nightly state refresh

**Needs:** scheduled tasks and a one-time setup.

At 06:30, before your brief, Vepol reads what each project logged since the
last pass. Claude Code proposes point edits to that project's `state.md`.
Only edits that match the page exactly and cite a dated log or daily entry
are applied. If the model fails, the page gets a short block listing the
newer log headlines, so it still shows what it is missing. A report and a
copy of the page before the change go to
`~/knowledge/.orchestrator/consolidate/<project>/`. When the model's edits
are applied, the project's `log.md` gets one line.

It covers the projects listed in `~/knowledge/hierarchy.yaml`. Create that
file once:

```bash
kb-rebuild-registry bootstrap
kb-rebuild-registry apply
```

For a project you add later, `new-wiki` prints the lines to append to the
table this creates, `~/knowledge/migration-2026-04-25.yaml`; append them as
printed, then run `kb-rebuild-registry apply`. Do not run `bootstrap` again: it
refuses to overwrite the table. `bootstrap --force` rebuilds it and keeps the
old one as a `.bak-<date>-<time>` copy, but it cannot read back a
`registry.md` that `apply` wrote, so check every category, status and
description afterwards. Until `hierarchy.yaml` exists, the refresh runs and
changes nothing. Preview it with
`kb-consolidate --dry-run`: it asks the model and prints the edits without
writing them. Creating `hierarchy.yaml` also wakes the experimental 20:45
cycle (see [Turn on scheduled tasks](#turn-on-scheduled-tasks)).

## People reminders and proposals

All of these are off until you switch them on. They need Telegram and the
Python packages from `requirements.txt` (see
[Getting started](getting-started.md)). Details:
[People](modules/people.md).

**Follow-up reminders.** Set a date on a contact with
`kb-contact remind <slug> --in 2w` (or `--date YYYY-MM-DD`). Check who is due
with `kb-contact due`. Set `enabled: true` on `people-remind`. On days when
contacts are due, a 09:00 message lists every contact due today or overdue.

**People proposals.** New people are proposed for review, each as a Telegram
message with buttons: Approve, Reject, Merge…, Later and Web search. A new
person stays in the review queue until you tap. Sources you can switch on:

| Step | What it adds | Before you enable it |
|---|---|---|
| `people-extract` | proposals from your project logs, from new mail senders once mail works, and from what `telegram-people` collected | run `kb-extract-people --hub ~/knowledge --init-watermarks` once |
| `calendar` | proposals from meeting attendees; a known email only gets a dated "seen" note | connect Google Calendar in Claude Code |
| `telegram-people` | who wrote to you in private Telegram chats: names, usernames and message counts (plus a phone number when Telegram shows one), never message text. It only collects; `people-extract` turns this into proposals, so switch both on. | install Telethon (`python3 -m pip install --user 'telethon>=1.36,<2.0'`; with Homebrew's Python, add `--break-system-packages` after `--user`), put `TG_API_ID` and `TG_API_HASH` (from my.telegram.org) in `~/.orchestrator/multibot.env`, then run `kb-telegram-people --hub ~/knowledge --login` once |

## Time zone and location

Vepol uses your Mac's time zone for the mail windows, calendar reads,
follow-ups and the day plan. To use another zone for them, set `KB_TZ` to a
zone name such as `America/New_York`. For scheduled runs, add it to the
`EnvironmentVariables` of `~/Library/LaunchAgents/com.knowledge.tick.plist`,
then unload and load the scheduler (see
[Switch a step on or off](#switch-a-step-on-or-off)). The times in
`processes.yaml` and the dates on briefs and reports always follow the Mac's
clock.

The midnight planner also records sunrise and sunset in the day record. Those
times are for information only; no routine runs by them. For the location it
uses `CoreLocationCLI` if installed, then `KB_FALLBACK_LAT` and
`KB_FALLBACK_LON` from `.secrets`. As a last resort it asks ip-api.com, a
plain-HTTP lookup by your IP address. Fill in the two fallback values to
avoid that lookup. With a location, it asks api.sunrise-sunset.org for the
day's times. If every lookup fails, the day still starts normally.

## Where everything goes

Everything lands in plain files under `~/knowledge`, and `kb-search` finds
the briefs and reports.

| What | Where |
|---|---|
| What the scheduler ran, when, and with what result | `logs/planner.log` |
| What has run today | `logs/today-plan.json` |
| Morning brief, evening retro and reflection, one file per day | `briefs/<date>.md` |
| Brief and retro logs | `logs/brief.log`, `logs/retro.log` |
| Mail summaries | `personal/mail/briefs/<date>-morning.json`, `<date>-evening.json` |
| arXiv digest | `reports/learning-arxiv-summary-<date>.md`; log `logs/learning-arxiv.log` |
| Audio digests | `reports/morning-digest-<date>.*`, `reports/evening-digest-<date>.*`; log `logs/morning-digest.log` |
| Daily research | `reports/daily-research-notebooklm-brief-<date>.md`; log `logs/daily-research.log` |
| Money Radar | `reports/money-radar/`, `sources/money-radar/`; log `logs/money-radar.log` |
| State refresh reports | `.orchestrator/consolidate/<project>/` |
| Crashes of the LaunchAgents themselves | `logs/tick.stderr.log`, `logs/planner.stderr.log`, `logs/people-review-bot.err.log` |

## Troubleshooting

**Start with the Automations view.** In Vepol Desktop, **Automations** lists
every step in `processes.yaml` with today's state and the reason. It shows
the last and next run, 14 days of history and the end of each log. "Failed in
result" flags runs that finished without a usable result.

**Nothing arrives at all.**

1. `launchctl list | grep com.knowledge` should list `com.knowledge.tick` and
   `com.knowledge.planner`. If not, turn on scheduled tasks
   ([above](#turn-on-scheduled-tasks)).
2. `kb-doctor install-health` checks the LaunchAgents, the agent CLIs and the
   install.
3. Look at the end of `~/knowledge/logs/planner.log`. Each step that started
   has a `firing` line, then `completed rc=0` or `will retry next tick`. A
   check with nothing due writes no line. `processes.yaml invalid` means the
   file has a mistake; [check it](#how-steps-run).
4. `kb-tick` runs whatever is due right now, the same way the scheduler does.

**The brief is saved but not sent.** Check both Telegram values and run the
test in [Set up Telegram](#set-up-telegram). Then run `kb-brief` to send the
saved brief.

**You got an error message instead of the brief.** Neither Codex nor Claude
Code answered: both were logged out, out of quota or offline. Sign in again
(`claude auth login`, `codex login`) and read `~/knowledge/logs/brief.log`.
The brief retries every 15 minutes on its own.

**The arXiv digest or the audio did not come.** The arXiv digest and the
morning audio wait for the brief; the evening audio waits for the retro. Fix
that step first, or look at the step's own log.

**Mail is missing.** Run `kb-mail-brief --period morning --json`. If it
reports `"available": false`, the `errors` line gives the reason: for
example, Codex was not found, its Gmail plugin is not connected, or it is out
of quota.

**"The calendar could not be read today."** Connect Google Calendar in Claude
Code. `kb-doctor mcp-check` checks that Claude Code answers from a
non-interactive shell, and `kb-agenda --json` shows what the brief gets.

**No audio.** NotebookLM route: run `notebooklm login`. Local route: run
`kb-tts-render --check`, and make sure Telegram is set. Then run
`kb-morning-digest --force`.

**A people step fails with `ModuleNotFoundError`.** The scheduler runs the
first `python3` on `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`. Install
the packages from `requirements.txt` for that interpreter
([Getting started](getting-started.md)).

**A step is cut off after 30 minutes.** Add `timeout: 3600` (or up to `7200`)
to its block.

**A step ran but you want it again today.** Run its command by hand, for
example `kb-learning-arxiv --text-only`. Most routines skip work already done
today. Add `--force` where it exists (`kb-learning-arxiv`,
`kb-money-radar`, `kb-morning-digest`, `kb-daily-research`) to redo it.

More: [Features](features.md) ·
[Security and privacy](security-and-privacy.md) ·
[Dependencies](dependency-matrix.md)
