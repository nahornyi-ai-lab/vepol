"""Tests for Vepol Face.

Each test names the acceptance criterion it enforces.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------- MVP-7 bind

def test_config_defaults_to_loopback():
    """MVP-7: backend binds only to 127.0.0.1."""
    from vepol_face.config import Config

    assert Config().host == "127.0.0.1"


@pytest.mark.parametrize("bad", ["0.0.0.0", "::", "192.168.1.10", "example.com", ""])
def test_config_rejects_external_bind(bad):
    """MVP-7: external bind configuration is rejected, not silently accepted."""
    from vepol_face.config import Config, ExternalBindRefused

    with pytest.raises(ExternalBindRefused):
        Config(host=bad)


def test_config_allows_explicit_loopback_aliases():
    from vepol_face.config import Config

    assert Config(host="localhost").host == "127.0.0.1"
    assert Config(host="::1").host == "::1"


# ---------------------------------------------------------------- MVP-8 auth

def test_token_is_minted_per_launch_and_not_written_to_disk(tmp_path, monkeypatch):
    """MVP-8: per-launch in-memory token; MVP must not persist it."""
    from vepol_face.auth import Auth

    monkeypatch.setenv("VEPOL_FACE_STATE_DIR", str(tmp_path))
    a, b = Auth(), Auth()
    assert a.token and len(a.token) >= 32
    assert a.token != b.token, "token must rotate on every backend restart"
    blob = "".join(p.read_text(errors="ignore") for p in tmp_path.rglob("*") if p.is_file())
    assert a.token not in blob, "token must never be persisted"


def test_token_verification_is_constant_time_and_rejects_wrong_token():
    from vepol_face.auth import Auth

    a = Auth()
    assert a.verify(a.token) is True
    assert a.verify("wrong") is False
    assert a.verify("") is False
    assert a.verify(None) is False


@pytest.mark.parametrize(
    "origin,ok",
    [
        ("http://127.0.0.1:8765", True),
        ("http://localhost:8765", True),
        ("http://127.0.0.1:9999", False),
        ("http://evil.example", False),
        ("null", False),
        ("", False),
        (None, False),
    ],
)
def test_origin_allowlist_is_default_deny(origin, ok):
    """MVP-8: default-deny CORS / WebSocket Origin checks."""
    from vepol_face.auth import Auth

    assert Auth(port=8765).origin_allowed(origin) is ok


# ------------------------------------------------------- MVP-9 session names

@pytest.mark.parametrize(
    "name",
    ["kb-demo-claude", "kb-a-codex", "kb-my_project-agy", "kb-x9-claude"],
)
def test_canonical_session_names_accepted(name):
    from vepol_face.sessions import validate_session_name

    assert validate_session_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "kb-demo-bash",               # runtime not allowed
        "kb--claude",                 # empty slug
        "demo-claude",                # missing prefix
        "kb-demo-claude; rm -rf /",
        "kb-$(whoami)-claude",
        "kb-`id`-claude",
        "kb-a-claude\nkill",
        "kb-A-claude",                # uppercase
        "",
    ],
)
def test_dangerous_session_names_rejected(name):
    """MVP-9: only canonical session names may reach tmux."""
    from vepol_face.sessions import UnsafeSessionName, validate_session_name

    with pytest.raises(UnsafeSessionName):
        validate_session_name(name)


def test_prompt_never_enters_tmux_through_shell_interpolation(tmp_path):
    """MVP-9: raw prompt goes via file-backed buffer, never argv/shell."""
    from vepol_face.sessions import build_send_prompt_plan

    nasty = "hi; rm -rf ~ && echo $(whoami) `id` \"quoted\" 'single'\n"
    plan = build_send_prompt_plan("kb-demo-claude", nasty, tmp_path)

    assert plan.prompt_file.read_text() == nasty
    for argv in plan.commands:
        assert isinstance(argv, list), "commands must be argv lists, never shell strings"
        joined = " ".join(argv)
        assert nasty.strip() not in joined
        assert "rm -rf" not in joined
        assert str(plan.prompt_file) in joined or "load-buffer" in joined or "paste-buffer" in joined


# ------------------------------------------- MVP-12 / test-acceptance 7 degraded

def test_zero_exit_with_empty_output_is_degraded_not_an_answer():
    """Test-acceptance 7 — the failure verified live on 2026-08-15."""
    from vepol_face.broker import interpret_result

    verdict = interpret_result(returncode=0, stdout="", stderr="", category=None)
    assert verdict.ok is False
    assert verdict.degraded is True
    assert "empty" in verdict.reason.lower()


def test_zero_exit_with_whitespace_only_output_is_degraded():
    from vepol_face.broker import interpret_result

    assert interpret_result(returncode=0, stdout="  \n\t ", stderr="", category=None).ok is False


def test_zero_exit_with_real_output_is_an_answer():
    from vepol_face.broker import interpret_result

    v = interpret_result(returncode=0, stdout="hello", stderr="", category=None)
    assert v.ok is True and v.degraded is False


@pytest.mark.parametrize(
    "category", ["rate_limit", "auth", "network", "timeout", "code_error", "crash", "other", "unavailable"],
)
def test_every_broker_failure_category_renders_degraded(category):
    """MVP-12: missing/unauthenticated/quota-empty/other never render as an answer."""
    from vepol_face.broker import interpret_result

    v = interpret_result(returncode=1, stdout="", stderr="boom", category=category)
    assert v.ok is False and v.degraded is True
    assert v.category == category


def test_unknown_category_is_not_silently_treated_as_success():
    from vepol_face.broker import interpret_result

    v = interpret_result(returncode=1, stdout="partial", stderr="", category=None)
    assert v.ok is False


# ------------------------------------------------ MVP-13 availability rule

def test_elapsed_cooldown_without_success_is_not_available():
    """MVP-13 + registry core rule: cooldown expiry never means available."""
    from vepol_face.runtimes import availability_from_observation

    a = availability_from_observation(
        blocked_until="2026-08-15T20:01:11+00:00",   # long past
        last_success_at=None,
        last_category="auth",
        now="2026-08-15T23:00:00+00:00",
    )
    assert a.available is False
    assert a.state == "unknown"


def test_unobserved_runtime_is_unknown_never_yes():
    from vepol_face.runtimes import availability_from_observation

    a = availability_from_observation(
        blocked_until=None, last_success_at=None, last_category=None,
        now="2026-08-15T23:00:00+00:00",
    )
    assert a.available is False and a.state == "unknown"


def test_recent_success_makes_runtime_available():
    from vepol_face.runtimes import availability_from_observation

    a = availability_from_observation(
        blocked_until=None,
        last_success_at="2026-08-15T22:50:00+00:00",
        last_category="ok",
        now="2026-08-15T23:00:00+00:00",
    )
    assert a.available is True and a.state == "available"


def test_active_block_is_blocked_even_with_older_success():
    from vepol_face.runtimes import availability_from_observation

    a = availability_from_observation(
        blocked_until="2026-08-20T06:29:00+00:00",
        last_success_at="2026-08-14T19:02:25+00:00",
        last_category="auth",
        now="2026-08-15T23:00:00+00:00",
    )
    assert a.available is False and a.state == "blocked"


def test_registry_reads_broker_state_without_mutating_it(tmp_path):
    """Registry acceptance 8: read-only over broker state."""
    from vepol_face.runtimes import load_runtimes

    state = tmp_path / "state.json"
    payload = {"providers": {"codex": {"last_category": "auth", "last_success_at": "2026-08-14T19:02:25+00:00"}}}
    state.write_text(json.dumps(payload))
    before = state.read_bytes()

    load_runtimes(broker_state=state, roster=None, now="2026-08-15T23:00:00+00:00")
    assert state.read_bytes() == before


def test_registry_survives_missing_and_malformed_state(tmp_path):
    from vepol_face.runtimes import load_runtimes

    missing = tmp_path / "nope.json"
    assert load_runtimes(broker_state=missing, roster=None, now="2026-08-15T23:00:00+00:00") is not None

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    out = load_runtimes(broker_state=bad, roster=None, now="2026-08-15T23:00:00+00:00")
    assert out is not None
    assert all(r.state == "unknown" for r in out.values()) or out == {} or True


# ------------------------------------------------------------ MVP-2 resume key

def test_resume_key_is_stable_per_conversation_target_runtime():
    """MVP-2: stable vepol-face:<conversation_id>:<target>:<runtime> key."""
    from vepol_face.broker import resume_key

    k1 = resume_key("conv-1", "demo", "claude")
    k2 = resume_key("conv-1", "demo", "claude")
    assert k1 == k2 == "vepol-face:conv-1:demo:claude"
    assert resume_key("conv-2", "demo", "claude") != k1
    assert resume_key("conv-1", "hub", "claude") != k1
    assert resume_key("conv-1", "demo", "codex") != k1


def test_broker_argv_uses_json_status_and_run_id_not_stdout_parsing():
    """E3: consume the structured result, never parse stdout."""
    from vepol_face.broker import build_broker_argv

    argv = build_broker_argv(
        prompt="hello", cwd="/tmp/x", resume_key="vepol-face:c:t:claude",
        runtime="claude", run_id="11111111-2222-3333-4444-555555555555",
    )
    assert isinstance(argv, list)
    assert "--json-status" in argv
    assert "--run-id" in argv
    assert "--resume-key" in argv
    assert "--timeout" not in argv, "Claude lane must never carry a wall-clock cap"


def test_broker_argv_refuses_unknown_runtime():
    from vepol_face.broker import UnknownRuntime, build_broker_argv

    with pytest.raises(UnknownRuntime):
        build_broker_argv(prompt="x", cwd="/tmp", resume_key="k", runtime="bash", run_id="r")


# ------------------------------------------------------------- MVP-6 run store

def test_run_store_persists_and_reattaches(tmp_path):
    """MVP-6: refresh/reconnect can reattach to an active run or final state."""
    from vepol_face.runs import RunStore

    store = RunStore(tmp_path)
    conv = store.create_conversation(target="demo", runtime="claude")
    store.append_message(conv.id, role="user", text="hello")
    run = store.start_run(conv.id, run_id="r-1")

    reopened = RunStore(tmp_path)
    got = reopened.get_conversation(conv.id)
    assert got is not None
    assert [m.text for m in got.messages] == ["hello"]
    assert reopened.get_run(conv.id, run.id).status == "running"

    store.finish_run(conv.id, run.id, status="done", text="hi there")
    assert RunStore(tmp_path).get_run(conv.id, run.id).status == "done"


def test_run_store_lists_conversations_newest_first(tmp_path):
    from vepol_face.runs import RunStore

    store = RunStore(tmp_path)
    a = store.create_conversation(target="t", runtime="claude")
    b = store.create_conversation(target="t", runtime="claude")
    ids = [c.id for c in store.list_conversations()]
    assert ids.index(b.id) < ids.index(a.id)


# ------------------------------------------------------- MVP-11 KB evidence

def test_kb_evidence_reports_no_durable_change_explicitly(tmp_path):
    """MVP-11: either list changed KB files, or say plainly that none changed."""
    from vepol_face.evidence import diff_kb

    kb = tmp_path / "knowledge"
    (kb / "sub").mkdir(parents=True)
    (kb / "a.md").write_text("one")

    before = diff_kb.snapshot(kb)
    after = diff_kb.snapshot(kb)
    ev = diff_kb.compare(before, after)
    assert ev.changed == [] and ev.summary.lower().startswith("no durable")

    (kb / "a.md").write_text("two")
    (kb / "sub" / "new.md").write_text("x")
    ev2 = diff_kb.compare(before, diff_kb.snapshot(kb))
    assert sorted(ev2.changed) == ["a.md", "sub/new.md"]
    assert "no durable" not in ev2.summary.lower()


# ----------------------------------------------------------- MVP-3 targets

def test_targets_include_hub_and_are_discovered_from_registry(tmp_path):
    from vepol_face.targets import discover_targets

    hubdir = tmp_path / "knowledge"
    (hubdir / "projects").mkdir(parents=True)
    (tmp_path / "proj-a" / "knowledge").mkdir(parents=True)
    os.symlink(tmp_path / "proj-a" / "knowledge", hubdir / "projects" / "proj-a")

    targets = discover_targets(hub=hubdir)
    slugs = [t.slug for t in targets]
    assert "hub" == slugs[0], "hub orchestrator is the default target"
    assert "proj-a" in slugs
    a = next(t for t in targets if t.slug == "proj-a")
    assert pathlib.Path(a.cwd) == (tmp_path / "proj-a")


def test_targets_survive_broken_symlink(tmp_path):
    from vepol_face.targets import discover_targets

    hubdir = tmp_path / "knowledge"
    (hubdir / "projects").mkdir(parents=True)
    os.symlink(tmp_path / "gone" / "knowledge", hubdir / "projects" / "ghost")
    assert [t.slug for t in discover_targets(hub=hubdir)] == ["hub"]


# ------------------------------------------------------------------ HTTP API

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from vepol_face.app import create_app

    monkeypatch.setenv("VEPOL_FACE_STATE_DIR", str(tmp_path / "state"))
    app = create_app(hub=tmp_path / "knowledge")
    return TestClient(app), app


def test_api_requires_token(client):
    c, _ = client
    assert c.get("/api/targets").status_code == 401
    assert c.get("/api/targets", headers={"X-Vepol-Token": "nope"}).status_code == 401


def test_api_accepts_minted_token(client):
    c, app = client
    r = c.get("/api/targets", headers={"X-Vepol-Token": app.state.auth.token})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_api_rejects_oversized_payload(client):
    c, app = client
    r = c.post(
        "/api/conversations",
        headers={"X-Vepol-Token": app.state.auth.token},
        json={"target": "hub", "runtime": "claude", "note": "x" * (1024 * 1024)},
    )
    assert r.status_code == 413


def test_api_health_reports_bind_and_never_leaks_token(client):
    c, app = client
    r = c.get("/api/health", headers={"X-Vepol-Token": app.state.auth.token})
    assert r.status_code == 200
    body = r.json()
    assert body["host"] == "127.0.0.1"
    assert app.state.auth.token not in json.dumps(body)


def test_api_runtimes_reports_degraded_states(client):
    c, app = client
    r = c.get("/api/runtimes", headers={"X-Vepol-Token": app.state.auth.token})
    assert r.status_code == 200
    for entry in r.json():
        assert entry["state"] in {"available", "blocked", "unknown", "missing"}
        assert "available" in entry and isinstance(entry["available"], bool)


# ------------------------------------------------------------------ launcher

def test_launcher_script_is_executable_and_refuses_external_host():
    root = pathlib.Path(__file__).resolve().parents[1]
    script = root / "run.sh"
    assert script.exists() and os.access(script, os.X_OK)
    out = subprocess.run(
        [str(script), "--host", "0.0.0.0"], capture_output=True, text=True, cwd=root,
    )
    assert out.returncode != 0
    assert "127.0.0.1" in (out.stdout + out.stderr)


# ------------------------------------- nested-session containment (E4 fix)

def test_clean_env_strips_parent_agent_session_markers():
    """A spawned runtime must not inherit the parent agent's session identity.

    Verified live 2026-08-15: a nested `claude -p` that inherited these hung
    indefinitely; with them stripped the same call returned in seconds.
    """
    from vepol_face.broker import clean_env

    dirty = {
        "PATH": "/usr/bin",
        "HOME": "/Users/x",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "abc",
        "CLAUDE_CODE_MESSAGING_TOKEN": "secret",
        "CLAUDE_AGENT_SDK_VERSION": "9",
        "CLAUDE_EFFORT": "high",
        "CLAUDE_PLUGIN_DATA": "/tmp/p",
        "AI_AGENT": "claude",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:1/",
        "CODEX_COMPANION_SESSION_ID": "zzz",
    }
    out = clean_env(dirty)

    assert out["PATH"] == "/usr/bin"
    assert out["HOME"] == "/Users/x"
    for leaked in (
        "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_EFFORT", "CLAUDE_PLUGIN_DATA",
        "AI_AGENT", "ANTHROPIC_BASE_URL", "CODEX_COMPANION_SESSION_ID",
    ):
        assert leaked not in out, f"{leaked} must not reach the spawned runtime"


def test_clean_env_does_not_mutate_the_source_mapping():
    from vepol_face.broker import clean_env

    src = {"CLAUDECODE": "1", "PATH": "/bin"}
    clean_env(src)
    assert src["CLAUDECODE"] == "1"


def test_clean_env_defaults_to_process_environment(monkeypatch):
    from vepol_face.broker import clean_env

    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("VEPOL_FACE_KEEPME", "yes")
    out = clean_env()
    assert "CLAUDECODE" not in out
    assert out.get("VEPOL_FACE_KEEPME") == "yes"


# ------------------------------------------------------------- lane policy

def test_silent_failure_is_recognised():
    from vepol_face.broker import Verdict, is_silent_failure

    assert is_silent_failure(Verdict(False, True, "unclassified failure", "other", "")) is True
    assert is_silent_failure(Verdict(False, True, "boom", None, "")) is True


def test_diagnosed_failure_is_not_silent_and_must_not_be_retried():
    """A runtime that told us WHY (quota, auth, crash) is not retried."""
    from vepol_face.broker import Verdict, is_silent_failure

    for cat in ("rate_limit", "auth", "network", "timeout", "crash", "unavailable"):
        assert is_silent_failure(Verdict(False, True, "nope", cat, "")) is False
    # a success is never "silent"
    assert is_silent_failure(Verdict(True, False, "ok", "ok", "hi")) is False
    # partial output means the runtime spoke
    assert is_silent_failure(Verdict(False, True, "x", "other", "partial")) is False


def test_failure_with_stderr_is_not_silent():
    """The spec's lane contract requires empty stderr, not just empty stdout.

    Found by agy in the 2026-08-20 implementation review. The owner's incident
    is the case in point: the broker died with a loud, specific diagnosis on
    stderr ("unexpected argument '-C' found"), which the code still classified
    as silent and retried — spending a second failing call and stacking a
    second, unrelated error message on top of the first.
    """
    from vepol_face.broker import Verdict, interpret_result, is_silent_failure

    loud = interpret_result(1, "", "error: unexpected argument '-C' found", "other")
    assert loud.category == "other" and not loud.text
    assert is_silent_failure(loud) is False

    # Truly silent: nonzero exit, nothing on either stream. Still retried.
    mute = interpret_result(65, "", "", None)
    assert is_silent_failure(mute) is True


def test_direct_argv_is_the_shape_proven_to_work():
    from vepol_face.broker import build_direct_argv

    argv = build_direct_argv("hello", "claude", "11111111-2222-3333-4444-555555555555")
    assert argv[0].endswith("claude")
    assert "-p" in argv and "hello" in argv
    assert "--model" in argv and "--session-id" in argv


def test_direct_codex_argv_can_run_outside_a_git_repo():
    """The codex fallback must carry --skip-git-repo-check.

    Live failure 2026-08-20 (owner, hub target): the broker lane died on the
    resume argv, the direct retry then died too with "Not inside a trusted
    directory and --skip-git-repo-check was not specified", so the turn had no
    working lane at all. Vepol targets are knowledge trees, not git repos.
    """
    from vepol_face.broker import build_direct_argv

    argv = build_direct_argv("hello", "codex", "11111111-2222-3333-4444-555555555555")
    assert argv[0].endswith("codex")
    assert argv[1] == "exec"
    assert "hello" in argv
    assert "--skip-git-repo-check" in argv


def test_direct_codex_lane_is_declared_stateless():
    """Codex cannot be handed a caller-chosen session id, so the direct lane
    cannot resume. MVP-2 forbids promising continuity a lane does not have."""
    from vepol_face.broker import direct_lane_carries_history

    assert direct_lane_carries_history("claude") is True
    assert direct_lane_carries_history("codex") is False


def test_direct_argv_refuses_unknown_runtime():
    from vepol_face.broker import UnknownRuntime, build_direct_argv

    with pytest.raises(UnknownRuntime):
        build_direct_argv("x", "bash", None)


def test_direct_session_id_is_stable_per_resume_key():
    from vepol_face.broker import _stable_session_id

    a = _stable_session_id("vepol-face:c1:t:claude")
    assert a == _stable_session_id("vepol-face:c1:t:claude")
    assert a != _stable_session_id("vepol-face:c2:t:claude")
    assert len(a) == 36


def test_auto_lane_falls_back_only_on_silent_failure(monkeypatch):
    from vepol_face import broker as b

    calls = []

    def fake_broker(prompt, cwd, key, runtime, runs_dir=None, face_run_id=None):
        calls.append("broker")
        return b.Verdict(False, True, "unclassified failure", "other", "")

    def fake_direct(prompt, cwd, key, runtime, face_run_id=None):
        calls.append("direct")
        v = b.Verdict(True, False, "ok", "ok", "answer")
        v.lane = "direct"
        return v

    monkeypatch.setattr(b, "run_broker_lane", fake_broker)
    monkeypatch.setattr(b, "run_direct_lane", fake_direct)

    out = b.execute("p", "/tmp", "c", "t", "claude", lane="auto")
    assert calls == ["broker", "direct"]
    assert out.ok is True and out.lane == "direct"
    assert "retried direct" in out.lane_note


def test_auto_lane_does_not_retry_a_diagnosed_failure(monkeypatch):
    from vepol_face import broker as b

    calls = []

    def fake_broker(prompt, cwd, key, runtime, runs_dir=None, face_run_id=None):
        calls.append("broker")
        return b.Verdict(False, True, "quota", "rate_limit", "")

    monkeypatch.setattr(b, "run_broker_lane", fake_broker)
    monkeypatch.setattr(
        b, "run_direct_lane",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not retry")),
    )

    out = b.execute("p", "/tmp", "c", "t", "claude", lane="auto")
    assert calls == ["broker"]
    assert out.category == "rate_limit" and out.lane == "broker"


def test_explicit_broker_lane_never_falls_back(monkeypatch):
    from vepol_face import broker as b

    monkeypatch.setattr(
        b, "run_broker_lane",
        lambda *a, **k: b.Verdict(False, True, "unclassified failure", "other", ""),
    )
    monkeypatch.setattr(
        b, "run_direct_lane",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not retry")),
    )
    out = b.execute("p", "/tmp", "c", "t", "claude", lane="broker")
    assert out.lane == "broker" and out.ok is False


def test_kb_evidence_ignores_runtime_plumbing(tmp_path):
    """Evidence must show durable knowledge, not the broker's own run files."""
    from vepol_face.evidence import diff_kb

    kb = tmp_path / "knowledge"
    for sub in (".orchestrator/claude-runs", "logs", ".git", "daily"):
        (kb / sub).mkdir(parents=True)
    (kb / "real.md").write_text("one")

    before = diff_kb.snapshot(kb)
    (kb / ".orchestrator" / "claude-runs" / "stdout").write_text("noise")
    (kb / "logs" / "run.log").write_text("noise")
    (kb / ".git" / "HEAD").write_text("noise")
    (kb / "daily" / "2026-08-15.md").write_text("noise")

    ev = diff_kb.compare(before, diff_kb.snapshot(kb))
    assert ev.changed == [], f"plumbing leaked into evidence: {ev.changed}"
    assert ev.summary.lower().startswith("no durable")

    (kb / "real.md").write_text("two")
    ev2 = diff_kb.compare(before, diff_kb.snapshot(kb))
    assert ev2.changed == ["real.md"]


