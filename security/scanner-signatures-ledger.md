# Scanner signatures ledger — hub-level

Authority record for `catalogue-revision` entries per
[`/Users/macbook/vepol-dev/knowledge/decisions/context-injection-scanner-v2.md`](/Users/macbook/vepol-dev/knowledge/decisions/context-injection-scanner-v2.md)
§ Catalogue location and protocol.

This is a **peer ledger** to `~/knowledge/promotions.md` — same append-only
YAML-block structure, same multi-party authorization, but its own
independent hash chain over catalogue revisions. Not nested under
`promotions.md`.

**Strict rules:**
- Append-only. No in-place edits.
- `write_allowlist` excludes every capability except the dedicated reviewer
  capability `scanner-catalogue-reviewer` (requires human + quorum reviewer
  multi-party auth).
- Strict YAML-block parse. Each entry has its own ```yaml ... ``` fence.
- Date is ISO 8601 UTC second-resolution timestamp.
- `previous_catalogue_sha256` must match the prior revision's recorded hash
  (chain integrity). Genesis r001 skips this check.
- `fcntl` advisory lock on append; writers re-read latest state before
  appending. Single-machine POSIX scope only.
- Fail-closed: missing, unreadable, or malformed ledger → all
  scanner runs refuse with `verdict_reason: catalogue-unavailable`.

---

## [2026-05-27T00:00:00Z] catalogue-revision | r001

```yaml
entry_id: cat-rev-2026-05-27-001
type: catalogue-revision
revision_id: r001
catalogue_path: ~/knowledge/security/scanner-signatures/r001.md
catalogue_sha256: c68bfae18dbd9c8b1b16fb24b91cfb81427c553aa49b9032802c96526c848804
previous_revision_id: none
previous_catalogue_sha256: none
date: 2026-05-27T00:00:00Z
quorum:
  codex: approve
  claude_code: approve
  gemini_cli: approve
safety_veto: false
diff_summary: genesis revision; seed catalogue (16 signatures across families A-E)
written_by:
  - human: vadym@nahornyi.ai
  - reviewer_capability: scanner-catalogue-reviewer
signature: r001-genesis
```
