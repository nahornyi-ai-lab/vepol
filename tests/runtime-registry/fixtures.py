#!/usr/bin/env python3
"""fixtures.py — hermetic suite for kb-runtime-registry.

Spec: decision page "Runtime capability registry" (2026-08-15, contract sha256
3f323b89…) and its build plan (2026-09-01) in the project knowledge base.

Drives the REAL binary as a subprocess against a sandbox hub (KB_HUB=<tmp>,
KB_CLAUDE_RUN_ROOT=<tmp>/claude-runs). The sandbox roster points at fake
executables that append every invocation to <tmp>/calls.log, so each test can
assert that a probe did (or did not) run. A fake bin/kb-claude-run in the
sandbox execs the command after `--`, so the production Claude launch path is
exercised without the durable runner.

The suite itself runs NON-NESTED by construction: the agent-session markers
are stripped from the environment handed to the binary (same construction as
Face E7). T7 re-adds one marker to prove the refusal path.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile

# The suite tests its own tree: <tree>/tests/runtime-registry/fixtures.py drives
# <tree>/bin/kb-runtime-registry, so a shipped copy never silently tests the hub.
HUB_LIVE = pathlib.Path(__file__).resolve().parents[2]
BIN = HUB_LIVE / "bin" / "kb-runtime-registry"
PKG = HUB_LIVE / "bin" / "_kb_runtime_registry"
SCHEMA = PKG / "schema.json"
LIVE_CACHE = HUB_LIVE / ".orchestrator" / "runtime-registry.json"

# Copied from vepol-face/vepol_face/broker.py (SESSION_ENV_PREFIXES / _EXACT);
# the hub cannot import Face, and the registry must use the same list.
SESSION_ENV_PREFIXES = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_", "CODEX_COMPANION_")
SESSION_ENV_EXACT = (
    "CLAUDECODE", "CLAUDE_EFFORT", "CLAUDE_PLUGIN_DATA", "AI_AGENT", "ANTHROPIC_BASE_URL",
)

TOKENS = {
    "claude": "CLAUDE_OK",
    "codex": "CODEX_OK",
    "agy": "AGY_OK",
    "grok": "GROK_OK",
    "opencode": "OPENCODE_OK",
    "hermes": "HERMES_OK",
}
ROSTER_NAMES = ["claude", "codex", "agy", "grok", "notebooklm", "opencode", "hermes"]
FIELDS = [
    "installed", "authenticated", "quota_available", "healthy",
    "resumable", "interactive", "web_current", "edit_capable",
]
NOW = "2026-08-15T12:00:00Z"


def assert_(cond, msg):
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def clean_env() -> dict:
    env = dict(os.environ)
    for key in list(env):
        if key in SESSION_ENV_EXACT or key.startswith(SESSION_ENV_PREFIXES):
            env.pop(key, None)
    return env


FAKE_RUNTIME = """#!/usr/bin/env bash
# fake {name}: logs the call, then behaves per the mode file.
printf '%s %s\\n' "{name}" "$*" >> "{log}"
mode="token"
[[ -f "{modes}/{name}" ]] && mode="$(cat "{modes}/{name}")"
case "$mode" in
  token)            printf '  {token} \\n' ;;
  token-extra)      printf 'preface line\\nnoise {token} trailing\\n' ;;
  lower)            printf '%s\\n' "$(printf '{token}' | tr '[:upper:]' '[:lower:]')" ;;
  empty)            : ;;
  fail-with-token)  printf '{token}\\n'; exit 1 ;;
