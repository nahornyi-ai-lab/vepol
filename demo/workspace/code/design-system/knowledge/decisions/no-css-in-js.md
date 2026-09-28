---
title: "Components ship without CSS-in-JS"
date: 2026-09-17
status: proposed
tags: [components, performance]
---

# Components ship without CSS-in-JS

## Context

acme-web now server-renders checkout. Runtime CSS-in-JS would add a style
engine to every page and fight the server rendering.

## Proposal

Components use class names plus the generated `tokens.css`. The inline styles in
`Button.tsx` are a stop-gap until the migration guide is out.

## Open point

Whether to switch before or after the billing admin pages move to v3. Waiting for
the owner.
