# Backlog — acme-web

## Backlog

- [ ] Remove the old checkout
  plan_item_id: aw-7
  priority: P2
  owner: unassigned
  created: 2026-09-08
  updated: 2026-09-08
  acceptance: |
    No route serves the old checkout and its bundle is gone from the build.
  body: |
    One week after checkout v2 reaches 100%.

## Ready

- [ ] Raise checkout-v2 to 50% of shoppers
  plan_item_id: aw-5
  priority: P2
  owner: unassigned
  created: 2026-09-23
  updated: 2026-09-23
  acceptance: |
    flags.json at 50% and the dashboard shows the error rate for the 3 days before.
  body: |
    Only after the error rate has held under 0.5% for 3 days (prevention rule).

## In Progress

- [>] Saved addresses in checkout v2
  plan_item_id: aw-4
  priority: P2
  owner: unassigned
  created: 2026-09-26
  updated: 2026-09-26T10:00:00Z
  claim_owner: claude
  claim_id: clm-120af4e605a4
  claim_expires_at: 2026-09-26T10:15:00Z
  acceptance: |
    A returning shopper completes checkout without typing an address.
  body: |
    Signed-in shoppers pick a saved address; the form reuses design-system text inputs.

## Blocked

- [ ] Apple Pay button on the payment step
  plan_item_id: aw-6
  priority: P2
  owner: unassigned
  created: 2026-09-19
  updated: 2026-09-24T16:00:00Z
  blocked_reason: |
    waiting for billing-api to publish the Apple Pay domain verification file
  acceptance: |
    Apple Pay completes a test order on staging.
  body: |
    Needs the domain verification file that billing-api publishes for the merchant account.

## Done

- [x] Server-render the checkout pages
  plan_item_id: aw-1
  priority: P2
  owner: unassigned
  created: 2026-09-08
  updated: 2026-09-12T17:00:00Z
  acceptance: |
    The payment step is usable in under 1.5 s on a mid-range phone.
  evidence: |
    closed
  body: |
    Render every checkout step on the server; keep small scripts only for the card field.

- [x] Card payments in checkout v2
  plan_item_id: aw-2
  priority: P2
  owner: unassigned
  created: 2026-09-10
  updated: 2026-09-15T17:00:00Z
  acceptance: |
    A test order completes on staging and shows one ledger row in billing-api.
  evidence: |
    closed
  body: |
    Card entry, 3-D Secure and the receipt page against the billing-api sandbox.

- [x] Add the checkout-v2 flag to config/flags.json
  plan_item_id: aw-3
  priority: P2
  owner: unassigned
  created: 2026-09-16
  updated: 2026-09-17T17:00:00Z
  acceptance: |
    Setting percent to 0 sends every shopper to the old checkout.
  evidence: |
    closed
  body: |
    Percentage rollout by a stable hash of the shopper id.
