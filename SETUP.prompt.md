<!--
This is Vepol's agent setup prompt. A human copies the fenced block below from the
GitHub README (or this file) and pastes it to a coding agent (Claude Code, Codex, …)
with terminal access. The agent drives Vepol's deterministic installer; it never
re-implements installation. Manual install (git clone && ./install.sh) is the fallback.
-->

# Install Vepol with your agent

Copy everything inside the box and paste it to a coding agent that has terminal access:

```text
Install Vepol on this machine — a local AI operating environment for durable knowledge
and action. You DRIVE Vepol's installer; you do NOT re-implement it. I approve the steps.

Rules (non-negotiable):
- Never send my secrets, tokens, private paths, or knowledge-base contents off this machine.
- Ask me before anything that installs software, changes files outside the repo, loads a
  background service, or touches an account. Never use sudo or install a package manager.
- The installer (install.sh) and uninstall.sh / upgrade.sh do all file changes. If a tool,
  mode, or script you need is MISSING or behaves oddly, STOP and tell me — do not improvise.
- Treat empty or error output as failure, never "nothing to do."

1. Get Vepol. If ~/vepol doesn't exist, ask me, then:
   git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
   cd ~/vepol and read VERSION and README.md.

2. Check the installer is new enough:
   ./install.sh --capabilities --json
   If that errors, returns empty, or doesn't list --probe/--apply/--verify, STOP and tell me
   to update Vepol (or fall back to manual `./install.sh`). Do NOT run a bare ./install.sh
   hoping it just "looks" — on old versions it would install everything.

3. Look at the machine (changes nothing):
   ./install.sh --probe --json
   Tell me what's missing and whether a security migration is needed (needs_security_migration).

4. For anything missing, show me the exact command to run and let ME run it. Don't install it
   yourself. Re-run --probe after I fix things.

5. Show the plan, then install:
   ./install.sh --dry-run --json     # preview
   Ask which extras I want (scheduled tasks, Telegram, auto session-capture). Then:
   VEPOL_ENABLE_LAUNCHD=1 VEPOL_ENABLE_TELEGRAM=1 VEPOL_ENABLE_MEMORY_COMPILER=1 ./install.sh --apply
   Include only the VEPOL_ENABLE_* I approved; leave the rest off.

6. If --probe reported needs_security_migration, explain why it matters, get my explicit OK,
   then re-run apply with VEPOL_APPLY_C01=1. Never set that on your own.

7. Verify:
   ./install.sh --verify --json   and   kb-doctor
   Everything should be green. (kb-* commands live in ~/knowledge/bin/ — run them
   from there if they're not on my PATH yet.)

8. Quick proof it works (run and tell me what each shows):
   kb-doctor → kb-demo brief → kb-task "My first Vepol task" → kb-search "first Vepol"

9. If something fails: fix ONE thing at a time, ask before side effects, re-run the same check.
   After 3 failed tries, stop and hand it back to me. Never weaken a security/privacy check to
   make an error go away.

10. If a fresh install must be undone: ./uninstall.sh  (it removes only Vepol's managed files
    and never deletes my data). If uninstall.sh is missing, STOP — don't delete anything by hand.

11. Read me the install receipt the installer wrote under ~/knowledge/install/receipts/, and
    summarize: version, what's installed, extras on, anything left to do.
```

---

## Prefer to do it by hand?

```bash
git clone https://github.com/nahornyi-ai-lab/vepol ~/vepol
cd ~/vepol
./install.sh
```

`./install.sh` walks you through the same steps interactively. See
[`docs/getting-started.md`](docs/getting-started.md),
[`docs/dependency-matrix.md`](docs/dependency-matrix.md), and
[`docs/security-and-privacy.md`](docs/security-and-privacy.md).