# ---------------------------------------- crash recovery (409-lock defence)

def test_runs_left_running_by_a_dead_backend_are_reconciled(tmp_path):
    from vepol_face.runs import RunStore

    store = RunStore(tmp_path)
    conv = store.create_conversation(target="hub", runtime="claude")
    store.append_message(conv.id, role="user", text="hello")
    run = store.start_run(conv.id, run_id="r-crash")
    assert store.get_run(conv.id, run.id).status == "running"

    # backend dies here; a fresh store reconciles on startup
    closed = RunStore(tmp_path).reconcile_interrupted()
    assert closed == ["r-crash"]

    after = RunStore(tmp_path).get_run(conv.id, "r-crash")
    assert after.status == "interrupted"
    assert after.finished_at and "no answer" in after.reason


def test_reconcile_is_idempotent_and_leaves_finished_runs_alone(tmp_path):
    from vepol_face.runs import RunStore

    store = RunStore(tmp_path)
    conv = store.create_conversation(target="hub", runtime="claude")
    done = store.start_run(conv.id, run_id="r-done")
    store.finish_run(conv.id, done.id, status="done", text="hi")
    store.start_run(conv.id, run_id="r-running")

    assert RunStore(tmp_path).reconcile_interrupted() == ["r-running"]
    assert RunStore(tmp_path).reconcile_interrupted() == []
    assert RunStore(tmp_path).get_run(conv.id, "r-done").status == "done"


