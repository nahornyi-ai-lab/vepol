---
title: "Vepol People — a card for everyone who matters"
status: stable
type: module
parent: vepol
---

# Vepol People

Remember people the way Vepol remembers your projects. Vepol People keeps one
Markdown card per person in your knowledge base: who they are, how you met,
what happened between you, and when you owe them a message. It reminds you on
the day a follow-up is due. It can also notice new people in your mail, your
calendar and your private Telegram chats, and ask you with one tap whether to
keep them.

People are the context you carry and lose most easily. Calls you postponed,
introductions you owe, the person who could unblock a project: none of that
lives cleanly in a calendar, an inbox or a contact list. A card does.

## What you get

- **A card per person** at `~/knowledge/people/<slug>.md`. Plain Markdown you
  can open in any editor, grep, version or back up. `kb-search` searches the
  cards along with the rest of your knowledge base.
- **`kb-contact`** to add, log, search, show and remind, and a short
  "who is this" card before you reply to someone.
- **Follow-up reminders** in Telegram on the day they are due.
- **Proposals of new people** from mail senders, calendar attendees, private
  Telegram chats and project logs. Each new person arrives in Telegram with
  Approve, Merge, Reject and Later buttons. Nothing about a new person from
  mail, calendar or Telegram reaches your cards until you approve it.
- **A one-time public profile lookup** for a person, run by Codex. A profile is
  kept only when it matches something you already know about them.

## What works when

| What | When it works |
|---|---|
| Cards and `kb-contact` | Right after install, once the Python packages from [`requirements.txt`](../../requirements.txt) are installed |
| Review buttons in Telegram | After you answer yes to "Install scheduled tasks?" and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `~/knowledge/personal/.secrets` |
| Follow-up reminders in Telegram | When you switch on `people-remind` (same Telegram settings) |
| Proposals from project logs and mail senders | When you switch on `people-extract`; mail senders also need mail reading (Codex with its Gmail plugin) |
| Proposals from calendar attendees | When you switch on `calendar`; needs Google Calendar connected in Claude Code |
| Proposals from private Telegram chats | When you switch on `telegram-people` and `people-extract`; needs Telethon and a one-time sign-in with your own Telegram account |
| Public profile lookup | Any time with `kb-contact enrich`; needs the Codex CLI |

You switch these on in `~/knowledge/personal/processes.yaml` by setting
`enabled: true` on the process. Processes run on schedule only after you
answered yes to "Install scheduled tasks?". The steps for each are below.

## Everyday use

```bash
kb-contact add "Marina Soto" --email marina@example.com \
  --met "Lisbon AI meetup, 2026-03" --tags colleague,ml
kb-contact log marina-soto "Talked about her side project on causal inference."
kb-contact remind marina-soto --in 6w
kb-contact due --horizon 60
```

```text
Contacts due in next 60 days:

  2026-12-30  Marina Soto  [marina-soto]  colleague, ml
```

Before a call or a reply, ask for the short version:

```bash
kb-contact context marina@example.com
```

```text
Marina Soto <marina@example.com> [marina-soto]
recent:
  2026-11-18 | manual | Talked about her side project on causal inference.
next touch due: 2026-12-30
```

Read it yourself, or let your agent run it. All the commands:

| Command | What it does |
|---|---|
| `kb-contact add "Name" [--email] [--telegram @handle] [--met] [--tags a,b] [--company] [--role]` | Creates a card, or updates the existing one when the email or name matches |
| `kb-contact log <slug> "summary"` | Adds a dated row to the card's Interactions table |
| `kb-contact remind <slug> --in 6w` (or `--date YYYY-MM-DD`) | Sets the next follow-up date; durations use `d`, `w` or `m` |
| `kb-contact due [--horizon 7]` | Lists who is due in the next N days, overdue included |
| `kb-contact search <text>` | Finds cards that contain the text |
| `kb-contact show <slug>` | Prints the whole card |
| `kb-contact context <email \| @handle \| slug \| name>` | Prints a compact card: role, company, known profiles, the last three interactions, the next follow-up |
| `kb-contact review` | Walks pending proposals in the terminal: approve, merge, reject or defer (`--json` lists them) |
| `kb-contact push` | Sends pending proposals to Telegram now |
| `kb-contact merge <proposal-slug> <card-slug>` | Folds a proposal into an existing card |
| `kb-contact review-drafts` | Walks cards marked `draft: true`, for example a name you added that looks like an existing card |
| `kb-contact enrich <slug>` | Runs the one-time public profile lookup |

