# Security policy

## Reporting vulnerabilities

If you find a security vulnerability in Vepol — **please report it
privately, not through a public issue**.

### How to report

Use GitHub's private vulnerability reporting:
<https://github.com/nahornyi-ai-lab/vepol/security/advisories/new>

This routes the report directly to the maintainers without making it
public. We will respond from there.

Please include:

- A description of the vulnerability and the affected component
- Steps to reproduce, ideally with a minimal proof of concept
- The version of Vepol affected (`cat ~/vepol/VERSION` on the user side)
- Your contact info if you want acknowledgement

### What to expect

- **Acknowledgement** within 72 hours
- **Initial assessment** within 7 days
- **Fix or mitigation** depending on severity:
  - Critical: targeted release within 14 days
  - High: targeted release within 30 days
  - Medium/Low: included in the next regular release

We will credit you in the changelog unless you prefer to stay
anonymous.

## What counts as a security issue

- Personal-data leak vectors (e.g. a Vepol script that exfiltrates user
  data, or a path that lets a clone of Vepol read files outside the
  knowledge directory)
- Privilege escalation through the installer or scripts
- Token or credential exposure (e.g. logging an API key)
- Code execution via crafted input to any Vepol CLI
- Supply-chain attacks (compromised dependency)

## What does NOT count

- Generic best-practice suggestions ("you should use 2FA") — open a
  regular issue
- Anything covered by the FSL competing-use clause — that's a license
  question, not security
- Issues in user-managed configuration (your own `~/.claude/settings.json`)
  unless Vepol's installer puts a real flaw there

## Supported versions

| Version | Status | Security fixes |
|---|---|---|
| 0.1.x | Current | Yes |
| <0.1 | Not released | N/A |

Older versions stop receiving security fixes one minor version after a
new minor release ships (e.g. when 0.2 ships, 0.0 stops; when 0.3
ships, 0.1 stops). Major versions promise longer support windows once
we reach 1.0.

## Disclosure policy

We follow coordinated disclosure:

1. You report privately
2. We confirm and assess
3. We develop a fix
4. We agree on a public-disclosure date with the reporter
5. We release the fix and publish the advisory
6. The reporter is credited (unless declined)

For critical issues affecting production users, we may release a fix
before the advisory is fully public, with a brief note.