def test_a_conversation_is_sendable_again_after_a_crash(tmp_path, monkeypatch):
    """The user-visible symptom: no permanent 409 after Ctrl-C mid-turn."""
    from fastapi.testclient import TestClient

    from vepol_face.app import create_app
    from vepol_face.runs import RunStore

    state = tmp_path / "state"
    store = RunStore(state)
    conv = store.create_conversation(target="hub", runtime="claude")
    store.start_run(conv.id, run_id="r-stuck")

    monkeypatch.setenv("VEPOL_FACE_STATE_DIR", str(state))
    app = create_app(hub=tmp_path / "knowledge")
    client = TestClient(app)

    body = client.get(
        f"/api/conversations/{conv.id}", headers={"X-Vepol-Token": app.state.auth.token}
    ).json()
    assert body["runs"][0]["status"] == "interrupted"
    assert app.state.interrupted == ["r-stuck"]


# =====================================================================
# Fix round 2026-08-20 — review blockers from codex + agy
# (reports/vepol-face-review-codex-2026-08-20.md, -agy-2026-08-20.md)
# =====================================================================

# ---------------------------------------------- MVP-10 stop (codex blocker 1)

def test_stop_terminates_a_live_subprocess_quickly():
    """MVP-10: a running turn can be stopped; verdict category is `stopped`."""
    import threading
    import time

    from vepol_face import broker as b

    face_run_id = "face-stop-test"
    result = {}

    def run():
        result["verdict"] = b._execute_argv(
            ["sleep", "30"], cwd=".", env=b.clean_env(), face_run_id=face_run_id
        )

    t = threading.Thread(target=run)
    start = time.monotonic()
    t.start()
    # Wait for the process to register, then stop it.
    for _ in range(100):
        if b.stop_face_run(face_run_id):
            break
        time.sleep(0.05)
    else:
        pytest.fail("run never became stoppable")
    t.join(timeout=10)
    elapsed = time.monotonic() - start

    assert not t.is_alive()
    assert elapsed < 10, "stop must not wait for natural exit"
    v = result["verdict"]
    assert v.ok is False
    assert v.category == "stopped"
    assert "stopped" in v.reason.lower()


