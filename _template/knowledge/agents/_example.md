---
# Copy this file to `agent-card.md` and fill it for this project role.
# One project role = one card. Do not create per-runtime cards.

schema_version: "agent-card/v1"
inherits: "hub-baseline@0.4.0" # provenance/policy pointer, not runtime merge

name: "{{PROJECT_SLUG}}"
display_name: "{{PROJECT_SLUG}} orchestrator"
version: "0.1.0"
description: "Use proactively when working in this project on its main scope. Do not use for out-of-scope work."

role: "<one sentence: what role this agent plays in the project>"
goal: "<one sentence: what this role tries to achieve>"

boundaries:
  - "<project-specific boundary; what not to do and where to route instead>"

skills:
  - id: "<skill-id>"
    name: "<skill name>"
    description: "<when to use it, what it does, what durable output appears>"
    tags: [project]

subagents: []

tools:
  - "<project-specific tool or surface, if any>"

provider:
  organization: "{{PROJECT_SLUG}}"
  url: "<project URL, if any>"

documentation_url: "../../AGENTS.md"
---

# {{PROJECT_SLUG}} orchestrator

## Self-introduction

I am the `<project role>` for `{{PROJECT_NAME}}`. My job is `<main responsibility>`.

This card is shared by all runtimes that work in this project. Runtime differences, if relevant, are listed in `## Operating notes`.

## Specialization

- `<project-specific focus area 1>`
- `<project-specific focus area 2>`
- `<project-specific invariant or audience>`

Keep this section specific to the project. Generic workflow policy belongs in `AGENTS.md`, not in the card.

## Skills

### <skill-id>

Trigger: `<when this skill is used>`.
Action: `<what the agent does>`.
Durable output: `<log/report/decision/source/page created or updated>`.

## Subagents

| Subagent | When to call |
|----------|--------------|
| `<name or runtime>` | `<project-specific reason>` |

Use `subagents: []` if this role has no project-specific subagent roster.

## Boundaries

### <Boundary title>

Why: `<reason this is a real project boundary>`.
Instead: `<where to route the work or what to do instead>`.

## Operating notes

Project map:

- Current state: `knowledge/state.md`
- History: `knowledge/log.md`
- Open tasks: `knowledge/backlog.md`
- Escalations: `knowledge/escalations.md`
- Incidents: `knowledge/incidents.md`
- Strategy: `knowledge/strategies.md`

Runtime notes:

- Claude Code: `<project-specific notes only, if any>`
- Codex: `<project-specific notes only, if any>`
- Antigravity CLI: `<project-specific notes only, if any>`

Do not paste the full CLI matrix, task-board protocol, startup contract, or generic safety policy here. Link to `AGENTS.md` or the relevant KB page instead.
