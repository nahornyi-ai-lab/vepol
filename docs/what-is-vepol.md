# What Vepol is

> The long answer for people who read the [README](../README.md) and want to
> know whether Vepol is for them. The 60-second summary is at the bottom.

## A second inner voice, not a memory tool

Most "AI memory" tools answer a narrow question: how does the chatbot remember
what you said yesterday? The result is a chatbot that remembers a little more
and still waits for you to ask.

Vepol answers a different question: **how do you work with an AI partner that
knows all your projects, speaks up first, and handles more of your routine,
while you stay in control of where it goes?**

Memory is the base. On top of it, Vepol briefs you every morning, closes your
day every evening, sorts your mail, keeps you current on research and shows all
of it in one window. Taking on more of your work over time is the direction it
is built for; [Grows with you](#grows-with-you-the-direction) says exactly what
runs today.

## An operating layer over the agents you already use

Vepol is not a new model and not another chat app. It works through the agent
CLIs you already trust: Claude Code, Codex, Antigravity (`agy`), Hermes,
OpenCode and Grok. Claude Code is required; the others are optional.

Around those agents, Vepol adds:

- **One shared memory.** Each project gets a `knowledge/` folder with
  `state.md` (where things stand), `log.md` (what happened), `backlog.md`
  (tasks) and a few more files. One hub, `~/knowledge`, links every project and
  holds what belongs to no single project.
- **A head start for every session.** Claude Code loads the project's state,
  recent log, open tasks, open escalations and incident rules through a
  session-start hook. The installer adds it to a new `settings.json`, and
  `~/knowledge/bin/kb-claude-hooks --apply` adds it to an existing one. Codex
  and other agents load the same bundle by following the project's
  `AGENTS.md`, which tells them to run
  `~/knowledge/bin/kb-session-start --print --cwd "$PWD"`.
- **A roster of your agents.** Every session also learns which agent CLIs are
  installed on your Mac and when to use each, so one agent can ask another for
  a second opinion.
- **A daily routine on a schedule.** Once you turn on scheduled tasks at
  install, a scheduler checks one readable file,
  `~/knowledge/personal/processes.yaml`, every 15 minutes and runs what is due.
  A failed step retries at the next check. A finished step never runs twice in
  a day.
- **Failover between providers.** The brief and the retro try Codex first. When
  Codex is rate-limited, signed out, offline or returns nothing, the same job
  goes to Claude, and the failing provider rests for a while. This is the main
  reason the morning brief keeps arriving.
- **Records that outlive the chat.** Logs, tasks, escalations and incidents
  stay on disk across sessions and across vendors.

The model provider is replaceable. The knowledge base is not. Whether Claude,
Codex or a future agent picks up the task, it starts from the same files and
writes back to them. Your work never turns into one more vendor's chat history.

## What you get each day

The brief, the retro, mail and the research digests run once you answer yes to
"Install scheduled tasks?". They reach you in Telegram once you add your bot to
`~/knowledge/personal/.secrets`. [What works when](#what-works-when) lists what
each part needs.

### A one-minute morning brief

Every morning, around 07:30 by default, a short brief arrives in Telegram:

- your focus for the day;
- a timed plan around today's meetings, once your Google Calendar is connected;
- one to three actions, each with a clear "done when";
- every new email, one line each, marked by whether you need to act;
- ready ideas, what changed, risks, and the decisions only you can make.

The brief reads each project's state, log, tasks and escalations, plus your
goals if you keep them in `~/knowledge/personal/goals.md`. It is told never to
invent work, so on a quiet day it says so in one line.

Each brief is saved to `~/knowledge/briefs/<date>.md` before it is sent, and
every Telegram part is tracked. A crash or a dropped connection never sends a
part twice. A part that surely did not go out is retried at the next check. A
part that may have gone out waits for you to check it.

### Mail, sorted and read-only

Twice a day, at 07:15 and 20:30, Vepol reads up to 25 new inbox threads
through Codex's Gmail plugin. It sorts each one (needs a reply, waiting,
calendar, receipt, newsletter, noise and so on) and writes a one-line summary.
The morning brief lists every email. The evening retro lists what still waits
for an answer.

Vepol never drafts, sends, labels or deletes mail. It never saves an email body
or a recipient list. It keeps only the short summaries, plus each sender's name
and address for [People](modules/people.md), in files that only you can read.
Mail stays silent until you connect Gmail in Codex.

### An evening retro

Around 20:45 a short retro arrives: what actually closed today (from the logs,
not the plan), how heavy the backlog is, what is stuck, one insight and one
question before sleep. It also checks whether the morning brief matched your
real day and names one concrete improvement for tomorrow's brief. That note is
saved in the same day file as the brief, so each day keeps one record.

### Plan my day

In Vepol Desktop, **Plan my day** opens a conversation with the agent you pick.
It starts from the brief, your goals and your calendar, proposes a plan and
saves each correction as a new version for you to confirm. Only when you ask
separately does it write the agreed blocks to Google Calendar, through Claude
Code's Google Calendar connector. It then reads the calendar back and reports
exactly what is there. A clash with a busy event stops the write.

### Research that keeps you sharp

- **arXiv learning digest.** After the brief, up to three new arXiv papers on
  AI agents (memory, tools, reasoning, evaluation, local models, safety) arrive
  in Telegram, one message per paper. Each one is explained in your language:
  why it was picked, what was studied, how, what was found, and a short
  glossary. Vepol reads the full paper when it can. Claude writes the
  explanations, with Codex as the fallback.
- **Research on demand.** `kb-daily-research --text-only` sends a short list of
  links on what is new in AI agents to Telegram. Without `--text-only` it
  builds a NotebookLM notebook with a short audio recap in your language.
  `--set-topic` pins a topic of your own.
- **Money Radar** (switch it on when you want it). Several agents with web
  search (Codex, Claude, Grok and Antigravity, whichever you have) look for
  paying opportunities grounded in real complaints. Vepol merges and ranks
  their finds by fixed rules, not by another model, and sends one or two to
  Telegram. Each find carries the money flow, rough numbers, proof links and a
  white, grey or black label.

### Audio, if you would rather listen

The morning audio digest joins the finished brief, the arXiv report and the
Money Radar digest (when it is on) into one listen, without rewriting them.
You choose the voice at install and can switch later with `kb-digest-migrate`:

- **NotebookLM** (the default) turns them into its own Audio Overview, which
  stays in your NotebookLM account.
- **A local Qwen voice** narrates them on your Mac and sends the MP3 to
  Telegram. It needs Apple Silicon, `uv`, `ffmpeg` and about 10 GB of free
  disk.

An evening audio of the retro works the same way.

### Your health, as one suggestion

If your own sync writes a small health file each morning (from your watch, an
Apple Health export or a script of your own), the brief opens with a short Body
section: last night's sleep, HRV against your own baseline, resting pulse,
energy at wake and yesterday's activity. It ends with one suggestion grounded
in those numbers: train, rest or go to bed earlier. The day plan carries that
suggestion. Stale or missing data is reported plainly, never passed off as
today's, and the brief draws no medical conclusions.

Vepol ships no device connector. You point `KB_HEALTH_METRICS` in
`~/knowledge/personal/.secrets` at the folder your sync writes to; the file
format is in [Health in the brief](health-in-the-brief.md). A plan that eases
off on its own after several bad nights is the direction, not today's
behavior.

### People and ideas

- **People.** `kb-contact` keeps one Markdown card per person with your
  interactions and a follow-up date, and shows a short "who is this" summary
  before you reply. Switch on reminders, and Vepol messages you in Telegram
  when a follow-up is due. Switch on proposals, and new people from your mail,
  calendar and private Telegram chats arrive as Telegram messages that you
  approve, merge or reject with a tap. Nothing about a new person is written
  until you tap. More in [People](modules/people.md).
- **Ideas.** `kb-idea capture "..."` turns a passing thought into a card. You
  triage it, then park it, drop it, promote it to a board task or block time
  for it in your calendar after you approve. Up to three ready ideas appear in
  the morning brief. More in [Idea Intake](modules/idea-intake.md).

### One window for all of it: Vepol Desktop

Vepol Desktop is a native Mac app over the same files:

- **Memory:** one card per project with what is happening now, what is next,
  the last decision, the last activity and whether `state.md` has fallen behind
  the log. A Today card holds **Plan my day**.
- **A project screen:** state, sessions, task board, decisions, history,
  lessons and files.
- **Your agents in real terminals:** Claude Code, Codex, Antigravity, Hermes,
  OpenCode or Grok, each in its own session. A session survives quitting the
  app, and you can continue it in Terminal with the `tmux attach` command the
  app shows.
- **Sessions and Tasks:** every session on one board, and every project's tasks
  in one table, where you can start an agent on a task or close it with Undo.
- **Automations:** every scheduled routine with today's state and the reason,
  its last and next run, and 14 days of history. It also flags runs that ended
  without an error but produced no usable result.

The app listens only on your Mac (`127.0.0.1`), behind a token that lives in
memory for one launch. You build it once from the `face/` folder; it needs an
Apple Silicon Mac, Python 3.11 or later, the Command Line Tools and `tmux`
([guide](../face/README.md)). After the build, `./demo.sh` in the same folder
opens it on an invented company so you can look around first.

## What makes Vepol different: visible discipline

Most AI assistants are black boxes. The model decides something, remembers
something, and an answer appears in a chat window. You cannot audit it, so it
is hard to trust it with important work.

Vepol works the other way. **Every meaningful action leaves a text trace that
you can read, edit, override or grep six months later.**

### Memory stays current, in the open

Three things keep a project's memory current:

1. **Your agents write as they work.** The project's `AGENTS.md` tells every
   agent to record durable events in `log.md` and to replace outdated lines in
   `state.md`.
2. **Session capture** (optional, Claude Code only). After each session, and
   before auto-compaction, a model summarizes the session's decisions, lessons
   and action items into `knowledge/daily/YYYY-MM-DD.md` and adds one dated
   line to `log.md`. Token-shaped secrets are redacted first. You turn it on at
   install, and it needs `uv`.
3. **A nightly `state.md` refresh** (with scheduled tasks on). At 06:30 a
   model proposes point edits to each project's `state.md` from what was
   logged since the last pass. Only edits that match the page exactly and cite
   a log or daily note are applied, and each run leaves a report, a diff and a
   backup. It needs a one-time `kb-rebuild-registry` setup so it knows your
   projects.

Moving recurring themes out of daily notes into their own pages (`concepts/`,
`people/`, `companies/`, `solutions/`) is planned. Today agents create those
pages as they write, or when you ask.

### Pages link to each other

Pages reference each other with wiki-links such as `[[concept]]` or
`[[person]]`, which agents add as they write. You can browse the network in
Obsidian's graph view or any tool that reads wiki-links. `kb-search` searches
the hub and every project at once, and `kb-doctor graph-audit` finds pages that
nothing links to.

Vepol does not propose new links on its own yet. The brief reads a fixed set of
files (each project's state, log, tasks and escalations, plus your goals), not
the whole graph.

### Three files, three jobs

- **`backlog.md`** is the task board every agent shares. Tasks move through
  Backlog, Ready, In Progress, Review and Done, with Blocked and Cancelled on
  the side. `kb-task "..."` adds one, and `kb-board` moves it.
- **`escalations.md`** is where an agent writes when it cannot go on without
  your decision. Open escalations show at the start of every agent session and
  in the morning brief's risks line.
- **`incidents.md`** records what broke, the root cause, the fix and a
  prevention rule. Prevention rules load into every new session, so a mistake
  is less likely to repeat. Vepol Desktop shows them as Lessons.

This is not a task tracker. It is a protocol between you and your agents, with
one file per kind of message.

### Strategy is a file you own

Each project has a `strategies.md`: where it is heading and why, plus testable
hypotheses. Agents update it when you ask or after a real pivot. A weekly
automatic review of the strategy is the direction; today nothing rewrites the
file on a schedule.

### A second agent checks the plan, as a working rule

For non-trivial development work, the contract Vepol installs
(`~/knowledge/AGENTS.md`) and its `development-loop` skill tell your agent to
write a short spec, have one other agent check it once against the real code,
and wait for your approval before writing code. This is a rule your agents
follow, not an automatic gate: Vepol does not start the reviewer itself or
block work without the review. See
[Lightweight spec review](methodology/cross-agent-review.md).

### Every meaningful event is a log line

Not "I did something" in a chat window, but a dated line with a category in the
project's `log.md`, such as
`## [YYYY-MM-DD] strategy | <project> | <what changed and why>`. Six months
later, `kb-search "strategy"` finds every such line across all your projects,
each with the file it sits in. The scheduled routines keep records too: each
run writes to `~/knowledge/logs/` and shows up in the Automations view.

## Grows with you: the direction

Vepol is built to take on more of your work over time, one kind of task at a
time. Each kind starts supervised. As your corrections drop, it earns more
room; where you keep correcting, it stays supervised.

**This is the design, not today's product.** Nothing in Vepol measures your
edits or raises autonomy on its own yet. What runs on its own today is the
daily routine above, once you turn on scheduled tasks.

Here is the design, with mail as the example:

- **Day 1 (works today):** every new email shows up in your brief, marked by
  whether you need to act. You decide, and you write.
- **Week 2 (design):** Vepol drafts replies to routine mail. You proofread and
  send.
- **Month 2 (design):** typical inquiries are answered through your drafts
  folder. You spot-check.
- **Month 6 (design):** half of your operational routine runs without you, and
  you spend that time on what only you can do.

The weeks and months show the intended pace, not a promise.

## How Vepol differs from a typical AI chat

| | Typical AI chat | Vepol |
|---|---|---|
| **Memory** | hosted by the vendor, opaque to you | Markdown files on your Mac that you can edit |
| **Context across sessions** | usually lost or summarized | kept: every session starts from the project's files |
| **Switching agents** | a new agent starts from zero | Claude Code, Codex and others share one folder |
| **Tasks** | in your head or a separate tracker | in `backlog.md`, a board every agent shares |
| **Decisions and lessons** | dissolve in chat history | written to the project's log, automatically with session capture |
| **Initiative** | waits for your prompt | brief, retro, mail and digests arrive on schedule |
| **When a provider fails** | the chat stops | the brief and retro switch from Codex to Claude |
| **Transparency** | inside the model | every step is a file or a log line |
| **Plans** | one answer from one model | a working rule: one second-agent review of each non-trivial spec |
| **Health** | absent | the brief reads your morning health file and makes one suggestion |
| **Growth over time** | each chat starts blank | today a daily routine; the direction is more autonomy as you correct less |

## How Vepol stays yours

- **It runs on your Mac.** Vepol has no server of its own. The agents you use
  talk to their own vendors as they always do, and Telegram, Gmail, Google
  Calendar or NotebookLM come in only when you connect them.
- **It is plain Markdown.** Open any file in any editor, search it with
  `kb-search` or grep, and browse it as a graph in Obsidian.
- **Your keys stay in one private file.** Your Telegram bot token, chat id and
  other private values live in `~/knowledge/personal/.secrets`, which the
  installer makes readable only by you.
- **Upgrades and uninstall keep your notes.** `./upgrade.sh` moves to the
  newest release and re-applies the installer without overwriting your notes.
  `./uninstall.sh` removes Vepol's commands, skills and scheduled tasks and
  leaves your hub in place; `--backup-user-data` archives it first.
- **The license is FSL-1.1-MIT.** It is source-available now, and each release
  becomes MIT two years after it is published. Personal use, internal company
  use, client work, changes and forks are all allowed. The one thing it rules
  out is offering Vepol as a competing commercial product or service. Details:
  [LICENSE](../LICENSE) and [LICENSE-FUTURE.md](../LICENSE-FUTURE.md).

More in [Security and privacy](security-and-privacy.md).

## What works when

- **Right after install:** the shared memory and the hub, startup context in
  Claude Code, `kb-search`, the task board, ideas and people cards (once the
  Python packages in `requirements.txt` are installed), the `kb-demo` sample,
  the `kb-doctor` health check, upgrade and uninstall.
- **Build once by hand:** Vepol Desktop, from the `face/` folder.
- **When you answer yes to "Install scheduled tasks?":** the morning brief, the
  evening retro, the mail summaries, the arXiv digest, the morning and evening
  audio, and the nightly `state.md` refresh (after its one-time registry
  setup).
- **With your own account or source:** a Telegram bot (`TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` in `~/knowledge/personal/.secrets`), Gmail through Codex,
  Google Calendar through Claude Code, a NotebookLM login or the local Qwen
  voice for audio, a daily health file from your own sync, and Codex for
  failover and second opinions.
- **Switch on when you want it:** Money Radar, people proposals, follow-up
  reminders and daily research on a schedule.
- **Experimental:** the multi-project nightly cycle and its plan dispatch, the
  runner for tasks marked `auto: true`, the self-improvement helpers
  (`kb-evolution`) and one Telegram bot per project.
- **Direction:** autonomy that grows as your edits drop, a strategy that
  reviews itself, a day plan whose intensity follows your health beyond the
  brief's one suggestion, lifting daily notes into their own pages, and Pro
  modules.

A few of these are newer than the latest tagged release; the
[changelog](../CHANGELOG.md) lists them under Unreleased. For setup, see
[Getting started](getting-started.md) and [Features](features.md).

## Who this is for

- People who already work with Claude Code, Codex or another terminal agent,
  write in Markdown, and want their notes to act instead of sit
- Founders, consultants, engineers and researchers who run several projects at
  once and are tired of every chat starting from zero
- Anyone who needs an audit trail of what the AI did, decided and changed, in
  files they can read
- Mac users who want their assistant's memory kept in files on their own
  machine

## Who this is *not* for

- People who want a hosted cloud service. Vepol is your local setup, by design.
- People who do not use a terminal agent yet. Vepol works through Claude Code,
  Codex and agents like them, so start there first.
- People on Windows or Linux. Vepol runs on macOS 13 or later, and Vepol
  Desktop needs Apple Silicon.
- People who want an AI that only answers when asked. Vepol's point is
  initiative, although you can leave the schedule off and use the memory alone.

## 60-second summary

Vepol is your second inner voice: a personal AI assistant on your Mac that
works through the agents you already use, such as Claude Code and Codex. It
keeps one shared memory per project, so no session starts from zero. Once you
turn on scheduled tasks, it sends a one-minute brief every morning and a retro
every evening to Telegram, sorts your mail without touching it, explains new
research in your language, can read the brief and the research aloud, and
switches from Codex to Claude when Codex is unavailable. Vepol Desktop shows
every project, task, routine and agent session in one window. Everything it
knows is plain Markdown that you can read, edit and grep. Taking on more of
your work as your corrections drop is the direction, not yet the product. It is
source-available under FSL-1.1-MIT, and each release becomes MIT two years
after it is published.