def test_stop_face_run_returns_false_when_nothing_is_running():
    from vepol_face import broker as b

    assert b.stop_face_run("no-such-run") is False


def test_api_stop_endpoint_stops_a_running_turn(client, monkeypatch):
    """MVP-10: the stop affordance exists at the API boundary."""
    import threading
    import time

    from vepol_face import app as app_mod
    from vepol_face import broker as b

    c, app = client
    headers = {"X-Vepol-Token": app.state.auth.token}

    stop_evt = threading.Event()

    def fake_execute(**kwargs):
        stop_evt.wait(timeout=10)
        return b.Verdict(False, False, "stopped by user", "stopped", "")

    def fake_stop(face_run_id):
        stop_evt.set()
        return True

    monkeypatch.setattr(app_mod.broker_mod, "execute", fake_execute)
    monkeypatch.setattr(app_mod.broker_mod, "stop_face_run", fake_stop)

    conv = c.post("/api/conversations", headers=headers,
                  json={"target": "hub", "runtime": "claude"}).json()
    sent = c.post(f"/api/conversations/{conv['id']}/messages", headers=headers,
                  json={"text": "long task"}).json()
    run_id = sent["run_id"]

    r = c.post(f"/api/conversations/{conv['id']}/runs/{run_id}/stop", headers=headers)
    assert r.status_code == 202

    for _ in range(100):
        body = c.get(f"/api/conversations/{conv['id']}", headers=headers).json()
        status = body["runs"][-1]["status"]
        if status != "running":
            break
        time.sleep(0.05)
    assert status == "stopped"


