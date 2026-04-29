# Vepol Commercial Use FAQ

> **Note:** This document explains common scenarios under the
> [FSL-1.1-MIT license](LICENSE) in plain English. The legal text in
> `LICENSE` is authoritative — if there is any conflict, the legal text
> wins. This document has not yet been reviewed by counsel for v0.1.0;
> a professional review is planned before v1.0.0. **For high-stakes
> commercial scenarios, consult your own lawyer.**

## TL;DR

| Use case | Allowed under FSL? | Need commercial license? |
|---|---|---|
| Personal use on your own machines | ✅ Yes | No |
| Internal use at your company | ✅ Yes | No |
| Modify and self-host for your own org | ✅ Yes | No |
| Provide consulting using Vepol for a client | ✅ Yes | No |
| Fork for non-competing purposes | ✅ Yes | No |
| Build a hosted SaaS that competes with Vepol | ❌ No | Yes |
| Resell Vepol under another brand | ❌ No | Yes |

After 2 years from each release date, that release automatically becomes
[MIT](LICENSE-FUTURE.md) and all restrictions lift.

## Common scenarios

### "Can I use Vepol for my personal projects?"

Yes. Without restriction. No license needed.

### "Can I install Vepol on my work laptop?"

Yes. Internal company use is a Permitted Purpose under FSL.

### "Can I install Vepol for a client as part of a consulting engagement?"

Yes. FSL explicitly permits "professional services that you provide to a
licensee using the Software." The client gets the FSL license too, and
you can charge for your time setting up and customizing it.

### "Can I fork Vepol and add my own features?"

Yes, as long as your fork isn't a *competing* product. You must keep the
FSL notice and not remove copyright. If your fork is internal to your
company, you don't need to publish it.

### "Can I publish my fork on GitHub?"

Yes — under FSL, with our copyright preserved. If your fork is
genuinely a different product (different audience, different purpose),
you can publish it. If it's "Vepol but with our branding offered as a
managed service," that's a Competing Use → contact us for a commercial
license.

### "Can I host Vepol as a managed service for paying customers?"

Not under FSL. Hosted/SaaS that substitutes for Vepol is a Competing
Use. Contact us for a commercial license — we're happy to discuss
reasonable terms.

### "Can I include Vepol in my employer's internal tooling?"

Yes. Internal company use is permitted.

### "Can my company's open-source program office (OSPO) ship Vepol-derived code?"

It depends on what they ship. If they ship it as part of an internal
tool or as professional services to clients — yes, no license needed. If
they ship a public competing product — that's a Competing Use → contact
us.

### "Can I contribute back to Vepol?"

Yes, please. Contributions are accepted under the same FSL-1.1-MIT
terms. See [CONTRIBUTING.md](CONTRIBUTING.md) when published.

### "What if I'm not sure my use case fits?"

Email us. We're a small team and we read every message. Default
disposition: **try to find a way to say yes.** Vepol is meant to help
people, not to be a legal trap.

## Commercial license inquiries

If your use case requires a commercial license (hosted competing
service, brand resale, or pre-conversion access on terms different from
FSL), email us:

**Contact:** Open an issue in the public repository at
<https://github.com/nahornyi-ai-lab/vepol/issues> with the label
`commercial-license-inquiry`. We will reply with a short scoping
question or move to direct email.

Pricing varies by use case and company size:

- Small companies / startups: typically $500-2000/year
- Mid-size companies: typically $2000-10000/year
- Large enterprises: case-by-case

We try to keep the pricing reasonable. Vepol is a tool, not a
gatekeeper.

## Frequently misread

> "FSL is more restrictive than AGPL."

Not really. AGPL forces you to release source code of any modifications
*if you offer the software as a network service* — which is a strong
viral effect. FSL just says "don't compete with us as a managed service"
and lets everything else through. For most users, FSL is **less**
restrictive than AGPL.

> "I can't use FSL software in commercial products."

Yes you can — for any internal use, professional services, or
non-competing commercial product. The only restriction is offering it as
a competing managed service to others.

> "FSL stops you from forking."

It doesn't. Fork freely. Just don't sell the fork as a competing managed
service.

## See also

- [LICENSE](LICENSE) — full legal text (authoritative)
- [LICENSE-FUTURE.md](LICENSE-FUTURE.md) — explanation of MIT conversion
- [Official FSL FAQ](https://fsl.software/) — Sentry's explanation