## Follow-up reminders

Give a person a follow-up date with `kb-contact remind`. On that day, at
09:00, you get one Telegram message that lists everyone due today or overdue.
No message when nobody is due. A person stays on the list until you set a new
date with `kb-contact remind`.

To switch it on, set `enabled: true` on the `people-remind` process in
`~/knowledge/personal/processes.yaml`. It sends through the same Telegram bot
as your morning brief. To see what it would send today:

```bash
kb-people-remind --dry-run
```

A reminder is not a streak to keep. It is a small note to your future self
that you owe someone a message, a favor or some attention.

## New people, proposed for you

Vepol can watch four places for people:

- **Mail senders.** When mail reading is set up, every mail check also writes
  a list of who wrote to you: names, addresses and message counts, never
  subjects or text.
- **Calendar attendees** of your recent meetings, read through Google Calendar
  in Claude Code.
- **Private Telegram chats.** A read-only collector signs in with your own
  Telegram account and records who wrote to you: names, usernames, phone
  numbers when Telegram shows them, and message counts, never message text.
  Group chats are skipped unless you run it with `--include-groups`.
- **Project logs.** Email addresses and @handles that appear in your
  projects' `log.md`, `backlog.md`, `escalations.md` and daily notes. A name
  with no address is picked up only when you run
  `kb-extract-people --hub ~/knowledge --llm` yourself, and then always as a
  proposal.

What happens next depends on whether Vepol already knows the person:

- **Someone already on a card**, matched by email address (in Telegram, by
  username), gets a dated row in Interactions with its source: a message
  count for mail and Telegram, the meeting title for calendar, the log line
  for project logs.
- **Someone new from mail, calendar or Telegram** becomes a proposal, a
  `<slug>.staged.md` file next to the cards. It stays a proposal until you
  decide.
- **From project logs**, a new email address gets a card right away, because
  it is an address you or your agents wrote down. Role addresses such as
  `info@` or `no-reply@` are skipped, and so are your own addresses once you
  list them, one per line, in `~/knowledge/people/.owner-emails.txt`. An
  @handle, or a name close to an existing card, becomes a proposal.

Each proposal arrives in Telegram as its own message with buttons:

- **Approve** turns it into a card. Unless the person already has a known
  profile, you then get a choice: **Web search** runs the one-time profile
  lookup, **Skip search** does not.
- **Merge…** lists the closest existing cards; pick the one it belongs to.
- **Reject** drops it, and that person is not proposed again.
- **Later** sets it aside; it comes back in a later round.

At most eight proposals wait in Telegram at once; the rest follow as you clear
them. Bot accounts are rejected automatically. You can also review in the
terminal with `kb-contact review`.

### Switch the sources on

