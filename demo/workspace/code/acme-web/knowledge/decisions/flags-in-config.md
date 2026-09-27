---
title: "Feature flags live in a config file, not a flag service"
date: 2026-09-16
status: accepted
tags: [release, flags]
---

# Feature flags live in a config file, not a flag service

## Context

Checkout v2 needs a percentage rollout. We have three flags, one deploy a day and
no one on call for a hosted flag service.

## Decision

Flags live in `config/flags.json` as `{ "percent": N }` and ship with the deploy.
A shopper is in a rollout when a stable hash of their id (0-99) is below `percent`.
Changing a percentage is a one-line pull request that anyone can review.

## Consequences

- Rolling back a flag takes one deploy (about 6 minutes), not an instant toggle.
- The flag history is the git history of one file.
- Revisit if we need more than about ten flags or per-customer targeting.
