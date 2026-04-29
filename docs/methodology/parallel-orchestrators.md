---
title: "Parallel Orchestrators"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [multi-agent-coordination, knowledge-base-architecture]
---

# Parallel Orchestrators

The rules Vepol uses to keep multiple AI agents (Claude, Codex, and
future ones) working from the same knowledge base **without forking**
into incompatible private states. The goal is **zero split-brain**:
any second agent must be able to continue where any first agent left
off, using files alone.

## The problem with naive multi-agent setups

If you give multiple AI agents access to the same project, the
obvious mistake is: each agent keeps its own session memory.
Agent A writes notes in its conversation. Agent B writes notes in
its conversation. The next time anyone wants to know what was
decided, they have to ask the right agent (because only the right
agent remembers).

What you've built is two separate brains pretending to be one. The
first time agent B has to make a decision based on what agent A
already established, you discover that agent B doesn't know about
it.

Vepol does not allow this. The rules below enforce a shared
substrate.

## The six rules

### 1. One source of truth

`~/knowledge/` and the per-project `knowledge/` folders are the
single source of truth. There is no "Claude memory" folder and no
"Codex memory" folder. There are markdown files. They live in
shared locations. All agents read and write the same shared files.

If a tool tries to introduce a per-agent private memory store
(some agent frameworks do this), Vepol's contract is to disable
that feature.

### 2. One write protocol

Any agent doing significant work follows the same write protocol:

- Significant decision → record in `log.md`
- Status change → update `state.md`
- Error or unexpected behavior → write incident in `incidents.md`
- New cross-project knowledge → write in `concepts/`,
  `solutions/`, etc., with the appropriate frontmatter
- New session work → daily capture goes in `daily/<date>.md`

The protocol does not depend on which agent is acting. It depends
only on what the agent did.

### 3. One coordination set

Tasks live in the [coordination triad](orchestrated-knowledge-base.md):
`backlog.md`, `escalations.md`, `incidents.md`. Both agents read and
write all three:

- New work → `backlog.md`
- Blocked / awaiting input → `escalations.md`
- Error / fix / prevention rule → `incidents.md`

If only one agent uses these files and the other has its own
parallel system, you've recreated the split-brain problem at the
coordination layer.

### 4. Same input discipline

Before doing significant work, *every* agent reads the same curated
context:

- Project `README.md` and `CLAUDE.md`
- `state.md`
- `index.md`
- The most recent entries in `log.md`
- If relevant: `backlog.md`, `escalations.md`, `incidents.md`
- If a cross-project question: hub `registry.md` and hub-level
  cross-project files

Both agents have the same starting point because both agents read
the same starting files. There is no "agent A starts with extra
context that agent B doesn't have."

### 5. Same output discipline

After significant work, the agent leaves a trail. If a tool has
automatic session capture, use it; otherwise the agent emulates
capture manually — not as an option, as part of the protocol.

The acceptance test for any session: **could a second agent, with
no access to this conversation, continue the work using only the
files?** If the answer is no, the output discipline failed.

### 6. No agent-private memory

Specifically forbidden:

- Per-agent training-style memories ("Claude remembers the user
  prefers X")
- Per-tool memory features that hide knowledge from other agents
- Agent-specific note files (`claude-memory.md`,
  `codex-cache.md`)

Allowed:

- A summary in agent-specific session memory **if** the original
  also lives in shared knowledge — the session memory is a
  pointer, not the source

## How the broker handles handoffs

When work needs to be dispatched to "an agent," Vepol uses a broker
that picks one of the available agents based on availability:

- Agent has rate limit headroom → eligible
- Agent's CLI is healthy → eligible
- Otherwise → fail over to the next agent

The agent that picks up the work reads the same files, follows the
same protocols, writes to the same outputs. The fact that "this
session was Claude" or "this one was Codex" is metadata in the log,
not a structural difference in what got done.

If the broker has only one agent available (the other is
rate-limited), the work proceeds with the available agent. The
single-point-of-failure case is when *all* agents are unavailable —
which is rare in practice.

## What this looks like in a session

A typical session under parallel-orchestrators discipline:

1. Session starts. Agent (whichever) reads project state files.
2. User asks for work. Agent does the work, writes results into
   appropriate files (concepts, log, daily, etc.).
3. Session ends. Auto-capture (or manual emulation) appends a
   one-line summary to `log.md` and a structured extract to
   `daily/<date>.md`.

The next session, with any agent:

1. Reads the same starting files. Sees the previous session's
   capture. Picks up where things left off.
2. Has full context. Doesn't ask the human "what did you mean
   yesterday?" because yesterday's session left a written record.

## What goes wrong without this discipline

Common failure modes when parallel-orchestrators discipline is not
followed:

- **The agent re-asks questions you already answered.** Because
  the previous session's answer wasn't captured.
- **Conflicting decisions.** Agent A decides X. Agent B, not
  knowing about the decision, decides not-X. The conflict surfaces
  weeks later.
- **Documented incidents repeat.** An error happened, was fixed
  via a chat conversation, no incident file written. Three months
  later the same error happens because there's no prevention
  rule.
- **The "right" agent for a task gets bottlenecked.** Because
  context is in agent A's memory, only agent A can do tasks that
  use that context. Failover doesn't actually fail over — it
  fails.

Each of these is the absence of one of the six rules above.

## Why this matters even with one agent

Even if you only ever use one AI agent today, the parallel-
orchestrators discipline pays off:

- It future-proofs you for adding a second agent later
- It survives upgrading your agent (today's Claude becomes
  tomorrow's Claude+1; the conversation memory is gone, but the
  knowledge base persists)
- It survives switching agents (Claude to Codex to something new)
- It produces an audit trail you can read yourself, six months
  later, when the agent's session memory is long gone

The point is **durable partnership continuity**: any authorized
agent can resume the work from shared context. Every other property
(multi-agent coordination, audit trail, cross-review) follows from
that.