**Telegram review buttons.** Answer yes to "Install scheduled tasks?" at
install. That loads the `people-review-bot` LaunchAgent, which listens for
your taps. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in
`~/knowledge/personal/.secrets`
([how to get both](../getting-started.md#turn-on-your-daily-routine)); the bot
picks them up within about five minutes. It uses the same bot as your morning
brief. Keep every other listener off that bot: Telegram allows one listener
per bot, so Claude Code's own Telegram plugin needs a different one.

The three collectors below run after your evening retro.

**Project logs and mail senders.** Mark the starting point once, so the first
run does not sweep up your whole history:

```bash
kb-extract-people --hub ~/knowledge --init-watermarks
```

Then set `enabled: true` on `people-extract`. Run the command again after you
add a project, or scheduled runs skip that project; each run marks every
project's current state as the new starting point. Mail senders arrive only
when mail reading works: Codex with its Gmail plugin connected.

**Calendar attendees.** Connect Google Calendar in Claude Code, then set
`enabled: true` on `calendar`. Each run looks at the last two days of
meetings.

**Private Telegram chats.**

1. Install Telethon: `python3 -m pip install --user 'telethon>=1.36,<2.0'`.
2. Get an API id and hash for your account at my.telegram.org. Put them in
   `~/.orchestrator/multibot.env` as `TG_API_ID=...` and `TG_API_HASH=...`
   (or in the environment, or in another file named by `KB_TG_ENV_FILE`).
3. Sign in once: `kb-telegram-people --hub ~/knowledge --login`. It asks for
   your phone number and the code Telegram sends you, and for your two-step
   password if you set one.
4. Set `enabled: true` on `telegram-people`, and on `people-extract`, which
   turns the collector's list into proposals.

## The one-time profile lookup

```bash
kb-contact enrich marina-soto
```

Codex runs a few web searches for the person's public profiles (LinkedIn,
company site, GitHub). A profile is kept only when its evidence quotes
something you already know: the company, email domain, role, location or
Telegram handle. A matching name alone never counts. Found profiles go into
the card's `public_profiles` with their source and confidence.

The lookup runs once per person. A card that already has a profile, or was
searched before, is skipped; `--force` repeats it. It needs the Codex CLI, and
it sends the person's name and those known details to Codex's web search.

## How a card is built

Each person is one file, `~/knowledge/people/<slug>.md`. The frontmatter holds
identity: a stable ID, the name, aliases, channels (email, Telegram, LinkedIn,
phone), company, role, when you first met, when you last saw them, the next
follow-up date, tags, and a draft flag. The body has two regions that never
collide:

- **Notes**, between `<!-- MANUAL-NOTES-BEGIN -->` and
  `<!-- MANUAL-NOTES-END -->`. Anything you write. Automation never touches it.
- **Interactions**, between `<!-- DERIVED-SIGHTINGS-BEGIN -->` and
  `<!-- DERIVED-SIGHTINGS-END -->`. A dated table of meetings, messages and
  mentions. Each row names where it came from, and the same row is never
  added twice.

Cards start sparse: only fields with a value are written, and they grow as
you or the sources add more. A missing field means "no data yet", not
"broken". [`_template/knowledge/people/_example.md`](../../_template/knowledge/people/_example.md)
shows every field, and
[`demo/knowledge/people/sarah-mendez.md`](../../demo/knowledge/people/sarah-mendez.md)
is a filled-in card.

### One person, one card

Vepol matches people in layers:

- **The same email** is the same person.
- **The same Telegram username** is the same person when the Telegram
  collector sees them.
- **A similar name** is compared by Jaro-Winkler similarity, a simple string
  distance, for names of four characters or more. When you add someone by
  hand, or a new email address turns up in a project log, a score of 0.92 or
  higher counts as the same person. Between 0.85 and 0.92 the new entry becomes a
  draft or proposal marked `possible_duplicate_of: <slug>`. From mail,
  calendar and Telegram, a name match alone never merges anything; it only
  marks the proposal.

Matching is cautious on purpose: a wrong merge is harder to undo than a
duplicate.

## People in the rest of your knowledge base

Cards live in the same hub as your projects, so they connect the same way
everything else does:

- Link a person from a project page, for example
  `Lead reviewer: [[people/marina-soto]]`. In Obsidian, with the vault opened
  at `~/knowledge`, the link opens the card, and an agent that reads the page
  can follow it there.
- `kb-search "Marina"` finds her card next to every project note that
  mentions her.
- `kb-contact context` gives you, or your agent, the short version before a
  reply.
- With `people-extract` on, her email address in a project log adds a dated
  row to her card that points at the log line.

The morning brief does not read people cards yet, and agents do not load
cards on their own. They open one when a page links to it or when you ask.

## Why Markdown and not a database

The same file does four jobs at once:

1. **A note for you.** Open `people/marina-soto.md` in any editor and write a
   paragraph, the way you would in a notebook.
2. **A history you can check.** The Interactions table names the source of
   every row. You can grep it, diff it and read it without a query language.
3. **Something to cite.** An agent can point you at the card a fact came from.
   The card is the reference, not a record ID in a database you cannot read.
4. **Context for agents.** Markdown is what models read natively. There is no
   adapter between what the card says and what the agent knows.

A database with a form on top would split these jobs across screens, exports
and prompt code, and you would spend effort keeping them in sync.

## What People is not

- **Not a CRM.** No sales pipeline, deal stages, lead scoring or team
  dashboards.
- **Not a contact service.** No backend, no proprietary format, no
  subscription. If you leave Vepol, you keep every card.
- **Not a quantified-self loop.** Counting interactions per week is not the
  goal. Remembering the right person at the moment it changes a decision is.
- **Not a mailer.** People never drafts or sends messages. It gives you
  context and reminders; you write.

## Not built yet

- Follow-up dates suggested from how often you talk.
- Voice-call transcripts as interactions.
- Suggestions of whom to introduce to whom.
- Groups, households and families beyond individual cards.
- Confidence scores on facts in a card.
- People in the morning brief.

## If something does not work

- **`ModuleNotFoundError` (for example `frontmatter` or `click`).** Install
  the packages: from your Vepol folder, run
  `python3 -m pip install --user -r requirements.txt` (if pip refuses, see
  [Python packages](../dependency-matrix.md#python-packages)). Scheduled runs
  and the review bot use the first `python3` on
  `/opt/homebrew/bin:/usr/local/bin:/usr/bin`, so install them for that Python.
- **No buttons in Telegram.** Check both Telegram settings in
  `~/knowledge/personal/.secrets`, then look at
  `~/knowledge/logs/people-review-bot.err.log`. A `409 conflict` there means a
  second listener uses the same bot.
- **A project never produces proposals.** Run
  `kb-extract-people --hub ~/knowledge --init-watermarks` after adding it.
- **Calendar sync fails.** `kb-calendar-sync` exits with 3 when Claude Code is
  not reachable and with 4 when Google Calendar is not connected or not
  authorized in Claude Code. Scheduled runs log the code in
  `~/knowledge/logs/planner.log`, as `calendar rc=3` or `calendar rc=4`.

## Under the hood

- Commands: `bin/kb-contact`, `bin/kb-people-remind`, `bin/kb-extract-people`,
  `bin/kb-calendar-sync`, `bin/kb-telegram-people` and
  `bin/kb-people-review-bot`, with shared code in `bin/_kb_people/`.
- The review bot's LaunchAgent:
  `launchd/com.knowledge.people-review-bot.plist.template`.
- Scheduled processes in `~/knowledge/personal/processes.yaml`:
  `people-remind` (09:00), and `telegram-people`, `people-extract` and
  `calendar` (after the evening retro). All four start switched off.
- Tests: `bin/tests/test-people*.sh`.

The calendar is read through Claude Code's Google Calendar connector and mail
through Codex's Gmail plugin, so there is no Google SDK or OAuth client in
Vepol's code. Telegram chats are the one source Vepol reads directly, through
Telethon signed in with your own account. See [MCP-first for external sources](../methodology/mcp-first-sources.md).

## See also

- [Orchestrated Knowledge Base](../methodology/orchestrated-knowledge-base.md): why one Markdown hub
- [KB-Authoring Discipline](../methodology/kb-authoring-discipline.md): how facts enter the knowledge base
- [MCP-first for external sources](../methodology/mcp-first-sources.md): how calendar data is read
