# Contributing to Vepol

Thank you for helping. Bug reports, fixes, docs and new ideas are all welcome.

- **Found a bug?** [Open an issue](https://github.com/nahornyi-ai-lab/vepol/issues/new/choose) with your macOS version, Vepol version (`cat ~/vepol/VERSION`) and what `kb-doctor` says.
- **Found a security problem?** Do not open a public issue; follow [SECURITY.md](SECURITY.md).
- **Want to change something non-trivial?** Open an issue first, so we can agree on the shape before you write code.

## Set up a development checkout

You need macOS 13 or later and the same tools the installer checks for: bash 5, Python 3.10+ (3.11+ for Vepol Desktop), ripgrep, git and Claude Code. Vepol Desktop also needs an Apple Silicon Mac, the Command Line Tools and `tmux`.

```bash
git clone https://github.com/nahornyi-ai-lab/vepol
cd vepol
python3 -m pip install --user -r requirements.txt
python3 -m pip install --user pytest           # tests/run-all.sh runs pytest suites

# Vepol Desktop (optional)
cd face
"$(brew --prefix)/bin/python3" -m venv .venv
.venv/bin/python --version                     # must print 3.11 or later
.venv/bin/pip install -r requirements.txt pytest httpx
```

If pip answers `externally-managed-environment` (Homebrew's Python does), add `--break-system-packages` after `--user`. Name the Desktop venv's Python as above, because a plain `python3` may be Apple's 3.9; any Python 3.11 or later works.

## Run the tests

`tests/run-all.sh` is the release gate: the core suites (task board, search, installer, health checks, orchestration) and the daily-routine suites (morning brief, evening retro, audio digests, mail, calendar, people, research, money radar, user language). Run it with a throwaway home folder so nothing touches your own `~/knowledge`:

```bash
HOME="$(mktemp -d)" bash tests/run-all.sh
```

It ends with `ALL Phase 1b tests passed`. The suites put stand-ins for the agent CLIs first on `PATH`, so they never reach your logged-in Claude Code or Codex. Some suites run with `python3 -m pytest`, so `pytest` must be installed for the `python3` on your `PATH` (see the setup above).

One check runs a command the way launchd would, with launchd's `PATH`, where `python3` is Homebrew's. Install the Python packages for that interpreter too (`/opt/homebrew/bin/python3 -m pip install --user --break-system-packages -r requirements.txt`), or that check fails while everything else passes.

Vepol Desktop has its own suite. It needs `pytest` and `httpx` in the app's `.venv`, which the setup above installs:

```bash
cd face
.venv/bin/python -m pytest -q tests
```

## How we work

- **Spec first for non-trivial changes.** Write a short spec, then failing tests, then the code. See the [spec-driven workflow](docs/methodology/spec-driven-workflow.md) and the [development loop](docs/methodology/development-loop.md).
- **One independent review for every non-trivial spec.** A second agent or person reviews the spec once, lightly, before implementation starts; trivial changes, as the development loop defines them, skip it ([cross-agent review](docs/methodology/cross-agent-review.md)).
- **Keep the stable core stable.** The knowledge folder layout, the `kb-board` task-board format and commands, and `install.sh` / `upgrade.sh` change incompatibly only in a new major version.
- **Record user-visible changes** under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).

## Language in the repository

Everything in the repository is written in English: code, comments, messages, docs, templates and the prompts Vepol sends to agents.

Vepol itself speaks the user's language, set by `language:` in `~/knowledge/personal/profile.yaml`. So:

- Text a user reads (Telegram messages, brief headers, captions) goes through a per-language table keyed by that setting, with English as the default. `bin/kb-brief` and `bin/kb-money-radar` show the pattern.
- Prompts are written in English and tell the agent which language to answer in.
- Other languages appear only in those tables, in patterns that must match text in that language (dates, keywords), and in tests that exercise them.

## Pull requests

- Keep each pull request to one change, and say what it changes and why.
- Run `tests/run-all.sh` (and the Desktop suite if you touched `face/`) and mention the result.
- Update the docs and the changelog when behavior changes.
- Never commit personal data: real names, addresses, tokens, chat IDs or anything from your own `~/knowledge`. Use the invented demo workspace in `demo/` for examples.

## License

Vepol is licensed under [FSL-1.1-MIT](LICENSE). By submitting a contribution you agree that it is licensed under the same terms.
