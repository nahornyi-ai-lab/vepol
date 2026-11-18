---
name: init-kb
description: Bootstrap a personal knowledge base (knowledge/ wiki) in the current project and register it in the global hub at ~/knowledge/. Use this skill when the user says "init knowledge base", "bootstrap wiki", "setup wiki here", "start a wiki", "create a knowledge base", "/init-kb", or otherwise indicates they want to start using the personal knowledge system in the current project. Users may ask in their own language, for example Russian user phrasing such as "заведи вику", "заведи базу знаний", "создай вику", "нужна вика". The skill analyzes the project, proposes a slug/category/description, confirms with the user, and creates the full knowledge/ structure + hub registration + .gitignore rules + hub symlink.
---

# init-kb — set up a knowledge base in a project

Creates a local `knowledge/` wiki in the current project, following the master schema in `~/knowledge/AGENTS.md`, and links it to the hub. From then on the project automatically gets SessionStart context injection and SessionEnd session capture through claude-memory-compiler (the hooks are already installed globally).

## When to run

- The user asks for it explicitly: "start a wiki", "create a knowledge base", "init-kb", "/init-kb", "I need a wiki here" (or the same in their own language)
- The user is working in a project that has no `knowledge/log.md` yet and wants to start collecting knowledge systematically

## When NOT to run

- `knowledge/log.md` already exists → the wiki is already set up; the skill must stop and say so
- `cwd` is `$HOME`, `/tmp`, or a system folder — refuse and ask the user for the correct project path
- The user mentioned a "wiki" in passing, in another context, with no clear intent to set one up

## Step by step

### Step 1. Check preconditions

1. Get `cwd` with `pwd` (Bash).
2. If `cwd/knowledge/log.md` already exists — **stop**, tell the user "the wiki is already set up", show the path, and offer to edit or extend the existing one instead. Do not run the skill.
3. If `cwd` == `$HOME` or `/tmp` or a system folder (`/usr`, `/opt`, `/etc`) — stop and ask the user for the correct project folder.

### Step 2. Analyze the project

Read the project's key files to understand what it is:

- `README.md` (if present) — project description
- `CLAUDE.md` (if present) — may contain local instructions
- `package.json` — stack (Next.js, React, Vue, Node library, ...)
- `pyproject.toml` / `requirements.txt` — Python project
- `Cargo.toml` — Rust
- `go.mod` — Go
- `.git/config` (with `cat`) — remote URL → repo name, organization
- Top-level layout with Glob or ls — which folders it has (src/, components/, api/, ...)

Form a short understanding: **"This is a <type> project on <stack> that does <what>"** — 1-2 sentences.

### Step 3. Talk it through with the user

Show the user:

