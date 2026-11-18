# Incidents — {{PROJECT_NAME}}

Every error, broken deploy, stuck integration, or unexpected behavior that had to be fixed by hand is **recorded here**. After the fix, the agent must ask itself: "what would stop this from happening again?" — and if the answer is more than "be more careful", set up automation (a hook, a CI check, a cron script, a pre-commit, an alert) or at least a rule in the `Prevention rules` section.

## Ongoing

<!-- Current open incidents. Format:
### [YYYY-MM-DD HH:MM] <short title>
- Symptoms: ...
- Tried so far: ...
- Next: ...
-->

## Resolved

<!-- After the fix:
### [YYYY-MM-DD] <title>
- Symptoms: what we saw
- Root cause: what actually broke
- Fix: what we changed
- Prevention: rule / automation (if any) or a link to Prevention rules below
-->

## Prevention rules

Rules distilled from the incidents above. Short imperatives. The agent checks them before risky actions.

<!-- Format:
- <one-line rule> — source: [YYYY-MM-DD incident]
-->

## Automated guards

A list of automations (hooks, checks, scripts) set up from these incidents — so the agent knows they are already in place and does not duplicate them.

<!-- Format:
- <what is automated> — where: <path or system> — from incident: [YYYY-MM-DD]
-->
