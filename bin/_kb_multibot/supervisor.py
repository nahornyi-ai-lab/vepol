"""Main async supervisor loop — wires registry, cache, queue, spawner, guards.

Concept §7 + §16: one Python+asyncio binary. Entrypoint `kb-multibot-supervisor`
runs `Supervisor.run()`. LaunchAgent restarts it via KeepAlive.

Top-level flow per concept §7.3:
  1. Load config + registry + StateStore.
  2. Connect Telethon listener (catchup from observer offsets, then go live).
  3. On each incoming TelegramEvent:
     a. dedup, cache, observer-offset persist
     b. parse mentions → identify target agent(s)
     c. apply loop guards
     d. for each target: emoji-ack, enqueue, async spawn coordinator
  4. spawn coordinator: acquire per-agent flock, watchdog.add(),
     spawner.spawn() with stdout→watchdog.touch, send result via Bot API,
     watchdog.remove() + state.write_run().
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import signal
import uuid
from pathlib import Path

from .cache import MessageCache
from .config import SupervisorConfig, load_config, read_bot_token
from .events import (
    QueueEntry,
    RUN_STATUS_FAILED,
    RUN_STATUS_KILLED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCESS,
    RUN_STATUS_TIMEOUT,
    RunState,
    TelegramEvent,
)
from .flock import AgentLock, AgentLockBusy
from .listener import GroupListener
from .loops import LoopGuard
from .mention import extract_stop_targets, filter_bot_mentions, has_stop_command
from .prompts import assemble_spawn_prompt
from .registry import AgentRegistry, AgentSpec, load_from_projects_dir
from .sender import BotApiSender
from .spawner import SpawnFailed, make_adapter
from .state import StateStore
from .watchdog import Watchdog


logger = logging.getLogger("kb-multibot")


# Concept §7.4 queue cap
QUEUE_MAX = 20


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_epoch() -> float:
    return dt.datetime.now(dt.timezone.utc).timestamp()


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


class Supervisor:
    """Long-running supervisor process. Single instance per machine."""

    def __init__(self, config: SupervisorConfig):
        self.config = config
        self.state = StateStore(config.state_root)
        self.state.ensure_dirs()
        self.cache = MessageCache()
        self.loop_guard = LoopGuard()
        self.watchdog = Watchdog()
        self.sender = BotApiSender()
        self.registry: AgentRegistry = AgentRegistry({})
        self.listener: GroupListener | None = None
        # Track active spawn tasks so we can wait on shutdown
        self._active_tasks: set[asyncio.Task] = set()
        # Dedup table for events seen this session (in addition to cache dedup)
        self._seen_events: set[tuple[int, int]] = set()
        self._shutdown = asyncio.Event()

    # ----- Lifecycle -----

    async def run(self) -> None:
        """Run until SIGTERM/SIGINT — main entrypoint called by kb-multibot-supervisor."""
        logger.info("supervisor v0.1: starting, group_chat_id=%s", self.config.group_chat_id)
        self._install_signal_handlers()
        self._reload_registry()

        # Build bot_id → slug mapping for listener
        bot_id_map: dict[int, str] = {}
        for spec in self.registry.all_agents():
            if spec.bot_id:
                bot_id_map[spec.bot_id] = spec.slug

        self.listener = GroupListener(
            api_id=self.config.tg_api_id,
            api_hash=self.config.tg_api_hash,
            session_file=str(self.config.session_file),
            group_chat_id=self.config.group_chat_id,
            on_event=self._handle_event,
        )
        self.listener.set_bot_id_mapping(bot_id_map)

        catchup = self.state.read_observer_offsets()
        await self.listener.start(catchup_offsets=catchup)

        watchdog_task = asyncio.create_task(self._watchdog_loop())
        try:
            await self._run_until_signal()
        finally:
            logger.info("supervisor: shutting down")
            watchdog_task.cancel()
            await self._drain_active_tasks()
            if self.listener:
                await self.listener.stop()
            await self.sender.close()

    async def _run_until_signal(self) -> None:
        listener_task = asyncio.create_task(self.listener.run_forever())
        shutdown_task = asyncio.create_task(self._shutdown.wait())
        done, _ = await asyncio.wait(
            {listener_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in (listener_task, shutdown_task):
            if not t.done():
                t.cancel()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: self._shutdown.set())
            except NotImplementedError:
                # Windows / some envs — fall back to default handlers
                pass

    async def _drain_active_tasks(self) -> None:
        if not self._active_tasks:
            return
        logger.info("supervisor: waiting for %d active spawns", len(self._active_tasks))
        await asyncio.gather(*self._active_tasks, return_exceptions=True)

    def _reload_registry(self) -> None:
        self.registry = load_from_projects_dir(self.config.projects_dir)
        n = len(self.registry)
        enabled = sum(1 for a in self.registry.all_agents() if a.enabled)
        logger.info("registry: loaded %d agents (%d enabled)", n, enabled)

    # ----- Watchdog loop -----

    async def _watchdog_loop(self) -> None:
        """Periodic poll: kill expired runs every 5s."""
        try:
            while not self._shutdown.is_set():
                await asyncio.sleep(5)
                expired = self.watchdog.expired_runs(now=_now_epoch())
                for wr, reason in expired:
                    asyncio.create_task(self._kill_expired_run(wr.run_id, wr.pid, reason))
        except asyncio.CancelledError:
            return

    async def _kill_expired_run(self, run_id: str, pid: int, reason: str) -> None:
        logger.warning("watchdog killing run %s pid=%s reason=%s", run_id, pid, reason)
        from .spawner import BaseAdapter
        try:
            await BaseAdapter().kill(pid)
        except Exception:
            logger.exception("kill failed for run %s", run_id)
        # Update run state on disk
        run = self.state.read_run(run_id)
        if run:
            run.status = (
                RUN_STATUS_TIMEOUT if reason == "timeout" else RUN_STATUS_KILLED
            )
            run.kill_reason = reason
            run.ended_at = _now_iso()
            self.state.write_run(run)
        self.watchdog.remove(run_id)

    # ----- Event handler -----

    async def _handle_event(self, event: TelegramEvent) -> None:
        """Main entrypoint per incoming Telegram event."""
        key = event.dedup_key
        if key in self._seen_events:
            return
        self._seen_events.add(key)

        # Persist observer offset for catchup-after-restart
        self.state.write_observer_offset(event.chat_id, event.message_id)
        # Update cache
        self.cache.append(event)

        # /stop command handling (skip normal mention flow)
        if has_stop_command(event.text):
            await self._handle_stop_command(event)
            return

        # Determine target agents from mentions + reply context
        known_bots = self.registry.known_bot_usernames()
        target_usernames = filter_bot_mentions(list(event.mentions), known_bots)

        # Reply-to-bot's-message implicit ping
        if event.reply_to_message_id and not target_usernames:
            target_usernames = self._resolve_reply_target(event)

        # DM private chat with bot → bot is implicit target
        if not target_usernames and event.is_private:
            spec = self.registry.by_username_or_none_from_chat_id(event.chat_id)
            if spec and spec.bot_username:
                target_usernames = [spec.bot_username]

        if not target_usernames:
            return

        # For each mentioned bot — apply guards + enqueue/spawn
        # Fan-out cap: process up to F=10 in parallel, queue rest.
        spawn_now, queue_later = self.loop_guard.truncate_fan_out(target_usernames)

        # User-level hourly quota check
        if self.loop_guard.quota_exceeded(event.from_.user_id, now=_now_epoch()):
            logger.warning(
                "quota exceeded for user %s — dropping event %s",
                event.from_.user_id, event.message_id,
            )
            return

        for username in spawn_now:
            spec = self.registry.by_username(username)
            if spec is None or not spec.enabled:
                continue
            if not spec.allows_user(event.from_.user_id):
                logger.info("agent %s: user %s not in allowlist — silent drop",
                            spec.slug, event.from_.user_id)
                continue
            # Cooldown check
            if self.loop_guard.in_cooldown(event.chat_id, spec.slug, now=_now_epoch()):
                logger.info("agent %s: cooldown active in chat %s",
                            spec.slug, event.chat_id)
                continue
            # Quota deduct
            self.loop_guard.record_spawn(event.from_.user_id, now=_now_epoch())
            # Schedule spawn — supervisor does NOT await it (parallel)
            task = asyncio.create_task(self._spawn_for_agent(spec, event))
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)

        for username in queue_later:
            spec = self.registry.by_username(username)
            if spec is None or not spec.enabled:
                continue
            self._enqueue(spec, event)

    def _resolve_reply_target(self, event: TelegramEvent) -> list[str]:
        """If event is a reply to one of our bot's messages, return that bot's
        username so it gets spawned as implicit target."""
        if not event.reply_to_message_id:
            return []
        # Walk recent runs to find any with reply_msg_id == reply_to_message_id
        for run in self.state.list_runs():
            if run.reply_msg_id == event.reply_to_message_id:
                spec = self.registry.get(run.agent_slug)
                if spec and spec.bot_username:
                    return [spec.bot_username]
        return []

    async def _handle_stop_command(self, event: TelegramEvent) -> None:
        """Concept Q-impl-8: parse /stop @bot or reply '/stop' on bot's message."""
        targets_usernames = extract_stop_targets(event.text)
        targets_specs: list[AgentSpec] = []
        for u in targets_usernames:
            spec = self.registry.by_username(u)
            if spec:
                targets_specs.append(spec)
        # If no targets but it's a reply — resolve via reply
        if not targets_specs and event.reply_to_message_id:
            reply_targets = self._resolve_reply_target(event)
            for u in reply_targets:
                spec = self.registry.by_username(u)
                if spec:
                    targets_specs.append(spec)
        for spec in targets_specs:
            # Find active run for this agent — there's at most one (per-agent flock)
            for wr in self.watchdog.all_runs():
                if wr.agent_slug == spec.slug:
                    asyncio.create_task(
                        self._kill_expired_run(wr.run_id, wr.pid, "explicit_stop")
                    )
                    logger.info("user %s issued /stop on %s",
                                event.from_.user_id, spec.slug)

    # ----- Spawn coordinator -----

    def _enqueue(self, spec: AgentSpec, event: TelegramEvent) -> None:
        queue = self.state.read_queue(spec.slug)
        if len(queue) >= QUEUE_MAX:
            logger.warning("queue full for %s — rejecting", spec.slug)
            return
        queue.append(QueueEntry.from_event(event))
        self.state.write_queue(spec.slug, queue)

    async def _spawn_for_agent(self, spec: AgentSpec, event: TelegramEvent) -> None:
        """Acquire flock, prepare prompt, run subprocess, send reply.

        If flock busy — enqueue and return; queue worker picks up later.
        """
        lock = AgentLock(self.config.state_root / "watchdog", spec.slug)
        try:
            lock.try_acquire()
        except AgentLockBusy:
            logger.info("agent %s busy — queuing event %s",
                        spec.slug, event.message_id)
            self._enqueue(spec, event)
            return

        bot_token = read_bot_token(spec.bot_token_ref)
        if not bot_token:
            logger.error("no token for agent %s (ref=%s)",
                         spec.slug, spec.bot_token_ref)
            lock.release()
            return

        run_id = _new_run_id()
        run = RunState(
            run_id=run_id,
            agent_slug=spec.slug,
            status=RUN_STATUS_RUNNING,
            source_chat_id=event.chat_id,
            trigger_msg_id=event.message_id,
            trigger_user_id=event.from_.user_id,
            started_at=_now_iso(),
            last_stdout_ts=_now_iso(),
        )
        self.state.write_run(run)

        try:
            # T=0 emoji ack
            asyncio.create_task(self.sender.set_reaction(
                bot_token=bot_token,
                chat_id=event.chat_id,
                message_id=event.message_id,
                emoji="👀",
            ))

            # Build prompt
            recent = self.cache.recent(event.chat_id, limit=15)
            children = self.registry.children_of(spec.slug)
            prompt = assemble_spawn_prompt(
                agent=spec,
                trigger_username=event.from_.username,
                trigger_chat_type=event.chat_type,
                recent_events=recent,
                children=children,
                trigger_text=event.text,
            )

            # Resolve warm-session id: per-(chat_id, agent_slug), latest success run.
            resume_id: str | None = None
            if spec.warm_session:
                latest = None
                for r in self.state.list_runs():
                    if (r.agent_slug == spec.slug
                            and r.source_chat_id == event.chat_id
                            and r.status == RUN_STATUS_SUCCESS
                            and r.claude_session_id):
                        if latest is None or r.started_at > latest.started_at:
                            latest = r
                if latest:
                    resume_id = latest.claude_session_id
                    logger.info("warm-session: agent %s chat %s → resume %s",
                                spec.slug, event.chat_id, resume_id[:8])

            adapter = make_adapter(spec.runtime, resume_session_id=resume_id)

            self.watchdog.add(
                run_id=run_id,
                agent_slug=spec.slug,
                pid=-1,  # set by spawner once subprocess started; we touch via callback
                silence_sec=spec.watchdog_silence_sec,
                hard_timeout_sec=spec.task_timeout_sec,
            )

            def on_chunk(_chunk: str) -> None:
                self.watchdog.touch(run_id, now=_now_epoch())
                lock.touch_activity()

            result = await adapter.spawn(
                run_id=run_id,
                agent_slug=spec.slug,
                workdir=spec.workdir,
                prompt=prompt,
                on_stdout_chunk=on_chunk,
            )

            self.watchdog.remove(run_id)

            # Extract response text
            reply_text = ""
            if result.parsed and isinstance(result.parsed, dict):
                reply_text = (result.parsed.get("result") or "").strip()
            if not reply_text:
                reply_text = result.stdout.strip() or "(no output)"

            # Mention triggering user in final reply (concept §7.9)
            if event.from_.username and not event.is_private:
                reply_text = f"@{event.from_.username} {reply_text}"

            send_result = await self.sender.send_message(
                bot_token=bot_token,
                chat_id=event.chat_id,
                text=reply_text,
                reply_to_message_id=event.message_id,
            )

            # Update run state
            final_status = (
                RUN_STATUS_SUCCESS if result.exit_code == 0 else RUN_STATUS_FAILED
            )
            run.status = final_status
            run.ended_at = _now_iso()
            run.reply_msg_id = send_result.message_id
            run.claude_session_id = (
                result.parsed.get("session_id") if result.parsed else None
            )
            self.state.write_run(run)

            # Mark cooldown
            self.loop_guard.mark_outbound(event.chat_id, spec.slug, now=_now_epoch())

        except SpawnFailed as e:
            logger.error("spawn failed for %s: %s", spec.slug, e)
            run.status = RUN_STATUS_FAILED
            run.ended_at = _now_iso()
            run.kill_reason = f"spawn_failed: {e}"
            self.state.write_run(run)
        except Exception:
            logger.exception("spawn for %s crashed", spec.slug)
            run.status = RUN_STATUS_FAILED
            run.ended_at = _now_iso()
            self.state.write_run(run)
        finally:
            lock.release()
            # Drain one item from queue if present
            asyncio.create_task(self._drain_queue(spec))

    async def _drain_queue(self, spec: AgentSpec) -> None:
        """Pull next entry from agent's queue and spawn if any."""
        queue = self.state.read_queue(spec.slug)
        if not queue:
            return
        entry = queue.pop(0)
        self.state.write_queue(spec.slug, queue)
        # Reconstruct a minimal event from queue entry for spawn
        synthetic = TelegramEvent(
            ts=entry.queued_at,
            chat_id=entry.trigger_chat_id,
            chat_type="group" if entry.trigger_chat_id < 0 else "private",
            message_id=entry.trigger_msg_id,
            from_=type("EF", (), {"user_id": entry.trigger_user_id,
                                  "username": None, "is_bot": False,
                                  "bot_slug": None})(),
            text=entry.trigger_text,
            reply_to_message_id=None,
            message_thread_id=None,
            mentions=(),
        )
        # Note: synthetic.from_ duck-types EventFrom; safe for spawn flow which
        # only reads .user_id and .username.
        await self._spawn_for_agent(spec, synthetic)


def _add_helper_to_registry() -> None:
    """Monkey-patch AgentRegistry with .by_username_or_none_from_chat_id().

    DM chats have chat_id == other user's id. If that id is one of our bots,
    we want to find the AgentSpec.
    """

    def by_username_or_none_from_chat_id(
        self: AgentRegistry, chat_id: int
    ) -> AgentSpec | None:
        for spec in self._by_slug.values():
            if spec.bot_id == chat_id:
                return spec
        return None

    AgentRegistry.by_username_or_none_from_chat_id = by_username_or_none_from_chat_id  # type: ignore[attr-defined]


_add_helper_to_registry()


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    try:
        config = load_config()
    except ValueError as e:
        logger.error("config error: %s", e)
        return 2
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    sup = Supervisor(config)
    await sup.run()
    return 0


__all__ = ["Supervisor", "main"]
