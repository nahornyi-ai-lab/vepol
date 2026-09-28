---
title: "Server-render the checkout pages"
date: 2026-09-10
status: accepted
tags: [checkout, performance]
---

# Server-render the checkout pages

## Context

The old checkout is a single-page app that downloads 480 KB of JavaScript before
the shopper sees the first field. On mid-range phones the payment step takes
4-6 seconds to become usable, and most abandoned carts drop off there.

## Decision

Checkout v2 renders every step on the server and adds small scripts only where a
step needs them (card field, address autocomplete). The cart stays client-side.

## Consequences

- First usable paint on the payment step target: under 1.5 s on a mid-range phone.
- Payment errors are rendered by the server, so they read the same with scripts off.
- Two rendering styles live side by side until the old checkout is removed.

## Alternatives considered

- Code-splitting the existing app: saves about a third of the bundle, not enough.
- A separate checkout subdomain: extra cookies and CORS work for little gain.
