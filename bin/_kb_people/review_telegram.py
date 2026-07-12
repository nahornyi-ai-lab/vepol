"""Telegram review surface for the people notebook.

Staged candidates are pushed to the owner's private chat (same bot/chat
as the daily digest) as one message per candidate with inline buttons;
`kb-people-review-bot` consumes the button callbacks and delegates every
mutation to the existing single-writer CLIs (`kb-extract-people
--approve/--reject`, `kb-contact merge/enrich`).

Contract: knowledge/decisions/people-review-telegram-2026-07-05.md
(spec-contract:sha256:11703f44…). Key invariants:
  - every outbox read-modify-write runs under `.cards.lock`; no writer
    saves a copy loaded outside its own lock window;
  - callback data carries only random cbids, never slugs;
  - callbacks are bound to the stored chat_id/message_id;
  - actions are idempotent so at-least-once update delivery is safe.
"""

from __future__ import annotations

import json
import os
import re
import secrets as _secrets
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import card, filters, index, locks

BIN_DIR = Path(__file__).resolve().parent.parent

OUTBOX_NAME = ".review-outbox.json"
CAP = 8
PENDING_TTL_DAYS = 7
TEXT_LIMIT = 3500  # Telegram cap is 4096; keep headroom for outcome lines.
CLI_TIMEOUT_S = 120
ENRICH_TIMEOUT_S = 520  # kb-contact enrich itself caps codex at 420s.

LABELS = {
    "ru": {
        "new_header": "🆕 Новый человек: {name}",
        "sightings_header": "📌 Новые упоминания: {name}",
        "seen": "Встречен: {n} раз(а)",
        "btn_approve": "✅ Принять",
        "btn_reject": "🚫 Отклонить",
        "btn_merge": "🔀 Влить…",
        "btn_defer": "⏸ Позже",
        "btn_search": "🔎 Поиск в интернете",
        "btn_nosearch": "⏭ Без поиска",
        "btn_back": "« Назад",
        "approved": "✅ Принят",
        "rejected": "🚫 Отклонён",
        "deferred": "⏸ Отложен — вернётся в следующем дайджесте",
        "merged": "🔀 Влит в {target}",
        "merge_prompt": "Куда влить?",
        "merge_no_targets": "Нет подходящих карточек для влития",
        "enrich_running": "🔎 Ищу в интернете… (до 7 минут)",
        "enrich_busy": "Поиск уже идёт",
        "enrich_found": "🔎 Найдено:",
        "enrich_none": "🔎 Ничего надёжного не нашлось",
        "enrich_failed": "⚠️ Поиск не удался — можно нажать ещё раз",
        "enrich_skipped": "⏭ Поиск пропущен",
        "bot_rejected": "🚫 Отклонён автоматически: бот, не человек",
        "already": "Уже обработан",
        "not_authorized": "Нет доступа",
        "action_failed": "Не получилось — смотри логи",
    },
    "en": {
        "new_header": "🆕 New person: {name}",
        "sightings_header": "📌 New sightings: {name}",
        "seen": "Seen {n} time(s)",
        "btn_approve": "✅ Approve",
        "btn_reject": "🚫 Reject",
        "btn_merge": "🔀 Merge…",
        "btn_defer": "⏸ Later",
        "btn_search": "🔎 Web search",
        "btn_nosearch": "⏭ Skip search",
        "btn_back": "« Back",
        "approved": "✅ Approved",
        "rejected": "🚫 Rejected",
        "deferred": "⏸ Deferred — returns in the next digest",
        "merged": "🔀 Merged into {target}",
        "merge_prompt": "Merge into which card?",
        "merge_no_targets": "No matching live cards to merge into",
        "enrich_running": "🔎 Searching the web… (up to 7 min)",
        "enrich_busy": "Search already running",
        "enrich_found": "🔎 Found:",
        "enrich_none": "🔎 Nothing reliable found",
        "enrich_failed": "⚠️ Search failed — tap again to retry",
        "enrich_skipped": "⏭ Search skipped",
        "bot_rejected": "🚫 Auto-rejected: bot account, not a person",
        "already": "Already handled",
        "not_authorized": "Not authorized",
        "action_failed": "Action failed — check logs",
    },
}