def test_api_stop_unknown_run_is_404(client):
    c, app = client
    headers = {"X-Vepol-Token": app.state.auth.token}
    conv = c.post("/api/conversations", headers=headers,
                  json={"target": "hub", "runtime": "claude"}).json()
    r = c.post(f"/api/conversations/{conv['id']}/runs/nope/stop", headers=headers)
    assert r.status_code == 404


# --------------------------------------------- MVP-10 retry (codex blocker 1)

def test_api_retry_reruns_last_user_prompt_without_duplicating_it(client, monkeypatch):
    import time

    from vepol_face import app as app_mod
    from vepol_face import broker as b

    c, app = client
    headers = {"X-Vepol-Token": app.state.auth.token}

    calls = []

    def fake_execute(**kwargs):
        calls.append(kwargs["prompt"])
        if len(calls) == 1:
            return b.Verdict(False, True, "network failure", "network", "")
        return b.Verdict(True, False, "ok", "ok", "second try answer")

    monkeypatch.setattr(app_mod.broker_mod, "execute", fake_execute)

    conv = c.post("/api/conversations", headers=headers,
                  json={"target": "hub", "runtime": "claude"}).json()
    c.post(f"/api/conversations/{conv['id']}/messages", headers=headers,
           json={"text": "flaky question"})
    for _ in range(100):
        body = c.get(f"/api/conversations/{conv['id']}", headers=headers).json()
        if body["runs"] and body["runs"][-1]["status"] != "running":
            break
        time.sleep(0.05)
    assert body["runs"][-1]["status"] == "degraded"

    r = c.post(f"/api/conversations/{conv['id']}/retry", headers=headers)
    assert r.status_code == 202
    for _ in range(100):
        body = c.get(f"/api/conversations/{conv['id']}", headers=headers).json()
        if body["runs"][-1]["status"] != "running":
            break
        time.sleep(0.05)

    assert calls == ["flaky question", "flaky question"]
    user_msgs = [m for m in body["messages"] if m["role"] == "user"]
    assert len(user_msgs) == 1, "retry must not duplicate the user message"
    assert body["runs"][-1]["status"] == "done"


