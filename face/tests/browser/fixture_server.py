"""Serve the real Face app against owned, isolated state; never start a runtime."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import tempfile

app_root, fixture_root = map(pathlib.Path, sys.argv[1:3])
sys.path.insert(0, str(app_root))

# Own tmux server in a short socket dir (macOS caps socket paths at 104 bytes);
# without TMUX/TMUX_PANE no tmux call can reach a caller's server.
os.environ["TMUX_TMPDIR"] = tempfile.mkdtemp(prefix="vt-", dir="/tmp")
os.environ.pop("TMUX", None)
os.environ.pop("TMUX_PANE", None)

import uvicorn
from vepol_face import terminal_session
from vepol_face.app import create_app
from vepol_face.config import Config

# The in-app terminal runs cat instead of an agent; tmux stays real. A wrapper
# drops the runtime flags (--permission-mode, --sandbox, ...) that cat rejects.
standin = fixture_root / "bin" / "runtime-standin"
standin.parent.mkdir(parents=True, exist_ok=True)
standin.write_text("#!/bin/sh\nexec /bin/cat\n", encoding="utf-8")
standin.chmod(0o755)
_real_binary = terminal_session.TerminalSession._binary


def _fixture_binary(self, runtime: str) -> str:
    return str(standin) if runtime in ("claude", "codex", "agy") else _real_binary(self, runtime)


terminal_session.TerminalSession._binary = _fixture_binary

hub = fixture_root / "hub"
for slug in ("alpha", "beta", "gamma", "delta"):
    (hub / "projects" / slug).mkdir(parents=True, exist_ok=True)

# kb-board, _kb_processes.py and the backlog template (read-only): VEPOL_FIXTURE_KB_ROOT if set,
# else the Vepol repo this app sits in (so a release tests its own tools), else ~/knowledge.
_repo = app_root.resolve().parent
if os.environ.get("VEPOL_FIXTURE_KB_ROOT"):
    REAL_HUB = pathlib.Path(os.environ["VEPOL_FIXTURE_KB_ROOT"]).expanduser()
elif (_repo / "bin" / "kb-board").is_file() and (_repo / "_template" / "knowledge" / "backlog.md").is_file():
    REAL_HUB = _repo
else:
    REAL_HUB = pathlib.Path.home() / "knowledge"


def kb_board(*args: str) -> str:
    return subprocess.run([str(hub / "bin" / "kb-board"), *args],
                          capture_output=True, text=True, check=True).stdout


def fill_board(slug: str, tasks: list[tuple[str, str, str, str]]) -> None:
    """tasks: (plan_item_id, title, final status, claim actor) via the real kb-board only."""
    board = hub / "projects" / slug / "backlog.md"
    template = (REAL_HUB / "_template" / "knowledge" / "backlog.md").read_text(encoding="utf-8")
    board.write_text(template.replace("{{PROJECT_NAME}}", slug), encoding="utf-8")
    path = str(board)
    for item_id, title, status, actor in tasks:
        start = "Backlog" if status == "Backlog" else "Ready"
        kb_board("append", path, title, "--plan-item-id", item_id, "--status", start, "--actor", "fixture")
        if status in ("In Progress", "Review", "Done"):
            kb_board("claim", path, "--plan-item-id", item_id, "--actor", actor)
            claim_id = next(r["claim_id"] for r in json.loads(kb_board("list", path, "--all", "--json"))
                            if r["plan_item_id"] == item_id)
            if status in ("Review", "Done"):
                kb_board("request-review", path, "--plan-item-id", item_id, "--claim-id", claim_id, "--actor", actor)
            if status == "Done":
                kb_board("close", path, "--plan-item-id", item_id, "--claim-id", claim_id,
                         "--actor", actor, "--outcome", "closed")


expected = None
if os.environ.get("VEPOL_FIXTURE_TASKS") == "1":
    (hub / "bin").mkdir(parents=True, exist_ok=True)
    (hub / "bin" / "kb-board").symlink_to(REAL_HUB / "bin" / "kb-board")
    fill_board("alpha", [
        ("alpha-1", "Wire the export button", "In Progress", "codex"),
        ("alpha-2", "Write the release notes", "Ready", ""),
        ("alpha-3", "Review the install script", "Review", "claude"),
        ("alpha-4", "Someday: dark theme polish", "Backlog", ""),
        ("alpha-5", "Fix the login redirect", "Done", "claude"),
    ])
    fill_board("beta", [
        ("beta-1", "Collect onboarding feedback", "Ready", ""),
        ("beta-2", "Migrate the old notes", "In Progress", "agy"),
    ])
    # Not valid UTF-8: kb-board list exits non-zero on it.
    (hub / "projects" / "gamma" / "backlog.md").write_bytes(b"\xff\xfe# Backlog\n")
    expected = {}
    for slug in ("alpha", "beta"):
        rows = json.loads(kb_board("list", str(hub / "projects" / slug / "backlog.md"), "--all", "--json"))
        expected[slug] = [{"id": r["plan_item_id"], "title": r["title"], "status": r["status"],
                           "owner": r["claim_owner"]} for r in rows]
    expected.update({"gamma": "error", "delta": "none", "hub": "none"})

if os.environ.get("VEPOL_FIXTURE_AUTOMATIONS") == "1":
    # One small valid registry (kb-tick's own parser) and two failed kb-tick attempts today.
    import datetime
    (hub / "bin").mkdir(parents=True, exist_ok=True)
    (hub / "bin" / "_kb_processes.py").symlink_to(REAL_HUB / "bin" / "_kb_processes.py")
    (hub / "personal").mkdir(parents=True, exist_ok=True)
    (hub / "personal" / "processes.yaml").write_text(
        "- id: fixture-report\n  enabled: true\n  when: \"00:01\"\n  run: kb-fixture-report\n  outputs: [file]\n",
        encoding="utf-8")
    today = datetime.date.today().isoformat()
    for n in (1, 2):
        run = hub / ".orchestrator" / "claude-runs" / f"kbcr-fixture-{n}"
        run.mkdir(parents=True)
        run.joinpath("state.json").write_text(json.dumps({
            "status": "failed", "returncode": 1,
            "started_at": f"{today}T00:0{n}:00", "completed_at": f"{today}T00:0{n}:30",
            "updated_at": f"{today}T00:0{n}:30",
            "metadata": {"caller": "kb-tick", "process_id": "fixture-report", "occurrence_date": today},
        }), encoding="utf-8")
        run.joinpath("stdout").write_text(f"fixture stdout attempt {n}\n", encoding="utf-8")
        run.joinpath("stderr").write_text(f"step one ok\nfixture failure attempt {n}: token expired\n", encoding="utf-8")

orca = None
if os.environ.get("VEPOL_FIXTURE_ORCA") == "1":
    # A small knowledge/ for alpha, one Codex rollout with rate_limits, one Claude usage file.
    import datetime
    import time
    knowledge = hub / "projects" / "alpha"
    files = {"log.md": "# Log\n\n## [2026-09-25] fixture | alpha | first entry\n",
             "decisions/a.md": "# Decision A\n\nKeep the knowledge panel read-only.\n"}
    for rel, text in files.items():
        (knowledge / rel).parent.mkdir(parents=True, exist_ok=True)
        (knowledge / rel).write_text(text, encoding="utf-8")
    # Over the 512 KB read limit: the panel lists it, opening it is 413.
    (knowledge / "huge.md").write_text("# Huge\n" + "x" * (600 * 1024) + "\n", encoding="utf-8")
    now = time.time()
    codex_home = fixture_root / "codex-home"
    rollout = codex_home / "sessions" / "2026" / "09" / "25" / "rollout-fixture.jsonl"
    rollout.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rollout.write_text("\n".join(json.dumps(e) for e in [
        {"timestamp": stamp, "type": "session_meta", "payload": {"id": "fixture"}},
        {"timestamp": stamp, "type": "event_msg", "payload": {"type": "token_count", "info": None, "rate_limits": {
            "limit_id": "codex", "primary": {"used_percent": 14.0, "window_minutes": 10080,
                                             "resets_at": int(now + 5 * 86400)}, "secondary": None}}},
    ]) + "\n", encoding="utf-8")
    os.environ["CODEX_HOME"] = str(codex_home)
    claude_usage = fixture_root / "state" / "claude-rate-limits.json"
    claude_usage.parent.mkdir(parents=True, exist_ok=True)
    claude_usage.write_text(json.dumps({"rate_limits": {
        "five_hour": {"used_percentage": 12, "resets_at": int(now + 3600)},
        "seven_day": {"used_percentage": 40, "resets_at": int(now + 4 * 86400)}}, "at": int(now)}), encoding="utf-8")
    orca = {"knowledge": str(knowledge), "files": files,
            "codex_rollout": str(rollout), "claude_usage": str(claude_usage)}

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
app = create_app(hub=hub, config=Config(port=port, desktop=True), store_dir=fixture_root / "state")
# The fixture's own tmux socket, so a runner can end an agent the way an exit would (never kill-server).
tmux_socket = f"{os.environ['TMUX_TMPDIR']}/tmux-{os.getuid()}/default"
print(json.dumps({"port": port, "token": app.state.auth.token, "tmux_socket": tmux_socket}), flush=True)
if expected is not None:
    print(json.dumps({"tasks": expected}), flush=True)
if orca is not None:
    print(json.dumps({"orca": orca}), flush=True)
# uvicorn re-raises SIGTERM after shutdown; exiting through Python runs the cleanup below.
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
try:
    uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False,
                                 log_level="error")).run(sockets=[sock])
finally:
    # Only this fixture's own tmux server lives under its TMUX_TMPDIR.
    subprocess.run([terminal_session.tmux_binary(), "kill-server"], capture_output=True)
    shutil.rmtree(os.environ["TMUX_TMPDIR"], ignore_errors=True)