def labels() -> dict:
    try:
        import _kb_profile
        lang = _kb_profile.get_language(os.environ.get("KB_HUB"))
    except Exception:
        lang = "en"
    return LABELS.get(lang, LABELS["en"])


# ---------------------------------------------------------------------------
# Bot API plumbing
# ---------------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, status: int, description: str = ""):
        self.status = status
        self.description = description
        super().__init__(f"telegram api error {status}: {description}")


def _api_base() -> str:
    return os.environ.get("KB_TG_API_BASE", "https://api.telegram.org")


def creds(hub: Path):
    """(token, chat_id) from env or $hub/personal/.secrets; None if absent."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN")
             or os.environ.get("TELEGRAM_TOKEN"))
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        sec = hub / "personal" / ".secrets"
        if sec.is_file():
            try:
                text = sec.read_text(encoding="utf-8")
            except OSError:
                text = ""

            def rd(key: str) -> str:
                m = re.findall(rf'^(?:export\s+)?{key}=(.*)$', text, re.M)
                return m[-1].strip().strip('"').strip("'") if m else ""

            token = token or rd("TELEGRAM_BOT_TOKEN") or rd("TELEGRAM_TOKEN")
            chat = chat or rd("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return None
    try:
        return token, int(chat)
    except ValueError:
        return None


def api(token: str, method: str, params: dict, timeout: int = 30) -> object:
    req = urllib.request.Request(
        f"{_api_base()}/bot{token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            desc = json.loads(e.read().decode()).get("description", "")
        except Exception:
            desc = ""
        raise ApiError(e.code, desc) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ApiError(0, str(e)) from None
    if not payload.get("ok"):
        raise ApiError(200, str(payload.get("description", "")))
    return payload.get("result")


# ---------------------------------------------------------------------------
# Outbox state (all RMW under .cards.lock — spec blocker #1)
# ---------------------------------------------------------------------------

def _outbox_path(hub: Path) -> Path:
    return hub / "people" / OUTBOX_NAME


def _load_outbox(hub: Path) -> dict:
    try:
        data = json.loads(_outbox_path(hub).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "items" in data:
            data.setdefault("offset", 0)
            return data
    except (OSError, ValueError):
        pass
    return {"schema_version": 1, "offset": 0, "items": {}}


def _save_outbox(hub: Path, data: dict) -> None:
    path = _outbox_path(hub)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".outbox-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _expire_stale(data: dict, now: datetime) -> None:
    """pending older than PENDING_TTL_DAYS → deferred (anti-starvation);
    `sending` reservations older than 10 min are dead crashed sends
    (no message exists for them) → dropped entirely."""
    dead = []
    for cbid, it in data["items"].items():
        try:
            sent = datetime.fromisoformat(it.get("sent_at", ""))
        except ValueError:
            continue
        if (it.get("state") == "pending"
                and (now - sent).days >= PENDING_TTL_DAYS):
            it["state"] = "deferred"
        elif (it.get("state") == "sending"
                and (now - sent).total_seconds() >= 600):
            dead.append(cbid)
    for cbid in dead:
        del data["items"][cbid]


# ---------------------------------------------------------------------------
# Staged candidates → message text + keyboards
# ---------------------------------------------------------------------------

def staged_items(hub: Path) -> list[dict]:
    people = hub / "people"
    if not people.is_dir():
        return []
    items = []
    for p in sorted(people.glob("*.staged.md")):
        items.append({"slug": p.name[:-len(".staged.md")],
                      "kind": "new-card", "path": p})
    for p in sorted(people.glob("*.staged-sightings.md")):
        slug = p.name[:-len(".staged-sightings.md")]
        if not (people / f"{slug}.staged.md").exists():
            items.append({"slug": slug, "kind": "sightings", "path": p})
    return items


def _staged_meta(path: Path) -> dict:
    try:
        import frontmatter
        with open(path, encoding="utf-8") as fh:
            return frontmatter.load(fh).metadata
    except Exception:
        return {}


def _staged_rows(path: Path) -> list[list[str]]:
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3 or "Date" in cells[0] or "---" in cells[0]:
                continue
            rows.append(cells[:3])
    except OSError:
        pass
    return rows


def candidate_text(hub: Path, item: dict, L: dict) -> str:
    slug, kind = item["slug"], item["kind"]
    people = hub / "people"
    rows = []
    lines = []
    if kind == "new-card":
        meta = _staged_meta(people / f"{slug}.staged.md")
        name = str(meta.get("name") or slug)
        lines.append(L["new_header"].format(name=name))
        for field in ("email", "telegram", "company", "role", "source",
                      "first_met_context"):
            v = meta.get(field)
            if v:
                lines.append(f"{field}: {v}")
        rows = _staged_rows(people / f"{slug}.staged.md")
        rows += _staged_rows(people / f"{slug}.staged-sightings.md")
    else:
        lines.append(L["sightings_header"].format(name=slug))
        rows = _staged_rows(people / f"{slug}.staged-sightings.md")
    if rows:
        lines.append(L["seen"].format(n=len(rows)))
        for r in rows[:3]:
            summary = r[2][:120] if len(r) > 2 else ""
            lines.append(f"• {r[0]} {r[1]}: {summary}")
    return "\n".join(lines)[:TEXT_LIMIT]


def _kb_main(cbid: str, kind: str, L: dict) -> dict:
    rows = [[{"text": L["btn_approve"], "callback_data": f"pn:a:{cbid}"},
             {"text": L["btn_reject"], "callback_data": f"pn:r:{cbid}"}]]
    second = []
    if kind == "new-card":
        second.append({"text": L["btn_merge"], "callback_data": f"pn:m:{cbid}"})
    second.append({"text": L["btn_defer"], "callback_data": f"pn:d:{cbid}"})
    rows.append(second)
    return {"inline_keyboard": rows}


def _kb_enrich(cbid: str, L: dict) -> dict:
    return {"inline_keyboard": [[
        {"text": L["btn_search"], "callback_data": f"pn:e:{cbid}"},
        {"text": L["btn_nosearch"], "callback_data": f"pn:x:{cbid}"},
    ]]}


def _kb_merge_menu(cbid: str, targets: list[str], L: dict) -> dict:
    rows = [[{"text": t, "callback_data": f"pn:mt:{cbid}:{i}"}]
            for i, t in enumerate(targets)]
    rows.append([{"text": L["btn_back"], "callback_data": f"pn:b:{cbid}"}])
    return {"inline_keyboard": rows}


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

def push(hub: Path, cap: int = CAP, flush_all: bool = False,
         quiet: bool = True) -> int:
    """Send staged candidates (not already pending) to the owner chat.

    Soft-fails on any Telegram error: candidates stay staged, nothing is
    recorded for the failed send. Returns the number of messages sent.
    """
    cr = creds(hub)
    if cr is None:
        if not quiet:
            print("review-push: no telegram credentials, skipping",
                  file=sys.stderr)
        return 0
    token, chat_id = cr
    L = labels()
    now = datetime.now(timezone.utc)
    sent = 0
    # Fresh candidates (never pushed) take the window slots BEFORE
    # re-pushable deferred ones — a stale deferred backlog must not
    # starve new people out of the chat (spec anti-starvation rule).
    with locks.cards_lock():
        known = {(it["slug"], it.get("kind", "new-card"))
                 for it in _load_outbox(hub)["items"].values()}
    ordered = sorted(staged_items(hub),
                     key=lambda i: ((i["slug"], i["kind"]) in known,
                                    i["slug"]))
    # Phase 1 — bot sweep over the ENTIRE staged backlog, BEFORE the send
    # loop: the cleanup must never depend on window state (a full window
    # breaks the send loop early and would skip bots queued behind it).
    # Bots are never people (owner directive 2026-07-05); this catches
    # staged backlog created before the extractor-level filter.
    humans = []
    for item in ordered:
        # The sweep applies to NEW candidates only. Sightings-only items
        # belong to an existing LIVE card the owner already approved —
        # with no staged frontmatter their name would fall back to the
        # live slug, and a human like "John Talbot" (no email in the
        # fallback) would get their pending sightings auto-deleted.
        if item["kind"] != "new-card":
            humans.append(item)
            continue
        meta = _staged_meta(hub / "people" / f"{item['slug']}.staged.md")
        if not filters.is_bot_identity(
                name=str(meta.get("name") or item["slug"]),
                email=str(meta.get("email") or ""),
                telegram=str(meta.get("telegram") or "")):
            humans.append(item)
            continue
        try:
            _run_cli(hub, "kb-extract-people", "--hub", str(hub),
                     "--reject", item["slug"], "--reason", "bot-identity")
        except Exception as e:
            if not quiet:
                print(f"review-push: bot auto-reject failed for "
                      f"{item['slug']}: {e}", file=sys.stderr)
            continue
        # A bot pushed BEFORE this filter existed may still hold a
        # pending outbox entry: close it too, or it keeps a window
        # slot and a live keyboard in the chat forever.
        with locks.cards_lock():
            data = _load_outbox(hub)
            stale = {cbid: dict(it) for cbid, it in data["items"].items()
                     if it["slug"] == item["slug"]
                     and it.get("kind", "new-card") == item["kind"]
                     and it.get("state") in ("pending", "sending")}
            for cbid in stale:
                data["items"][cbid]["state"] = "rejected"
            if stale:
                _save_outbox(hub, data)
        for it in stale.values():  # edits stay OUTSIDE the lock
            if it.get("message_id"):
                _edit(token, it["chat_id"], it["message_id"],
                      f"🤖 {item['slug']}\n\n" + L["bot_rejected"])

    # Phase 2 — send loop over human candidates only.
    for item in humans:
        # RESERVE the slot under the lock before sending (state
        # "sending" counts toward window + dedup), so two concurrent
        # pushers — extractor auto-push vs listener refill — can never
        # double-send the same candidate or blow past the cap. The
        # network send stays OUTSIDE the lock so a slow Telegram call
        # can't starve other .cards.lock writers.
        cbid = _secrets.token_hex(5)
        with locks.cards_lock():
            data = _load_outbox(hub)
            _expire_stale(data, now)
            live = [it for it in data["items"].values()
                    if it.get("state") in ("pending", "sending")]
            duplicate = any(it["slug"] == item["slug"]
                            and it.get("kind", "new-card") == item["kind"]
                            for it in live)
            window_full = (not flush_all) and len(live) >= cap
            if not (duplicate or window_full):
                data["items"][cbid] = {
                    "slug": item["slug"],
                    "kind": item["kind"],
                    "chat_id": chat_id,
                    "message_id": None,
                    "state": "sending",
                    "sent_at": now.isoformat(),
                }
            _save_outbox(hub, data)
        if window_full:
            break
        if duplicate:
            continue
        try:
            res = api(token, "sendMessage", {
                "chat_id": chat_id,
                "text": candidate_text(hub, item, L),
                "reply_markup": _kb_main(cbid, item["kind"], L),
            })
        except ApiError as e:
            # Roll the reservation back — no message exists for it.
            with locks.cards_lock():
                data = _load_outbox(hub)
                data["items"].pop(cbid, None)
                _save_outbox(hub, data)
            if not quiet:
                print(f"review-push: telegram send failed ({e})",
                      file=sys.stderr)
            break
        with locks.cards_lock():
            data = _load_outbox(hub)
            entry = data["items"].get(cbid)
            if entry is not None:
                entry["message_id"] = res.get("message_id")
                entry["state"] = "pending"
                _save_outbox(hub, data)
        sent += 1
    return sent


# ---------------------------------------------------------------------------
# Listener actions
# ---------------------------------------------------------------------------

def _run_cli(hub: Path, binary: str, *args: str,
             timeout: int = CLI_TIMEOUT_S) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["KB_HUB"] = str(hub)
    return subprocess.run(
        [sys.executable, str(BIN_DIR / binary), *args],
        capture_output=True, text=True, timeout=timeout, env=env)


def _update_item(hub: Path, cbid: str, **fields) -> dict | None:
    """Lock-load-mutate-save one outbox item; returns the new item."""
    with locks.cards_lock():
        data = _load_outbox(hub)
        item = data["items"].get(cbid)
        if item is not None:
            item.update(fields)
            _save_outbox(hub, data)
        return item


def _get_item(hub: Path, cbid: str) -> dict | None:
    with locks.cards_lock():
        return _load_outbox(hub)["items"].get(cbid)


def _answer(token: str, cb_id: str, text: str | None = None) -> None:
    params = {"callback_query_id": cb_id}
    if text:
        params["text"] = text
    try:
        api(token, "answerCallbackQuery", params)
    except ApiError:
        pass


def _edit(token: str, chat_id: int, message_id: int, text: str,
          keyboard: dict | None = None) -> None:
    """Edit outcome text; on failure fall back to bare keyboard removal.

    The disk action is already durable — rendering failures must never
    leave a live keyboard behind (spec AC13)."""
    params = {"chat_id": chat_id, "message_id": message_id,
              "text": text[:TEXT_LIMIT + 400]}
    if keyboard is not None:
        params["reply_markup"] = keyboard
    try:
        api(token, "editMessageText", params)
    except ApiError:
        try:
            api(token, "editMessageReplyMarkup", {
                "chat_id": chat_id, "message_id": message_id,
                "reply_markup": {"inline_keyboard": []}})
        except ApiError:
            pass


def _staged_exists(hub: Path, slug: str) -> bool:
    people = hub / "people"
    return ((people / f"{slug}.staged.md").exists()
            or (people / f"{slug}.staged-sightings.md").exists())


def _enrich_eligible(hub: Path, slug: str) -> bool:
    """Mirror kb-contact _enrich_slug's search-once skip rule: only a
    completed codex search (codex-*/none-found-*) or already-known
    profiles block the offer — `manual` means "never searched"."""
    post = card.load(slug)
    if post is None:
        return False
    status = str(post.get("enrichment_status", "") or "")
    if status.startswith("codex-") or status.startswith("none-found-"):
        return False
    return not (post.get("linkedin") or post.get("public_profiles"))


def _enrich_outcome(hub: Path, slug: str, L: dict,
                    rc: int) -> str:
    if rc != 0:
        return L["enrich_failed"]
    post = card.load(slug)
    status = str(post.get("enrichment_status", "")) if post else ""
    if status.startswith("none-found"):
        return L["enrich_none"]
    profiles = (post.get("public_profiles") or []) if post else []
    urls = [p.get("url", "") for p in profiles if isinstance(p, dict)]
    urls = [u for u in urls if u]
    if urls:
        return L["enrich_found"] + "\n" + "\n".join(urls[:3])
    return L["enrich_none"]


def _merge_targets(hub: Path, name: str) -> list[str]:
    """Top-5 live-card slugs fuzzy-matching the staged name."""
    people = hub / "people"
    seen: list[str] = []
    try:
        for uid, _score in index.lookup_by_name(name)[:20]:
            slug = index.get_slug(uid)
            if (slug and slug not in seen
                    and (people / f"{slug}.md").exists()):
                seen.append(slug)
            if len(seen) >= 5:
                break
    except Exception:
        pass
    return seen


class Listener:
    """Callback processor. One instance per daemon/--once run."""

    def __init__(self, hub: Path, token: str, chat_id: int):
        self.hub = hub
        self.token = token
        self.chat_id = chat_id
        self.L = labels()
        self.workers: list[threading.Thread] = []

    # -- startup reconciliation (spec blocker #2) -------------------------
    def reconcile(self) -> None:
        with locks.cards_lock():
            data = _load_outbox(self.hub)
            stuck = {cbid: dict(it) for cbid, it in data["items"].items()
                     if it.get("state") == "enriching"}
        for cbid, it in stuck.items():
            final = it.get("final_slug") or it["slug"]
            post = card.load(final)
            # Only a COMPLETED search counts (codex-*/none-found-*):
            # the default `manual` means "never searched", so an
            # interrupted search must be re-offered, not swallowed.
            status = str((post.get("enrichment_status") if post else "") or "")
            done = (status.startswith("codex-")
                    or status.startswith("none-found-"))
            _update_item(self.hub, cbid,
                         state="enriched" if done else "approved")
            if not done and it.get("message_id"):
                _edit(self.token, it["chat_id"], it["message_id"],
                      self.L["enrich_failed"], _kb_enrich(cbid, self.L))

    # -- one callback ------------------------------------------------------
    def process_update(self, upd: dict) -> None:
        cb = upd.get("callback_query")
        if not cb:
            return  # non-callback update queued earlier: skip, offset advances
        cb_id = cb.get("id", "")
        data = cb.get("data", "") or ""
        frm = (cb.get("from") or {}).get("id")
        msg = cb.get("message") or {}
        if frm != self.chat_id:
            _answer(self.token, cb_id, self.L["not_authorized"])
            print(f"review-bot: refused callback from {frm}", file=sys.stderr)
            return
        m = re.match(r"^pn:(a|r|d|m|mt|b|e|x):([a-z0-9]{1,32})(?::(\d+))?$",
                     data)
        if not m:
            _answer(self.token, cb_id)
            return
        verb, cbid, slot = m.group(1), m.group(2), m.group(3)
        item = _get_item(self.hub, cbid)
        if item is None:
            _answer(self.token, cb_id, self.L["already"])
            if msg.get("message_id"):
                _edit(self.token, (msg.get("chat") or {}).get("id"),
                      msg["message_id"], msg.get("text") or self.L["already"])
            return
        # Bind the button to the message we actually sent (spec auth).
        if ((msg.get("chat") or {}).get("id") != item.get("chat_id")
                or msg.get("message_id") != item.get("message_id")):
            _answer(self.token, cb_id, self.L["not_authorized"])
            return
        handler = getattr(self, f"_verb_{verb}")
        handler(cb_id, cbid, item, msg, slot)

    # -- helpers -----------------------------------------------------------
    def _finish(self, item: dict, msg: dict, outcome: str,
                keyboard: dict | None = None) -> None:
        base = msg.get("text") or ""
        _edit(self.token, item["chat_id"], item["message_id"],
              (base + "\n\n" + outcome).strip(), keyboard)

    def _already(self, cb_id: str, cbid: str, item: dict, msg: dict) -> None:
        # Never clobber a terminal state: a replayed callback (crash
        # before the offset save — at-least-once delivery) must converge
        # to the SAME outcome, not overwrite it with "closed" (AC9).
        if item.get("state") in ("pending", "deferred"):
            _update_item(self.hub, cbid, state="closed")
        _answer(self.token, cb_id, self.L["already"])
        self._finish(item, msg, self.L["already"])

    def _replay_terminal(self, cb_id: str, cbid: str, item: dict,
                         msg: dict) -> bool:
        """Re-render the terminal outcome for a replayed callback.

        Returns True when the item already reached a terminal state and
        the replay was answered idempotently."""
        state = item.get("state")
        if state == "approved":
            final = item.get("final_slug") or item["slug"]
            _answer(self.token, cb_id, self.L["approved"])
            if (item.get("kind") == "new-card"
                    and _enrich_eligible(self.hub, final)):
                self._finish(item, msg, self.L["approved"],
                             _kb_enrich(cbid, self.L))
            else:
                self._finish(item, msg, self.L["approved"])
            return True
        if state == "rejected":
            _answer(self.token, cb_id, self.L["rejected"])
            self._finish(item, msg, self.L["rejected"])
            return True
        if state == "merged":
            outcome = self.L["merged"].format(
                target=item.get("final_slug") or "")
            _answer(self.token, cb_id, outcome)
            self._finish(item, msg, outcome)
            return True
        if state == "enriching":
            _answer(self.token, cb_id, self.L["enrich_busy"])
            return True
        if state in ("enriched", "closed"):
            _answer(self.token, cb_id, self.L["already"])
            return True
        return False

    # -- verbs ---------------------------------------------------------------
    def _verb_a(self, cb_id, cbid, item, msg, slot) -> None:
        slug = item["slug"]
        if not _staged_exists(self.hub, slug):
            if not self._replay_terminal(cb_id, cbid, item, msg):
                self._already(cb_id, cbid, item, msg)
            return
        res = _run_cli(self.hub, "kb-extract-people",
                       "--hub", str(self.hub), "--approve", slug)
        if res.returncode != 0:
            _answer(self.token, cb_id, self.L["action_failed"])
            print(f"review-bot: approve {slug} failed: "
                  f"{(res.stderr or '').strip()}", file=sys.stderr)
            return
        final = slug
        m = re.search(r"promoted staged card as '([^']+)'", res.stdout or "")
        if m:
            final = m.group(1)
        _update_item(self.hub, cbid, state="approved", final_slug=final)
        _answer(self.token, cb_id, self.L["approved"])
        if item["kind"] == "new-card" and _enrich_eligible(self.hub, final):
            self._finish(item, msg, self.L["approved"],
                         _kb_enrich(cbid, self.L))
        else:
            self._finish(item, msg, self.L["approved"])
        push(self.hub)

    def _verb_r(self, cb_id, cbid, item, msg, slot) -> None:
        slug = item["slug"]
        if not _staged_exists(self.hub, slug):
            if not self._replay_terminal(cb_id, cbid, item, msg):
                self._already(cb_id, cbid, item, msg)
            return
        res = _run_cli(self.hub, "kb-extract-people",
                       "--hub", str(self.hub), "--reject", slug,
                       "--reason", "telegram-reject")
        if res.returncode != 0:
            _answer(self.token, cb_id, self.L["action_failed"])
            return
        _update_item(self.hub, cbid, state="rejected")
        _answer(self.token, cb_id, self.L["rejected"])
        self._finish(item, msg, self.L["rejected"])
        push(self.hub)

    def _verb_d(self, cb_id, cbid, item, msg, slot) -> None:
        _update_item(self.hub, cbid, state="deferred")
        _answer(self.token, cb_id, self.L["deferred"])
        self._finish(item, msg, self.L["deferred"])

    def _verb_m(self, cb_id, cbid, item, msg, slot) -> None:
        slug = item["slug"]
        if not _staged_exists(self.hub, slug):
            self._already(cb_id, cbid, item, msg)
            return
        meta = _staged_meta(self.hub / "people" / f"{slug}.staged.md")
        name = str(meta.get("name") or slug)
        targets = _merge_targets(self.hub, name)
        if not targets:
            _answer(self.token, cb_id, self.L["merge_no_targets"])
            return
        # Snapshot the rendered list so slot numbers can never go stale
        # against a mutated index (spec blocker #3).
        _update_item(self.hub, cbid, menu=targets)
        _answer(self.token, cb_id)
        base = re.sub(r"\n\n" + re.escape(self.L["merge_prompt"]) + r"$", "",
                      msg.get("text") or "")
        _edit(self.token, item["chat_id"], item["message_id"],
              (base + "\n\n" + self.L["merge_prompt"])[:TEXT_LIMIT + 400],
              _kb_merge_menu(cbid, targets, self.L))

    def _verb_mt(self, cb_id, cbid, item, msg, slot) -> None:
        slug = item["slug"]
        # Replay convergence FIRST: a completed merge must re-render its
        # terminal outcome even if the menu snapshot or the target card
        # has since changed (round-3 nit).
        if not _staged_exists(self.hub, slug):
            if not self._replay_terminal(cb_id, cbid, item, msg):
                self._already(cb_id, cbid, item, msg)
            return
        menu = item.get("menu") or []
        idx = int(slot) if slot is not None else -1
        if idx < 0 or idx >= len(menu):
            _answer(self.token, cb_id, self.L["already"])
            return
        target = menu[idx]
        if not (self.hub / "people" / f"{target}.md").exists():
            _answer(self.token, cb_id, self.L["already"])
            return
        res = _run_cli(self.hub, "kb-contact", "merge", slug, target)
        if res.returncode != 0:
            _answer(self.token, cb_id, self.L["action_failed"])
            print(f"review-bot: merge {slug}→{target} failed: "
                  f"{(res.stderr or '').strip()}", file=sys.stderr)
            return
        _update_item(self.hub, cbid, state="merged", final_slug=target)
        outcome = self.L["merged"].format(target=target)
        _answer(self.token, cb_id, outcome)
        self._finish(item, msg, outcome)
        push(self.hub)

    def _verb_b(self, cb_id, cbid, item, msg, slot) -> None:
        _answer(self.token, cb_id)
        staged = {"slug": item["slug"], "kind": item.get("kind", "new-card"),
                  "path": None}
        text = candidate_text(self.hub, staged, self.L)
        _edit(self.token, item["chat_id"], item["message_id"], text,
              _kb_main(cbid, staged["kind"], self.L))

    def _verb_e(self, cb_id, cbid, item, msg, slot) -> None:
        final = item.get("final_slug") or item["slug"]
        # Single-slot worker GLOBALLY (contract): one Codex search at a
        # time across all candidates, not just per cbid.
        self.workers = [t for t in self.workers if t.is_alive()]
        if self.workers:
            _answer(self.token, cb_id, self.L["enrich_busy"])
            return
        # Durable intent BEFORE the worker starts (spec blocker #2):
        # a crash after this point reconciles on the next startup, and
        # kb-contact enrich itself enforces search-once on the card.
        # The search may ONLY start from `approved` — a stale/replayed
        # pn:e must never override an explicit «без поиска» (closed) or
        # any other terminal state. Decide under the lock, answer AFTER
        # releasing it — no Telegram I/O while holding .cards.lock.
        with locks.cards_lock():
            data = _load_outbox(self.hub)
            cur = data["items"].get(cbid)
            if cur is None or cur.get("state") != "approved":
                verdict = ("busy" if cur is not None
                           and cur.get("state") == "enriching" else "already")
            else:
                cur["state"] = "enriching"
                _save_outbox(self.hub, data)
                verdict = "go"
        if verdict != "go":
            _answer(self.token, cb_id,
                    self.L["enrich_busy"] if verdict == "busy"
                    else self.L["already"])
            return
        _answer(self.token, cb_id, self.L["enrich_running"])

        def work():
            try:
                res = _run_cli(self.hub, "kb-contact", "enrich", final,
                               timeout=ENRICH_TIMEOUT_S)
                rc = res.returncode
            except subprocess.TimeoutExpired:
                rc = 1
            outcome = _enrich_outcome(self.hub, final, self.L, rc)
            ok = rc == 0
            _update_item(self.hub, cbid,
                         state="enriched" if ok else "approved")
            self._finish(item, msg, outcome,
                         None if ok else _kb_enrich(cbid, self.L))

        t = threading.Thread(target=work, daemon=True)
        t.start()
        self.workers.append(t)

    def _verb_x(self, cb_id, cbid, item, msg, slot) -> None:
        # Symmetric guard: skip-search only applies while the offer is
        # open (`approved`); a stale pn:x must not clobber a running or
        # completed search. Decide under the lock, answer AFTER
        # releasing it — no Telegram I/O while holding .cards.lock.
        with locks.cards_lock():
            data = _load_outbox(self.hub)
            cur = data["items"].get(cbid)
            if cur is None or cur.get("state") != "approved":
                verdict = ("busy" if cur is not None
                           and cur.get("state") == "enriching" else "already")
            else:
                cur["state"] = "closed"
                _save_outbox(self.hub, data)
                verdict = "go"
        if verdict != "go":
            _answer(self.token, cb_id,
                    self.L["enrich_busy"] if verdict == "busy"
                    else self.L["already"])
            return
        _answer(self.token, cb_id)
        self._finish(item, msg, self.L["enrich_skipped"])

    # -- polling -----------------------------------------------------------
    def poll_once(self, long_poll: bool = False) -> int:
        """One getUpdates round. Returns number of processed updates."""
        with locks.cards_lock():
            offset = _load_outbox(self.hub).get("offset", 0)
        params = {"offset": offset, "timeout": 50 if long_poll else 0,
                  "allowed_updates": ["callback_query"]}
        updates = api(self.token, "getUpdates", params,
                      timeout=60 if long_poll else 30)
        if not isinstance(updates, list) or not updates:
            return 0
        max_id = offset - 1
        for upd in updates:
            try:
                self.process_update(upd)
            except Exception as e:  # never let one update kill the loop
                print(f"review-bot: update {upd.get('update_id')} failed: "
                      f"{e}", file=sys.stderr)
            max_id = max(max_id, int(upd.get("update_id", 0)))
        with locks.cards_lock():
            data = _load_outbox(self.hub)
            data["offset"] = max(data.get("offset", 0), max_id + 1)
            _save_outbox(self.hub, data)
        return len(updates)

    def join_workers(self, timeout: float = ENRICH_TIMEOUT_S) -> None:
        for t in self.workers:
            t.join(timeout=timeout)
        self.workers = [t for t in self.workers if t.is_alive()]
