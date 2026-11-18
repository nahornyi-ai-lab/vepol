# Vepol demo

Two invented workspaces you can explore without touching your own data. Every
person, company, project and event in them is made up.

- [`knowledge/`](knowledge/) is a personal hub with five life areas. Use it to
  try Vepol's commands with `kb-demo`.
- [`workspace/`](workspace/) is a small software company with three code
  projects. Use it to try Vepol Desktop with `face/demo.sh`.

## Try the commands on `knowledge/`

From the root of your Vepol checkout:

```sh
bin/kb-demo search "client renewal"   # search the whole demo hub
bin/kb-demo backlog --open            # every open task, grouped by project
bin/kb-demo task "Call the accountant" # add a task to the demo's board
bin/kb-demo path                      # print where the demo copy lives
bin/kb-demo reset                     # start the demo over
```

`kb-demo` copies `demo/knowledge` to `~/.vepol/demo-knowledge` the first time
you use it and runs the matching `kb-*` command with that copy as its hub. So
nothing reaches your `~/knowledge`, and your Vepol checkout stays unchanged.
It also switches the calendar off, so no command reads or writes your real
calendar, and prints the brief and the retro instead of sending them.

To see the morning brief Vepol would write for this invented person:

```sh
bin/kb-demo brief
```

This makes a real model call. It needs a logged-in Claude Code or Codex and
can take a few minutes. `kb-demo` prints the brief instead of sending it, and
saves it in the demo copy's `briefs/` folder.

To see only the prompt the brief would send, with no model call:

```sh
KB_BRIEF_PROMPT_ONLY=1 bin/kb-demo brief
```

`bin/kb-demo` with no arguments lists more commands.

## What's in `knowledge/`

A personal hub for one invented consultant with a family, and five projects:

- `projects/work/`: three clients, a renewal negotiation, invoices and a
  pricing decision in `decisions/`.
- `projects/family/`: school, a summer trip and weekly routines.
- `projects/health/`: strength training, sleep, lab results and check-ups.
- `projects/finance/`: the monthly review, savings goals and a subscription
  audit.
- `projects/learning/`: books in progress, an online course and book notes in
  `sources/`.

The hub itself holds `state.md` (where everything stands), `index.md` (a map
of the hub), `log.md` (what happened, by date), `registry.md` (the project
list) and `backlog.md` (open tasks). Next to them are `escalations.md` (what
waits for your call), `incidents.md` (what broke and the rule that prevents it
next time) and `strategies.md` (how Vepol should help here). One example page
each in `people/`, `companies/` and `concepts/` shows knowledge shared across
projects. `personal/.secrets` holds empty placeholders only.

In a real hub, each entry in `projects/` is a link to that project's own
`knowledge/` folder. Here they are plain folders, so the whole demo fits in
one place.

A good first read:

1. `knowledge/state.md`: what is going on right now.
2. `knowledge/index.md`: the map of the hub.
3. `knowledge/log.md`: the latest entries show the pace.
4. `knowledge/backlog.md`: what is open across the hub.
5. Any folder in `knowledge/projects/`: the same files, one project deep.

## Try Vepol Desktop on `workspace/`

`workspace/` is an invented software company. Its hub is in
`workspace/knowledge/`. Three code projects sit in `workspace/code/`:
`acme-web`, `design-system` and `billing-api`. Each has a little code and its
own `knowledge/` folder with state, log, tasks, decisions and lessons.
`workspace/knowledge/projects/` links to those folders, the same way a real
hub links your projects.

After you build Vepol Desktop (see
[Build and open](../face/README.md#build-and-open)), run this from `face/`:

```sh
./demo.sh
```

It copies the sample to `~/.vepol/demo-workspace/` and opens the app on that
copy, with its own port, app state and `tmux` server. The Desktop guide lists
[what the demo keeps apart and what it still shares](../face/README.md#try-it-on-the-sample-workspace)
with your own setup.

## Why everyday life areas

Vepol's value is the system, not any one project. Real project names would
read like a portfolio, and "Project A" would read like a test. Work, family,
health, money and learning are areas everyone has, so you can picture how
Vepol would map onto your own life.