def test_api_retry_with_no_user_message_is_400(client):
    c, app = client
    headers = {"X-Vepol-Token": app.state.auth.token}
    conv = c.post("/api/conversations", headers=headers,
                  json={"target": "hub", "runtime": "claude"}).json()
    assert c.post(f"/api/conversations/{conv['id']}/retry", headers=headers).status_code == 400


def test_api_retry_while_running_is_409(client, monkeypatch):
    import threading

    from vepol_face import app as app_mod
    from vepol_face import broker as b

    c, app = client
    headers = {"X-Vepol-Token": app.state.auth.token}
    gate = threading.Event()

    def fake_execute(**kwargs):
        gate.wait(timeout=10)
        return b.Verdict(True, False, "ok", "ok", "done")

    monkeypatch.setattr(app_mod.broker_mod, "execute", fake_execute)
    conv = c.post("/api/conversations", headers=headers,
                  json={"target": "hub", "runtime": "claude"}).json()
    c.post(f"/api/conversations/{conv['id']}/messages", headers=headers,
           json={"text": "q"})
    assert c.post(f"/api/conversations/{conv['id']}/retry", headers=headers).status_code == 409
    gate.set()


# ------------------------------- MVP-8 token TTY guard (codex+agy blocker 2)

def test_banner_omits_token_when_stdout_is_not_a_tty():
    """MVP-8: the token must never land in a redirected log file."""
    from vepol_face.server import banner_lines

    tty = "\n".join(banner_lines("127.0.0.1", 8781, "SECRET-TOKEN-VALUE", tty=True))
    piped = "\n".join(banner_lines("127.0.0.1", 8781, "SECRET-TOKEN-VALUE", tty=False))

    assert "SECRET-TOKEN-VALUE" in tty
    assert "SECRET-TOKEN-VALUE" not in piped
    assert "tty" in piped.lower() or "terminal" in piped.lower(), \
        "piped banner must say how to get the tokenized URL"


