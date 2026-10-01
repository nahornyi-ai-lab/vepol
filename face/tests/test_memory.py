"""Memory Home on the sample workspace (spec: Vepol Desktop Memory Home, "How we verify" 1)."""
from __future__ import annotations

import datetime
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

REPO = pathlib.Path(__file__).resolve().parents[2]
KB_BOARD = REPO / "bin" / "kb-board"


def test_memory_cards_match_the_sample_workspace(tmp_path, monkeypatch):
    """Critical: without it the first screen can show wrong or empty memory for every project."""
    from fastapi.testclient import TestClient

    from vepol_face.app import create_app

    workspace = tmp_path / "workspace"
    shutil.copytree(REPO / "demo" / "workspace", workspace, symlinks=True)
    hub = workspace / "knowledge"
    os.symlink(REPO / "bin", hub / "bin")

    backlogs = [hub / "backlog.md", *(workspace / "code" / p / "knowledge" / "backlog.md"
                                      for p in ("acme-web", "billing-api", "design-system"))]
    for board in backlogs:
        check = subprocess.run([str(KB_BOARD), "check", str(board)], capture_output=True, text=True)
        assert check.returncode == 0, f"kb-board check {board}: {check.stdout}{check.stderr}"

    monkeypatch.setenv("VEPOL_FACE_STATE_DIR", str(tmp_path / "state"))
    app = create_app(hub=hub)
    client = TestClient(app)
    headers = {"X-Vepol-Token": app.state.auth.token}

    r = client.get("/api/memory", headers=headers)
    assert r.status_code == 200, r.text
    cards = {c["slug"]: c for c in r.json()["cards"]}
    assert [c["slug"] for c in r.json()["cards"]] == ["hub", "acme-web", "billing-api", "design-system"]
    assert cards["hub"]["label"] == "Vepol hub"

    expected = {
        "hub": ("Three projects are active for Acme's shop: acme-web is rolling out checkout v2, billing-api is "
                "unblocking Apple Pay and then refunds, and design-system is finishing the v3 migration guide.",
                "Shared release calendar for acme-web and billing-api", (1, 1, 0),
                None, "2026-09-25"),
        "acme-web": ("Checkout v2 is live for 20% of shoppers behind the checkout-v2 flag. Card payments work; saved "
                     "addresses are the last missing piece before a full rollout.",
                     "Saved addresses in checkout v2", (1, 1, 1),
                     ("Feature flags live in a config file, not a flag service", "2026-09-16"), "2026-09-26"),
        "billing-api": ("Invoices and card payments run on the new ledger. Next up are the Apple Pay verification file "
                        "for acme-web and the refunds endpoint; webhook retries wait on the payment provider.",
                        "Publish the Apple Pay domain verification file for acme-web", (0, 2, 1),
                        ("Invoices write to an append-only ledger", "2026-09-18"), "2026-09-24"),
        "design-system": ("Design tokens v3 are published. acme-web already uses them; the billing admin pages still "
                          "use v2, and the v2 to v3 migration guide is half written.",
                          "Write the v2 to v3 migration guide", (1, 1, 0),
                          ("Components ship without CSS-in-JS", "2026-09-17"), "2026-09-19"),
    }
    for slug, (now, next_title, counts, decision, activity) in expected.items():
        card = cards[slug]
        assert card["now"] == now, slug
        plans = card["plans"]
        assert plans["state"] == "ok", (slug, plans)
        assert plans["next"] == next_title, slug
        assert (plans["in_progress"], plans["ready"], plans["blocked"]) == counts, slug
        got = card["last_decision"] and (card["last_decision"]["title"], card["last_decision"]["date"])
        assert got == decision, slug
        assert card["last_activity"] == activity, slug
        assert card["status"] == "up_to_date", slug

    r = client.get("/api/memory/project", params={"target": "acme-web"}, headers=headers)
    assert r.status_code == 200, r.text
    page = r.json()
    # The project screen's State box: the same snapshot as the card, dated by state.md.
    assert page["now"] == cards["acme-web"]["now"]
    state_md = workspace / "code" / "acme-web" / "knowledge" / "state.md"
    assert page["state_date"] == datetime.date.fromtimestamp(state_md.stat().st_mtime).isoformat()
    assert page["history"][0]["date"] == "2026-09-26"
    assert page["history"][0]["heading"] == 'progress | acme-web | "Saved addresses started"'
    assert page["lessons"].startswith(
        "- Lock every payment submit button on the first click and send an idempotency key with each payment request")
    assert [d["title"] for d in page["decisions"]] == [
        "Feature flags live in a config file, not a flag service", "Server-render the checkout pages"]