esac
exit 0
"""

FAKE_CLAUDE_RUN = """#!/usr/bin/env bash
# fake kb-claude-run: logs, then execs the command after `--`.
printf 'kb-claude-run %s\\n' "$*" >> "{log}"
while [[ $# -gt 0 && "$1" != "--" ]]; do shift; done
[[ "${{1:-}}" == "--" ]] && shift
exec "$@"
"""


class Sandbox:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.orch = root / ".orchestrator"
        self.bin = root / "bin"
        self.fakebin = root / "fakebin"
        self.modes = root / "modes"
        self.log = root / "calls.log"
        for d in (self.orch, self.bin, self.fakebin, self.modes, root / "claude-runs"):
            d.mkdir(parents=True, exist_ok=True)
        self.log.write_text("")
        for name, token in TOKENS.items():
            self._script(self.fakebin / name, FAKE_RUNTIME.format(
                name=name, token=token, log=self.log, modes=self.modes))
        self._script(self.fakebin / "notebooklm",
                     f"#!/usr/bin/env bash\nprintf 'notebooklm %s\\n' \"$*\" >> \"{self.log}\"\nexit 0\n")
        self._script(self.bin / "kb-claude-run", FAKE_CLAUDE_RUN.format(log=self.log))
        (self.orch / "cli-tools.tsv").write_text(
            "# sandbox roster\n"
            "claude     | which-any | claude | write code\n"
            f"codex      | path-any  | {self.fakebin}/codex | review\n"
            f"agy        | path-any  | {self.fakebin}/agy:agy | third pass\n"
            f"grok       | path-any  | {self.fakebin}/grok | social\n"
            f"notebooklm | path-any  | {self.fakebin}/notebooklm | audio\n"
            f"opencode   | path-any  | {self.fakebin}/opencode:opencode | backup | fallback-of: grok\n"
            f"hermes     | path-any  | {self.fakebin}/hermes:hermes | always-on agent\n"
        )

    @staticmethod
    def _script(path: pathlib.Path, body: str) -> None:
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    @property
    def state(self) -> pathlib.Path:
        return self.orch / "state.json"

    @property
    def cache(self) -> pathlib.Path:
        return self.orch / "runtime-registry.json"

    def set_mode(self, name: str, mode: str) -> None:
        (self.modes / name).write_text(mode)

    def calls(self) -> list[str]:
        return [l for l in self.log.read_text().splitlines() if l.strip()]

    def env(self, extra: dict | None = None) -> dict:
        env = clean_env()
        env["KB_HUB"] = str(self.root)
        env["KB_CLAUDE_RUN_ROOT"] = str(self.root / "claude-runs")
        env["PATH"] = f"{self.fakebin}:{env.get('PATH', '')}"
        env["KB_RUNTIME_REGISTRY_PROBE_TIMEOUT"] = "30"
        if extra:
            env.update(extra)
        return env

    def run(self, *args: str, extra_env: dict | None = None, now: str | None = NOW):
        argv = [str(BIN)] + list(args)
        if now:
            argv += ["--now", now]
        return subprocess.run(argv, capture_output=True, text=True, env=self.env(extra_env))

    def run_json(self, *args: str, **kw) -> tuple[subprocess.CompletedProcess, dict]:
        proc = self.run(*args, "--json", **kw)
        doc = json.loads(proc.stdout) if proc.stdout.strip() else {}
        return proc, doc


def by_name(doc: dict) -> dict:
    return {r["name"]: r for r in doc["runtimes"]}


def load_output_module():
    """Import the shipped validator exactly as the binary does (hub bin on sys.path)."""
    sys.path.insert(0, str(PKG.parent))
    import _kb_runtime_registry.output as out  # noqa: E402
    return out


def iso(offset_hours: float) -> str:
    base = dt.datetime(2026, 8, 15, 12, 0, 0, tzinfo=dt.timezone.utc)
    return (base + dt.timedelta(hours=offset_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    live_cache_before = LIVE_CACHE.read_bytes() if LIVE_CACHE.exists() else None
    assert_(BIN.exists() and os.access(BIN, os.X_OK), f"binary exists and is executable: {BIN}")
    assert_(SCHEMA.exists(), f"pinned schema ships with the package: {SCHEMA}")

    with tempfile.TemporaryDirectory(prefix="kb-runtime-registry-") as tmp:
        sb = Sandbox(pathlib.Path(tmp))

        print("T1: --json lists every roster runtime with all eight fields + provenance")
        proc, doc = sb.run_json()
        assert_(proc.returncode == 0, f"rc=0 on --json (rc={proc.returncode}, stderr={proc.stderr[:200]!r})")
        assert_(doc.get("schema_version") == "kb-runtime-registry/v1", "schema_version pinned")
        rows = by_name(doc)
        assert_([r["name"] for r in doc["runtimes"]] == ROSTER_NAMES,
                f"roster order preserved, nothing omitted: {[r['name'] for r in doc['runtimes']]}")
        for name in ROSTER_NAMES:
            row = rows[name]
            missing = [f for f in FIELDS if f not in row]
            assert_(not missing, f"{name}: all eight fields present (missing={missing})")
            assert_(all(row[f] in ("yes", "no", "unknown") for f in FIELDS), f"{name}: fields are tri-state")
            for key in ("observed_at", "evidence", "blocked_until", "source", "age_seconds"):
                assert_(key in row["provenance"], f"{name}: provenance.{key} present")
        assert_(rows["opencode"]["fallback_of"] == "grok", "TSV 5th column fallback-of parsed")
        assert_(rows["claude"]["fallback_of"] is None, "no fallback_of where the column is absent")
        assert_(rows["codex"]["installed"] == "yes", "path-any candidate resolves → installed yes")
        assert_(rows["claude"]["installed"] == "yes", "which-any candidate resolves via PATH → installed yes")
        assert_(sb.calls() == [], "--json never probes (call log empty)")

        print("T2: unobserved runtime → unknown, never yes; available false")
        for name in ROSTER_NAMES:
            row = rows[name]
            for f in ("authenticated", "quota_available", "healthy"):
                assert_(row[f] == "unknown", f"{name}.{f} == unknown when unobserved (got {row[f]})")
            assert_(row["available"] is False, f"{name}.available is False when unobserved")
            assert_(row["provenance"]["source"] == "none", f"{name}: provenance.source == none")
        proc = sb.run()
        assert_(proc.returncode == 0 and "unknown" in proc.stdout, "--report renders unknown as text")
        assert_(all(n in proc.stdout for n in ROSTER_NAMES), "--report names every roster runtime")
        assert_(str(sb.cache) in proc.stdout, "--report footer names the cache path")

        print("T3: E6 fixture — codex quota-dead, 60-min cooldown elapsed, no later success (AC3/AC10)")
        e6 = {
            "providers": {
                "codex": {
                    "last_seen_at": iso(-2),
                    "last_category": "auth",
                    "last_stderr_snippet": "You've hit your usage limit. try again at Aug 20th, 2026 6:29 AM",
                    "blocked_until": iso(-1),
                    "last_success_at": iso(-27),
                    "last_session_id": "s-e6",
                },
                "claude": {"last_seen_at": iso(-0.5), "last_success_at": iso(-0.5), "last_session_id": "s-ok"},
            }
        }
        sb.state.write_text(json.dumps(e6, indent=2))
        state_bytes = sb.state.read_bytes()
        proc, doc = sb.run_json()
        rows = by_name(doc)
        codex = rows["codex"]
        assert_(codex["available"] is False, "codex NOT available despite elapsed cooldown (AC10)")
        assert_(codex["quota_available"] == "unknown", f"codex.quota_available == unknown, not yes (AC3) (got {codex['quota_available']})")
        assert_(codex["healthy"] == "no", "codex.healthy == no after a failed last observation")
        assert_(codex["authenticated"] == "no", "codex.authenticated == no for category auth (broker classification)")
        assert_(codex["provenance"]["source"] == "broker-state", "codex provenance from broker state")
        assert_(codex["provenance"]["blocked_until"] == iso(-1), "blocked_until carried through as provenance")
        assert_(codex["provenance"]["category"] == "auth", "failure category carried through")
        claude = rows["claude"]
        assert_(claude["available"] is True, "claude available on a fresh broker success")
        assert_(claude["healthy"] == claude["authenticated"] == claude["quota_available"] == "yes",
                "fresh success flips the three observed fields to yes")
        report = sb.run().stdout
        assert_(re.search(r"\b30m\b|\b0h\b|\b30 ?min", report) or "ago" in report, "report renders observation age")

        print("T3b: blocked_until in the future → quota_available no even with an old success")
        fut = json.loads(json.dumps(e6))
        fut["providers"]["codex"] = {"last_seen_at": iso(-0.2), "last_success_at": iso(-0.2), "blocked_until": iso(+5)}
        sb.state.write_text(json.dumps(fut))
        _, doc = sb.run_json()
        codex = by_name(doc)["codex"]
        assert_(codex["quota_available"] == "no" and codex["available"] is False,
                "future blocked_until → quota_available no, available false")
        sb.state.write_text(json.dumps(e6, indent=2))

        print("T13: broker success older than 24h → unknown (stale), available false, age rendered")
        stale = {"providers": {"codex": {"last_seen_at": iso(-30), "last_success_at": iso(-30)}}}
        sb.state.write_text(json.dumps(stale))
        _, doc = sb.run_json()
        codex = by_name(doc)["codex"]
        assert_(codex["healthy"] == "unknown" and codex["available"] is False, "stale success is unknown, not yes")
        assert_(codex["provenance"]["age_seconds"] == 30 * 3600, "age_seconds computed against --now")
        report = sb.run().stdout
        assert_(re.search(r"\b30h\b", report), "report renders the 30h age")
        sb.state.write_text(json.dumps(e6, indent=2))
        state_bytes = sb.state.read_bytes()

        print("T4: probe rc 0 + empty stdout → failure (AC4)")
        sb.set_mode("codex", "empty")
        proc, doc = sb.run_json("--probe", "codex")
        assert_(proc.returncode == 0, f"probe run exits 0 even when the probe fails (rc={proc.returncode} stderr={proc.stderr[:200]!r})")
        codex = by_name(doc)["codex"]
        assert_(any(l.startswith("codex ") for l in sb.calls()), "fake codex was actually invoked (mock won the resolver)")
        assert_(codex["healthy"] == "no" and codex["available"] is False, "empty-stdout probe → healthy no")
        assert_(codex["provenance"]["source"] == "probe", "probe observation is newest → provenance probe")
        assert_("empty stdout" in codex["provenance"]["evidence"], f"evidence names empty stdout: {codex['provenance']['evidence']}")
        res = {r["runtime"]: r for r in doc["probe"]["results"]}
        assert_(res["codex"]["outcome"] == "failure" and "empty stdout" in res["codex"]["reason"], "probe result recorded as failure/empty stdout")
        assert_(sb.cache.exists(), "cache written by --probe")
        cache_doc = json.loads(sb.cache.read_text())
        assert_(cache_doc["schema"] == "kb-runtime-registry-cache/v1", "cache schema pinned")
        assert_("CODEX_OK" not in sb.cache.read_text() and "prompt" not in json.dumps(cache_doc["probes"]["codex"]).lower(),
                "cache stores no stdout/prompt text")

        print("T12: token normalization — lowercase misses, non-zero rc fails, token inside noise succeeds")
        sb.set_mode("codex", "lower")
        _, doc = sb.run_json("--probe", "codex")
        assert_(by_name(doc)["codex"]["healthy"] == "no", "lowercase token is not the token (case-sensitive)")
        sb.set_mode("codex", "fail-with-token")
        _, doc = sb.run_json("--probe", "codex")
        res = {r["runtime"]: r for r in doc["probe"]["results"]}
        assert_(res["codex"]["outcome"] == "failure" and "exit 1" in res["codex"]["reason"],
                "token with rc 1 is a failure naming the exit code")
        sb.set_mode("codex", "token-extra")
        _, doc = sb.run_json("--probe", "codex")
        assert_(by_name(doc)["codex"]["healthy"] == "yes", "token embedded in extra text succeeds (substring after normalization)")

        print("T5: probe rc 0 + token → success flips healthy/authenticated/quota to yes (AC5)")
        sb.set_mode("codex", "token")
        calls_before = len(sb.calls())
        proc, doc = sb.run_json("--probe", "codex")
        codex = by_name(doc)["codex"]
        assert_(len(sb.calls()) == calls_before + 1, "exactly one probe invocation for --probe codex")
        assert_(codex["healthy"] == codex["authenticated"] == codex["quota_available"] == "yes", "three yes after a successful probe")
        assert_(codex["available"] is True, "available true after a successful probe")
        assert_(codex["provenance"]["source"] == "probe" and codex["provenance"]["observed_at"] == NOW,
                "provenance: probe at --now")
        assert_(not any(l.startswith("claude ") or l.startswith("agy ") for l in sb.calls()),
                "no other runtime was probed")
        codex_call = [l for l in sb.calls() if l.startswith("codex ")][-1]
        assert_("exec" in codex_call and "--skip-git-repo-check" in codex_call and "--sandbox read-only" in codex_call,
                f"codex probe argv carries the load-bearing flags: {codex_call}")
        assert_(sb.state.read_bytes() == state_bytes, "state.json byte-identical after probe (AC8)")

        print("T6: claude probe goes through $HUB/bin/kb-claude-run synchronously")
        _, doc = sb.run_json("--probe", "claude")
        calls = sb.calls()
        launcher = [l for l in calls if l.startswith("kb-claude-run ")]
        assert_(launcher, "sandbox bin/kb-claude-run was invoked for the claude probe")
        assert_(" -- " in launcher[-1] and " -p " in launcher[-1] and "--managed" not in launcher[-1],
                f"launcher argv: `--` separator, `-p`, no --managed: {launcher[-1]}")
        assert_(any(l.startswith("claude ") for l in calls), "fake claude ran under the launcher")
        assert_(by_name(doc)["claude"]["healthy"] == "yes", "claude probe success recorded")

        print("T6b: --probe with no names probes every roster runtime that has a probe; notebooklm stays unknown")
        sb.log.write_text("")
        _, doc = sb.run_json("--probe")
        probed = {l.split(" ", 1)[0] for l in sb.calls()}
        assert_({"claude", "codex", "agy", "grok", "opencode", "hermes"} <= probed, f"all probe-capable runtimes invoked: {probed}")
        assert_("notebooklm" not in probed, "notebooklm has no probe → not invoked")
        hermes_call = [l for l in sb.calls() if l.startswith("hermes ")][-1]
        assert_(" -z " in hermes_call and "--ignore-rules" in hermes_call and "--yolo" not in hermes_call,
                f"hermes probe is one-shot (-z) with --ignore-rules and no bypass flag: {hermes_call}")
        assert_(by_name(doc)["hermes"]["healthy"] == "yes" and by_name(doc)["hermes"]["edit_capable"] == "unknown",
                "hermes probe success flips health; unverified capabilities stay unknown")
        res = {r["runtime"]: r for r in doc["probe"]["results"]}
        assert_(res["notebooklm"]["outcome"] == "skipped" and "no probe defined" in res["notebooklm"]["reason"],
                "notebooklm result is skipped/no probe defined")
        assert_(by_name(doc)["notebooklm"]["healthy"] == "unknown", "notebooklm remains unknown")
        grok_call = [l for l in sb.calls() if l.startswith("grok ")][-1]
        assert_("--prompt-file" in grok_call and "--disable-web-search" in grok_call, f"grok probe uses prompt-file, no web: {grok_call}")
        agy_call = [l for l in sb.calls() if l.startswith("agy ")][-1]
        assert_("--add-dir" in agy_call and "--print" in agy_call, f"agy probe carries --add-dir/--print: {agy_call}")

        print("T7: nesting marker in the environment → --probe refuses (AC6)")
        sb.log.write_text("")
        cache_before = sb.cache.read_bytes()
        proc, doc = sb.run_json("--probe", "codex", extra_env={"CLAUDECODE": "1"})
        assert_(proc.returncode == 3, f"exit 3 on refused probe (rc={proc.returncode})")
        assert_(sb.calls() == [], "no probe ran under nesting")
        assert_(sb.cache.read_bytes() == cache_before, "cache untouched under nesting")
        assert_(doc["nested"]["detected"] is True and "CLAUDECODE" in doc["nested"]["markers"], "nesting reported with the marker")
        assert_(doc["probe"]["refused_reason"] and "CLAUDECODE" in doc["probe"]["refused_reason"],
                f"refused_reason names the marker: {doc['probe'].get('refused_reason')}")
        assert_("CLAUDECODE" in proc.stderr, "refusal reason printed to stderr")
        proc = sb.run(extra_env={"CLAUDE_CODE_ENTRYPOINT": "cli"})
        assert_(proc.returncode == 0, "--report is unaffected by nesting (prefix marker)")
        proc = sb.run("--probe", "codex", extra_env={"CLAUDE_CODE_ENTRYPOINT": "cli"})
        assert_(proc.returncode == 3 and sb.calls() == [], "prefix marker also refuses --probe")

        print("T8: cache deleted / malformed → --report still runs, unknown where no evidence (AC7)")
        sb.state.write_text(json.dumps({"providers": {}}))
        sb.cache.unlink()
        proc, doc = sb.run_json()
        assert_(proc.returncode == 0, "runs without a cache file")
        assert_(by_name(doc)["codex"]["healthy"] == "unknown", "codex back to unknown once the cache is gone")
        sb.cache.write_text("{not json")
        proc, doc = sb.run_json()
        assert_(proc.returncode == 0, "runs with a malformed cache")
        assert_("malformed" in proc.stderr.lower(), f"warns about the malformed cache: {proc.stderr[:200]!r}")
        assert_(by_name(doc)["codex"]["healthy"] == "unknown", "malformed cache contributes nothing")
        sb.cache.unlink()
        sb.state.write_text(json.dumps(e6, indent=2))

        print("T11: broker-state-only provider (no roster row) rendered with its own provenance")
        extra = json.loads(json.dumps(e6))
        extra["providers"]["zeta"] = {"last_seen_at": iso(-0.1), "last_success_at": iso(-0.1)}
        sb.state.write_text(json.dumps(extra))
        _, doc = sb.run_json()
        rows = by_name(doc)
        assert_("zeta" in rows, "zeta rendered although absent from the roster")
        assert_(rows["zeta"]["provenance"]["source"] == "broker-state-only", "provenance source broker-state-only")
        assert_(rows["zeta"]["installed"] == "unknown", "installed unknown without a roster row")
        assert_(rows["zeta"]["resumable"] == "unknown", "capability table has no row → unknown")
        assert_([r["name"] for r in doc["runtimes"]][:len(ROSTER_NAMES)] == ROSTER_NAMES, "roster rows come first, in roster order")
        proc = sb.run("--probe", "zeta")
        assert_(proc.returncode == 2 and "zeta" in proc.stderr and "codex" in proc.stderr,
                "--probe of a non-roster name is a usage error listing roster names")
        sb.state.write_text(json.dumps(e6, indent=2))

        print("T14: --probe with an unknown runtime name → exit 2 listing roster names")
        proc = sb.run("--probe", "nosuch")
        assert_(proc.returncode == 2 and "nosuch" in proc.stderr and "notebooklm" in proc.stderr, "exit 2 with roster names")

        print("T10: --json validates against the pinned schema; validator rejects a mutated document (AC9)")
        out = load_output_module()
        schema = json.loads(SCHEMA.read_text())
        _, doc = sb.run_json()
        assert_(out.validate(doc, schema) == [], "live --json document passes the validator")
        bad = json.loads(json.dumps(doc))
        bad["runtimes"][0]["installed"] = "maybe"
        assert_(out.validate(bad, schema) != [], "enum violation rejected (installed=maybe)")
        bad = json.loads(json.dumps(doc))
        del bad["runtimes"]
        assert_(out.validate(bad, schema) != [], "missing required key rejected")
        bad = json.loads(json.dumps(doc))
        bad["runtimes"][0]["extra_field"] = 1
        assert_(out.validate(bad, schema) != [], "unexpected key rejected (additionalProperties false)")
        bad = json.loads(json.dumps(doc))
        bad["runtimes"][0]["available"] = "yes"
        assert_(out.validate(bad, schema) != [], "available must be a boolean")

        print("T9: live hub untouched by the whole suite")
        live_cache_after = LIVE_CACHE.read_bytes() if LIVE_CACHE.exists() else None
        assert_(live_cache_after == live_cache_before, "live ~/knowledge/.orchestrator/runtime-registry.json unchanged/absent")
        assert_(not (HUB_LIVE / ".orchestrator" / "runtime-registry.json.tmp").exists(), "no stray temp file in the live hub")

    print("ALL runtime-registry fixtures passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