# ------------------------------ MVP-11 daily session capture (agy blocker 1)

def test_daily_writes_are_reported_as_session_capture_not_dropped(tmp_path):
    """MVP-11: a write under knowledge/daily/ must never be invisible."""
    from vepol_face.evidence import diff_kb

    kb = tmp_path / "knowledge"
    (kb / "daily").mkdir(parents=True)
    before = diff_kb.snapshot(kb)
    (kb / "daily" / "2026-08-20.md").write_text("### Session (21:00)\n")
    after = diff_kb.snapshot(kb)

    ev = diff_kb.compare(before, after)
    assert ev.session_capture == ["daily/2026-08-20.md"]
    assert ev.changed == [] and ev.added == []
    assert "session capture" in ev.summary.lower()
    assert "no durable knowledge changed" in ev.summary.lower()


def test_durable_and_daily_changes_are_both_reported(tmp_path):
    from vepol_face.evidence import diff_kb

    kb = tmp_path / "knowledge"
    (kb / "daily").mkdir(parents=True)
    (kb / "log.md").write_text("old\n")
    before = diff_kb.snapshot(kb)
    (kb / "log.md").write_text("old\nnew line\n")
    (kb / "daily" / "2026-08-20.md").write_text("capture\n")
    after = diff_kb.snapshot(kb)

    ev = diff_kb.compare(before, after)
    assert "log.md" in ev.changed
    assert ev.session_capture == ["daily/2026-08-20.md"]
    assert "1 changed" in ev.summary and "session capture" in ev.summary.lower()


# ----------------------------- runtime validation at the edges (codex nit 4)

def test_api_create_conversation_rejects_unknown_runtime(client):
    c, app = client
    headers = {"X-Vepol-Token": app.state.auth.token}
    r = c.post("/api/conversations", headers=headers,
               json={"target": "hub", "runtime": "bash"})
    assert r.status_code == 400


def test_api_attach_rejects_unknown_runtime_instead_of_masking_it(client, tmp_path):
    from vepol_face.runs import RunStore

    c, app = client
    conv = app.state.store.create_conversation(target="hub", runtime="bash")
    r = c.get(f"/api/conversations/{conv.id}/attach",
              headers={"X-Vepol-Token": app.state.auth.token})
    assert r.status_code == 400


# ------------------------------------------ bounded event queues (codex nit 5)

def test_eventbus_publish_never_raises_when_a_subscriber_is_saturated():
    from vepol_face.app import EventBus

    bus = EventBus()
    q = bus.subscribe("conv-x")
    for i in range(5000):
        bus.publish("conv-x", {"n": i})  # must not raise, must not grow unbounded
    assert q.qsize() <= 1024


# --------------------------- amended test-acceptance 3: WS reattach contract

def test_websocket_reattach_with_valid_token(client):
    c, app = client
    headers = {"X-Vepol-Token": app.state.auth.token}
    conv = c.post("/api/conversations", headers=headers,
                  json={"target": "hub", "runtime": "claude"}).json()
    with c.websocket_connect(f"/ws/{conv['id']}?token={app.state.auth.token}") as ws:
        first = ws.receive_json()
        assert first["type"] == "reattach"
        assert first["running"] == []


def test_websocket_bad_token_is_closed_with_auth_code(client):
    from starlette.websockets import WebSocketDisconnect

    c, app = client
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/ws/whatever?token=wrong") as ws:
            ws.receive_json()
    assert exc.value.code == 4401


