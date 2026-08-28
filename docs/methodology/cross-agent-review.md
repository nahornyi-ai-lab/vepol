---
title: "Lightweight Spec Review"
status: stable
type: methodology
parent: orchestrated-knowledge-base
applies-to: [non-trivial-specs, design-decisions, migrations, infrastructure]
---

# Lightweight Spec Review

Vepol uses one independent review of a non-trivial specification before owner
approval and code. Its job is narrow: compare the stated scenario with the real
code/API/schema and catch a gross logic mistake that would make the path fail.

This is not a second design process. The reviewer asks concise questions and
pulls toward the smallest working path. It does not try to find an objection.

## When it applies

Run it once for any non-trivial spec, including architecture, migrations,
dependencies, infrastructure, security/auth behavior, public install/usage
contracts, and cross-project methodology. Trivial work defined by the
[Development Loop](development-loop.md) skips it.

## Inputs

The author provides:

- Spec path
- `spec-contract` hash for traceability
- One-sentence stated scenario
- Concrete code/API/schema files the spec relies on

The reviewer must read those files. A finding without a `file:line` or an exact
contract citation cannot be a blocker.

## What the reviewer checks

Only four questions:

1. Can the stated path physically produce the stated result?
2. Do source and receiver parameters match in name, type, requiredness, format,
   and transport?
3. If the real API/code offers several paths or addresses, does the spec choose
   the one it will use?
4. Is a branch inside the stated scenario left undefined?

The reviewer may ask, for example: “How will this be implemented?”, “Which
parameters do we actually send?”, “Do we need both paths, or only one?”, or
“Can this be simpler?”. A question asks for an answer; it does not add a
requirement.

## Hard boundaries

Unless explicitly inside the stated scenario, do not raise or expand:

- security hardening or speculative threats
- observability, logs, metrics, or operational dashboards
- scaling, future-proofing, or hypothetical future scenarios
- rollback or migration machinery for paths not being built now
- code style, documentation completeness, or extra test ideas
- a more complete architecture than the minimal working path needs

Do not enumerate generic risks. Do not design states, invariants, locks, or
contracts for the author. Ask the shortest useful question.

## Output contract

Return exactly one of these and nothing else:

```
GO
<one line: what was checked in the code>
```

```
QUESTIONS (maximum 3)
1. <question> — why: <one phrase> — <file:line>
2. ...
3. ...
<one line: what was checked in the code>
```

```
BLOCK
<what is impossible>
<file:line or contract citation proving impossibility>
<the minimum change that makes it possible — one sentence>
```

`BLOCK` means direct, demonstrated logical incompatibility: not “risky”, not
“incomplete”, and not “may break”. If unsure between QUESTIONS and BLOCK,
choose QUESTIONS. If unsure between QUESTIONS and GO, choose GO.

## Anti-loop rule

After `GO` or the author's answers to `QUESTIONS`, review is complete.
A changed spec hash alone never invalidates the review and never triggers a fresh pass.
Do not add a second reviewer for completeness.

A genuine `BLOCK` allows one narrow delta check. The reviewer answers only
`RESOLVED` or `STILL BLOCKED` against the original citation.
**New findings are not accepted during the delta check.** If that reviewer is unavailable, the
owner may lift or keep the blocker; do not start a replacement-agent cascade.

Owner approval remains exact-hash: if scope, acceptance, public behavior,
security/privacy, migration, or mandatory E2E materially changes after owner
approval, write the new contract, run one lightweight review for that new
scenario, and ask the owner again. Wording changes and answers to review
questions do not create repeated review rounds.

## Canonical reviewer prompt

```text
You are an independent specification reviewer. This is exactly one pass. Your
job is not to find objections; it is to confirm that the stated scenario can
physically work by the path described in the spec.

INPUT
- Spec: <path>
- Hash: spec:<algo>:<hash>
- Stated scenario: <one sentence>
- Relevant code and contracts: <paths to modules, schemas, migrations, API docs,
  and integration points>

DO
1. Read the entire spec.
2. Read the listed code, schemas, and API contract. A blocking finding without
   a concrete file:line or contract citation is invalid.
3. Check only:
   a) the stated path can produce the stated result;
   b) source and receiver parameters match;
   c) when several real paths/addresses exist, the spec chooses the intended one;
   d) no branch inside the stated scenario is undefined.
4. Prefer the simplest working path. Ask a short question instead of proposing a
   larger design.

DO NOT
- Search for a comment at any cost.
- Expand security hardening, observability, scaling, rollback, future scenarios,
  style, documentation, or tests unless explicitly in scope.
- List generic risks or design a fuller architecture for the author.

OUTPUT — exactly one

GO
<one line: what you checked in the code>

or

QUESTIONS (maximum 3)
1. <question> — why: <one phrase> — <file:line>
2. ...
3. ...
<one line: what you checked in the code>

or

BLOCK
<what is impossible>
<file:line or contract citation proving impossibility>
<minimum change that makes it possible — one sentence>

BLOCK is only for direct, demonstrated logical incompatibility that makes the
stated scenario impossible. If unsure between QUESTIONS and BLOCK, choose
QUESTIONS. If unsure between QUESTIONS and GO, choose GO.
```

## Durable trace

Record the reviewer, date, scenario, result, and any author answers in the spec
or project log. The trace is short; it does not need a risk register or another
approval format.

Knowledge gaps discovered while checking a real external API still follow the
normal KB delegation rule: resolve the fact in `knowledge/sources/` or
`concepts/`, then return to the same one-pass review.
