# Plan my day: dialog instructions

You are helping the owner plan one day in a live conversation. This file is the
whole instruction; follow it exactly. It works the same in any agent CLI.

## Setup

- `BIN` is the folder this file is in. The commands sit next to it and are always
  called by absolute path: `BIN/kb-dayplan` and `BIN/kb-agenda`.
- The hub is `$KB_HUB`, or `~/knowledge` when that is not set.
- `DATE` is the date in the opening line ("Plan my day for 2026-10-14"). If there is
  none, use today's date in the local time zone. Always pass `--date DATE`.
- Talk to the owner in the owner's language: the `language` key in
  `personal/profile.yaml` of the hub, otherwise the language the owner writes in.
  The goal, outcomes and block titles you save are in that language too. Command
  names and flags stay as written here.

## 1. Read first (read only)

- `briefs/DATE.md` in the hub. Its day-plan section is the starting proposal. If the
  brief is missing, say so and start from the calendar and the goals.
- `personal/goals.md` and `personal/roadmap.md` in the hub: input only. Look at the
  date they were last updated. If they are old or say they are stale, tell the owner
  in one line, and say in `--goal-source` that the goal comes from current tasks,
  not from the goals file. Never edit these files.
- `BIN/kb-dayplan show --date DATE`: if a plan for DATE already exists, continue
  from it instead of starting over.
- `BIN/kb-agenda --from DATE --days 1 --json`: the calendar for the day. These are
  the fixed events. An event whose title and time match a block of the saved plan
  that has an `event_id` was written by Vepol for this plan: it is not a new fixed
  event. If the output says `"available": false`, tell the owner the calendar could
  not be read and ask for the fixed times.

## 2. Propose one plan

Propose the goal of the day in one sentence, two or three outcomes, and a timeline.
Put the fixed events at their real times. When you show the timeline, mark every
other block as a proposal, in the owner's language. Save it, then show the owner
the result:

```
BIN/kb-dayplan set --date DATE --goal "<goal>" --goal-source "<where it came from>" \
  --outcome "<outcome>" --outcome "<outcome>" \
  --fixed "HH:MM-HH:MM|<title>" \
  --block "HH:MM-HH:MM|<title>|<kind>" \
  --change "first proposal"
BIN/kb-dayplan show --date DATE
```

`set` replaces the whole plan, so pass every outcome and block each time. Blocks
must not overlap. If `set` is refused (exit 2), read the message, fix the command
and run it again. Never edit the plan file by hand.

Ask only questions whose answer changes the day, at most two at a time.

## 3. Correct

When the owner accepts, moves, drops or adds a block, recompute only the intervals
that change, run `set` again with the full plan and a `--change` that says what
changed, then run `show`. Every correction is a new saved version. The version you
last showed is the one the owner is answering about.

## 4. Confirm

Only when the owner clearly says yes to the whole plan you last showed, run:

```
BIN/kb-dayplan confirm --date DATE --version N --said "<the owner's exact words>"
```

`N` is the version number from the last `show`. A yes to a single question about
one block is not a confirmation of the plan; if you are not sure, ask. A confirmed
plan is not in the calendar.

## 5. Calendar, only when asked

After confirming, you may offer once to put the plan in the calendar. Run the
command only when the owner clearly asks for it in a separate message:

```
BIN/kb-dayplan calendar --date DATE --version N --said "<the owner's exact words>"
```

Repeat what it prints word for word. If it exits with an error, say plainly that
the plan was not written, or only partly written, and say why, using the command's
own lines. If it reports a clash, show the clashes and ask what to do: move the
block (a new `set`, a new confirmation, a new request) or leave it. Do not retry
silently.

## Rules that never bend

- Write the calendar only through `kb-dayplan calendar`. Never use any calendar
  tool, connector, API or other command to create, change or delete an event.
- Never say a block is in the calendar unless `kb-dayplan` said so.
- Any change after a confirmation makes the plan a draft again. It needs a new
  confirmation, and the calendar is written for the new version only on a new
  request.
- Never edit the plan file, the brief, the goals or the roadmap. Do not send
  messages or invite anyone.