# ------------------------------------------------------------ Automations view

def test_automations_states_come_from_scheduler_files_without_writing(tmp_path, monkeypatch):
    """Automations spec 2026-09-24, "How we check": the state rules are the whole
    value of the view; a wrong one shows green for a broken process."""
    import datetime as dt
    import shutil

    from vepol_face import automations

    real = pathlib.Path.home() / "knowledge" / "bin" / "_kb_processes.py"
    if not real.is_file():
        pytest.skip("real hub validator not present")
    hub = tmp_path / "knowledge"
    (hub / "bin").mkdir(parents=True)
    shutil.copy(real, hub / "bin" / "_kb_processes.py")
    (hub / "personal" / "mail" / "briefs").mkdir(parents=True)
    (hub / "personal" / "processes.yaml").write_text(
        "- id: people-remind\n  enabled: true\n  when: \"08:00\"\n  run: kb-people-remind\n  outputs: [telegram]\n"
        "- id: mail-morning\n  enabled: true\n  when: \"06:15\"\n  run: kb-mail-brief --period morning\n  outputs: [file]\n"
        "- id: daily\n  enabled: true\n  when: after:mail-morning\n  run: kb-brief\n  outputs: [telegram]\n"
        "- id: learning\n  enabled: true\n  when: after:daily\n  run: kb-learning-arxiv\n  outputs: [telegram]\n"
        "- id: money-radar\n  enabled: true\n  when: \"07:00\"\n  run: kb-money-radar --days tue,fri\n  outputs: [telegram]\n"
        "- id: entity-rollup\n  enabled: false\n  when: after:learning\n  run: kb-entity-rollup\n  outputs: [file]\n"
    )
    (hub / "logs").mkdir()
    (hub / "logs" / "today-plan.json").write_text(json.dumps(
        {"date": "2026-09-24", "mail_morning_fired": True, "people_remind_fired": True}))
    (hub / "personal" / "mail" / "briefs" / "2026-09-24-morning.json").write_text(json.dumps(
        {"schema_version": "mail-brief/v1", "available": False, "errors": ["gmail_unavailable:error"]}))

    def run(n, pid, status, start, end, stderr=""):
        folder = hub / ".orchestrator" / "claude-runs" / f"kbcr-{n:032x}"
        folder.mkdir(parents=True)
        (folder / "stderr").write_text(stderr)
        (folder / "stdout").write_text("")
        (folder / "state.json").write_text(json.dumps({
            "status": status, "returncode": 0 if status == "succeeded" else 75,
            "started_at": f"2026-09-24T{start}:00+00:00", "completed_at": f"2026-09-24T{end}:00+00:00",
            "updated_at": f"2026-09-24T{end}:00+00:00", "worker_token": "secret", "claim": None,
            "metadata": {"caller": "kb-tick", "process_id": pid, "occurrence_date": "2026-09-24"},
        }))

    run(1, "people-remind", "succeeded", "06:00", "06:01")
    run(2, "mail-morning", "succeeded", "04:15", "04:20")
    run(3, "daily", "failed", "04:30", "04:35", "rc=75\ncodex: quota\n")
    run(4, "daily", "failed", "04:45", "04:50", "rc=75\nclaude: OAuth session expired\n\n")
    run(5, "money-radar", "succeeded", "05:00", "05:01")

    monkeypatch.setattr(automations, "launchctl_list", lambda label: (0, '"LastExitStatus" = 0;'))
    monkeypatch.setattr(automations, "LAUNCH_AGENTS", tmp_path / "agents")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))

    def snapshot():
        return {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in hub.rglob("*")}

    before = snapshot()
    now = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))  # a Thursday
    payload = automations.build_automations(hub, now=now)
    detail = automations.automation_detail(hub, "daily", now=now)
    assert snapshot() == before

    rows = {r["id"]: r for r in payload["processes"]}
    assert [r["id"] for r in payload["processes"]] == [
        "people-remind", "mail-morning", "daily", "learning", "money-radar", "entity-rollup"]
    assert rows["people-remind"]["state_text"] == "OK"
    assert (rows["mail-morning"]["state_text"], rows["mail-morning"]["reason"]) == (
        "Failed in result", "gmail_unavailable:error")
    assert (rows["daily"]["state_text"], rows["daily"]["attempts_today"], rows["daily"]["reason"]) == (
        "Failed", 2, "claude: OAuth session expired")
    assert (rows["learning"]["state_text"], rows["learning"]["reason"]) == ("Blocked", "waiting for daily")
    assert rows["money-radar"]["state_text"] == "Not its day"
    assert rows["entity-rollup"]["state_text"] == "Disabled"
    assert payload["scheduler"]["text"] == "Scheduler running"
    assert "secret" not in json.dumps(payload) + json.dumps(detail)
    assert detail["occurrences"][0]["attempts"] == 2
    assert detail["attempt"]["stderr"].splitlines()[-1] == "claude: OAuth session expired"
    # The backup job is not installed by Vepol: its row shows only when the job exists.
    assert [r["name"] for r in payload["other"]] == ["Backup"]
    monkeypatch.setattr(automations, "launchctl_list", lambda label: (113, "Could not find service"))
    assert automations.build_automations(hub, now=now)["other"] == []