1. **What you found** — "I see a Next.js landing page for <work>. Is that right?"
2. **Proposed slug** — by default `basename($cwd)` in kebab-case
3. **Proposed category**:
   - If the path contains `<work-container>/projects/` → `order` (client order)
   - If the path contains `<work-container>/` (but not `projects/`) → `lab` (the lab's own work project)
   - If the path contains `PetProjects/` → `pet`
   - Otherwise → `personal`
4. **Proposed description** — 1-2 sentences (the user edits it)
5. **Proposed wiki categories** (subfolders in `knowledge/`):
   - **Next.js / web landing page**: `features`, `pages`, `components`, `decisions`, `experiments` (A/B tests)
   - **Lead-gen project**: `icp`, `offers`, `channels`, `funnel`, `metrics`, `experiments`, `agent-specs`
   - **Library / SDK**: `api`, `patterns`, `decisions`, `changelog-notes`
   - **Bot / integration**: `integrations`, `flows`, `decisions`
   - **Research**: `experiments`, `findings`, `hypotheses`
   - **Client order**: `requirements`, `meetings`, `deliverables`, `decisions`
   - **ML / Data**: `datasets`, `models`, `experiments`, `metrics`
   - **Minimal (default when the type is unclear)**: only `sources/` (already created) + `experiments/`

The user can accept everything as is, drop what they don't need, or add their own.

### Step 4. Create the structure with `new-wiki`

Once the user confirms, run in Bash:

```bash
bash ~/knowledge/bin/new-wiki "<absolute-project-path>" <slug> <category> "<one-line description>"
```

This will:
- Create `<project>/AGENTS.md` (canonical; read by Codex / Claude Code / Antigravity CLI via `agy --add-dir`). If the project already has its own `AGENTS.md`, `new-wiki` keeps the user's text and appends one block between `<!-- BEGIN VEPOL … -->` and `<!-- END VEPOL -->` that tells Codex and other agents to run `~/knowledge/bin/kb-session-start --print --cwd "$PWD"` (it prints `✓ … kept; Vepol block appended`). It never adds the block twice, and leaves a file that already runs `kb-session-start --print` as it is
- Create `<project>/knowledge/README.md`, `index.md`, `log.md`, `state.md`
- Create `<project>/knowledge/raw/assets/`, `sources/`, `daily/`
- Update `<project>/.gitignore` (adds `knowledge/` and `.kb-ignore`)
- Create the symlink `~/knowledge/projects/<slug>` → `<project>/knowledge`
- Append an entry to `~/knowledge/log.md`
- Add a `seeded` row for the project to a hand-written `~/knowledge/registry.md` (it prints `✓ … += <slug> (seeded)`); a registry generated by `kb-rebuild-registry` is left alone

### Step 5. Create the extra categories

`new-wiki` creates only the base folders. For the categories the user chose, run:

```bash
mkdir -p "<project>/knowledge/icp" "<project>/knowledge/offers" "<project>/knowledge/channels" ...
touch "<project>/knowledge/icp/.gitkeep" ...
```

### Step 6. Fill in real content (with Edit/Write)

`new-wiki` creates the files from templates with placeholders. Replace them with real content:

1. **`<project>/knowledge/README.md`** — Edit: remove the description placeholder and put in your analysis from Step 2 (1-2 sentences: what it is, who it's for, what state it's in)
2. **`<project>/knowledge/state.md`** — Edit: replace the placeholder under `## Current Snapshot` with your one-line assessment of the status. Leave the rest as in the template (empty).
3. **`<project>/AGENTS.md`** — if `new-wiki` created it, Edit: the project description section → the real description; the categories section → the list of chosen categories. If it is the user's own file (`new-wiki` printed `kept; Vepol block appended` or `already loads Vepol's startup context`), do not rewrite the user's text or the Vepol block; if `new-wiki` printed `not changed` (a link or a read-only file), show the user the line its step 1 printed and let them add it.
4. **`<project>/CLAUDE.md`** — `new-wiki` does not create one (Claude Code reads `AGENTS.md` directly when no `CLAUDE.md` or `CLAUDE.local.md` sits in the project or a folder above it). If the project already has a `CLAUDE.md`, check that it is a thin adapter over `AGENTS.md` (≤30 lines), with no separate copy of the rules.

### Step 7. Update the hub

1. **`~/knowledge/registry.md`** — `new-wiki` already added the project's row in Step 4. Check its output:
   - `✓ … += <slug> (seeded)` or `already lists <slug>`: do not add a second row. Nothing else to do, unless step 3 goes on with "This hub also has a migration table" (see the last case below).
   - No registry line, because the registry is generated by `kb-rebuild-registry` (it has DERIVED / HUB-MANAGED blocks): never edit `registry.md` by hand, and **never run `kb-rebuild-registry bootstrap`** on such a hub — it rebuilds the migration table from scratch and loses every project's category, status and description (it refuses without `--force`). Instead, `new-wiki`'s step 3 printed a migration-table entry for the project (the lines from `  - slug: <slug>` on). Append those lines unchanged, with their exact indentation, to the end of the migration table it names (`~/knowledge/migration-2026-04-25.yaml`). For a sub-project, change `parent: hub` to the parent project's slug. Then run `~/knowledge/bin/kb-rebuild-registry apply` and `~/knowledge/bin/kb-rebuild-registry check`; `check` must print `check: clean`. If step 3 said the table already lists the slug, only run `apply`. If step 3 said the migration table is missing, stop and tell the user: do not create the table or run `bootstrap` without their go-ahead.
   - No `registry.md` at all: tell the user; the installer creates one on a fresh hub.
   - Step 3 goes on with "This hub also has a migration table" (a hand-written registry, after `bootstrap` but before `apply`): append the entry it printed to that table the same way, then run `apply`.

2. **`~/knowledge/index.md`** — Edit: find the section that lists projects with a live wiki, `## Projects with a live wiki` (older hubs call it `## Проекты с живой вики`); if the hub has no such section yet, add it at the end. Add a bullet:
   ```
   - **[<slug>](projects/<slug>/README.md)** — <description>
   ```

### Step 8. Final confirmation

Show the user:
- What was created (list of paths)
- Where the hub entry is
- That the symlink works
- Next steps:
  1. "Open or restart Claude Code in `<project>` — SessionStart will automatically load the project's state and recent log into context"
  2. "Just start working — SessionEnd will record the session in `knowledge/daily/` and add a line to `log.md` on its own"
  3. "As you work, fill in `state.md` and the project-specific categories"

## Automation after bootstrap

Once the skill is done, everything else runs automatically through the hooks that are already installed (`~/.claude/settings.json`):

- **SessionStart** — `kb-session-start` injects a startup bundle into context: the agent card, `<project>/knowledge/state.md`, the tail of `log.md`, active work, open escalations, prevention rules and ongoing incidents from `incidents.md`, and the most recent `daily/*.md` note. Claude starts the session already knowing the project.
- **SessionEnd / PreCompact** — `kb-session-end` / `kb-pre-compact` delegate to the patched `flush.py` → it extracts decisions/lessons/actions through the Claude Agent SDK → writes them to `<project>/knowledge/daily/YYYY-MM-DD.md` + 1 cross-reference line in `log.md`.

The user doesn't need to do anything extra. They just work in the project.

## Edge cases

- **Nested project** (for example, `parent-project/sub-project/`) — **fine**, nesting is allowed. Each project gets its own `knowledge/`; the hooks pick the right one by `cwd`. Don't mix these wikis up; they are independent.
- **`.gitignore` already exists** — `new-wiki` appends the new lines without overwriting anything. Safe.
- **A hub symlink with the same slug already exists** — `new-wiki` warns and does not overwrite it. If it collides with another project, suggest a different slug to the user.
- **Project without git** (no `.git/`) — fine, `.gitignore` is still created preemptively.
- **The user declines at any step** — stop and don't leave partial structures behind. If something was already created, roll it back: delete the created files and the symlink, and remove the hub entry. Never delete or rewrite the user's own `AGENTS.md`: remove only the block from `<!-- BEGIN VEPOL` to `<!-- END VEPOL -->` that `new-wiki` appended. On a hub with a generated registry, the hub entry is the one appended to the migration table: remove it, then run `kb-rebuild-registry apply`.

## Final reminder

Right after running the skill, check that everything is actually in place — `ls` the key paths. Don't rely on "it should be there". If something went wrong, fix it or roll it back before handing control back to the user.
