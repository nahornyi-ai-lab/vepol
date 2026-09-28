---
title: "Design tokens are plain JSON, one source for web and email"
date: 2026-09-09
status: accepted
tags: [tokens]
---

# Design tokens are plain JSON, one source for web and email

## Context

Colours were defined three times: in CSS variables, in the email templates and in
the admin theme. They drifted; the order-confirmation email used an old blue.

## Decision

`tokens/colors.json` is the only place a colour is defined. The build writes CSS
variables for the web and a flat JSON file for the email templates.

## Consequences

- A colour change is one line and one release.
- Email templates must be rebuilt when tokens change (added to the release checklist).
