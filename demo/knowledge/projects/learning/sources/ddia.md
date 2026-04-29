---
title: "Designing Data-Intensive Applications (Kleppmann)"
type: book-summary
date_finished: 2026-04-20
status: finished
takeaways-pending-lift: 3
tags: [systems, distributed-systems]
---

# Designing Data-Intensive Applications

By Martin Kleppmann. Read 2026-03-15 to 2026-04-20.

## One-paragraph TL;DR

A textbook on the foundations of modern data systems — storage,
retrieval, transactions, distribution, consensus, derived data. Dense
but well-organized; chapters can be read non-linearly after the first
three. Most useful for the mental model it builds about which tradeoffs
exist (consistency vs availability, batch vs streaming, transactions
vs scale) — less useful as a how-to manual.

## Structure

- Part I (chapters 1-4): Foundations — reliability, scalability,
  maintainability; data models; storage and retrieval; encoding.
- Part II (chapters 5-9): Distributed Data — replication, partitioning,
  transactions, the trouble with distributed systems, consistency and
  consensus.
- Part III (chapters 10-12): Derived Data — batch processing,
  stream processing, the future.

## Three takeaways pending lift to hub `concepts/`

### 1. Consensus algorithms (chapter 9)

The framing in chapter 9 of consensus as "getting several nodes to agree
on something" with the explicit cost of consensus (round-trip latency,
quorum requirement, partition behavior) is the densest piece in the
book. Applies to:

- **Work** — client systems where we need to discuss concurrency control
- **Family** — joint decisions: a family-level analog of consensus
  (when do we need majority? when does any one veto suffice? when is
  the absence of objection enough?)

To lift as `~/knowledge/concepts/consensus-as-decision-protocol.md`.

### 2. Partition tolerance vs availability (chapter 8)

The CAP triangle as an explanation tool, not a hard tradeoff. The actual
tradeoff is "what do you do during a partition?" — return stale data,
refuse the request, or block. Each is a deliberate design choice with
specific consequences. Applies to:

- **Family** — when one parent is unavailable for a decision, what's
  the protocol? Defer (refuse), use last known preference (stale), or
  block all decisions until both available?
- **Work** — when a client contact is unavailable for a question, same
  three choices.

To lift as `~/knowledge/concepts/partition-handling-pattern.md`.

### 3. Derived data (chapter 11-12)

The framing of "primary state + derived views" — where the source of
truth lives in one place, and consumers maintain their own indexes/
caches that are eventually consistent with the source. Applies
directly to Vepol itself:

- **Vepol architecture** — `~/knowledge/` is the primary state; the
  `concepts/`, `people/`, `companies/` lifted pages are derived data
  that re-summarizes the primary state at a higher level. The lifting
  cycle is exactly the "rebuild the derived view" pattern.

To lift as `~/knowledge/concepts/primary-state-and-derived-views.md`.

## What I'd read after this

- *Database Internals* (Petrov) — for going deeper on storage engines
- *Designing Data-Intensive Applications* — re-read chapter 9 in 6
  months; first read was dense, second pass should consolidate

## What I would not recommend

- Skipping chapters 1-4 to "get to the interesting parts." The
  foundations chapters are where the vocabulary is built; without
  them, chapters 7-9 don't connect.
