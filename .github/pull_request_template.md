## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Why

## How it was tested

- [ ] `HOME="$(mktemp -d)" bash tests/run-all.sh` passes (needs `pytest` for your `python3`: `python3 -m pip install --user pytest`)
- [ ] `cd face && .venv/bin/python -m pytest -q tests` passes (if `face/` changed; the `.venv` is made with Python 3.11+ and needs `.venv/bin/pip install -r requirements.txt pytest httpx`)

## Checklist

- [ ] Docs and `CHANGELOG.md` ("Unreleased") updated if behavior changed
- [ ] Repository text is in English; user-facing text goes through the per-language tables
- [ ] No personal data (names, tokens, chat IDs, private notes)
