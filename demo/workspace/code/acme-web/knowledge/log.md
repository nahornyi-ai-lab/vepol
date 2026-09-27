# acme-web — log

Append-only. Format: `## [YYYY-MM-DD] <category> | acme-web | "<summary>"` and a short body.

## [2026-09-08] milestone | acme-web | "Checkout v2 work started"

Goal: a faster checkout that loses fewer carts on phones. Scope: payment step,
addresses, Apple Pay. The old checkout keeps running until v2 is at 100%.

## [2026-09-10] decision | acme-web | "Checkout pages will be server-rendered"

The old single-page checkout needs 4-6 s to become usable on mid-range phones.
See decisions/checkout-server-rendering.md.

## [2026-09-12] fix | acme-web | "Double charge on slow networks fixed"

Two shoppers were charged twice after tapping "Pay" again on a slow connection.
The submit button now locks on the first click and every attempt sends one
idempotency key; billing-api rejects repeats. Rule added to incidents.md.

## [2026-09-15] milestone | acme-web | "Card payments work end to end in checkout v2"

Card entry, 3-D Secure and the receipt page pass on staging with the billing-api
sandbox. Task closed by claude.

## [2026-09-16] decision | acme-web | "Feature flags move into config/flags.json"

No hosted flag service: three flags, one deploy a day. See decisions/flags-in-config.md.

## [2026-09-19] release | acme-web | "Checkout v2 live for 5% of shoppers"

First real traffic. Error rate 0.4% against 0.6% on the old checkout; median time
on the payment step 38 s against 71 s.

## [2026-09-23] release | acme-web | "Checkout v2 raised to 20%"

Error rate held at 0.3% for three days. Next step is 50% after saved addresses.

## [2026-09-24] blocker | acme-web | "Apple Pay waits on billing-api"

Apple Pay needs the domain verification file served from our domain; billing-api
owns the merchant account and has to publish it. Task moved to Blocked.

## [2026-09-26] progress | acme-web | "Saved addresses started"

The address form reuses the design-system text inputs, so it picks up the v3
focus ring for free. Open question for the owner: guests too, or signed-in only?
