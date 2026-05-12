"""Telethon listener — push events.NewMessage for группа + operator's DMs.

Concept §5: persistent connection, 1 long-lived TelegramClient. Receives
events realtime via push (no polling), normalizes to our TelegramEvent, hands
to a callback.

Phase 1: Telethon user-account sees the operator↔bot DMs natively (his account
is one side of the conversation). Phase 2 will add Bot API getUpdates per token
when third-party DMs become relevant.

/13: startup catchup via iter_messages from last_seen_msg_id.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Awaitable, Callable

from telethon import TelegramClient, events
from telethon.tl.custom import Message as TelethonMessage
from telethon.tl.types import PeerUser, PeerChannel, PeerChat

from .events import EventFrom, TelegramEvent
from .mention import extract_mentions


logger = logging.getLogger(__name__)


EventCallback = Callable[[TelegramEvent], Awaitable[None]]


class GroupListener:
    """Wraps Telethon client + events.NewMessage handler for <your_group> group.

    Single connection, registered for the configured group_chat_id + all
    private chats involving the operator. On each new message:
      1. Normalize Telethon Message → our TelegramEvent
      2. Dispatch to async callback (supervisor's handler)

    Catchup on startup: read missed messages from last_seen_msg_id to current,
    deliver in order before going live on push events. Single time MTProto
    `iter_messages` call per chat — rate-safe.
    """

    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        session_file: str,
        group_chat_id: int,
        on_event: EventCallback,
    ):
        self._client = TelegramClient(
            session_file,
            api_id=api_id,
            api_hash=api_hash,
            # Hint Telethon we're a long-lived listener; auto-reconnect is on by default
        )
        self._group_chat_id = group_chat_id
        self._on_event = on_event
        # Mapping of our bot user_ids → slugs, set by supervisor after registry load.
        self._bot_id_to_slug: dict[int, str] = {}
        self._running = False

    def set_bot_id_mapping(self, mapping: dict[int, str]) -> None:
        """Supervisor registers known bot user_ids so listener can stamp bot_slug.

        bot_id (numeric Telegram user_id of bot) → agent_slug. From registry.
        """
        self._bot_id_to_slug = dict(mapping)

    async def start(self, *, catchup_offsets: dict[int, int] | None = None) -> None:
        """Connect, perform catchup if requested, register handler, run.

        `catchup_offsets`: per-chat last_seen_msg_id. After connect, fetch
        messages newer than offset for each chat, deliver to callback before
        registering the live handler.
        """
        await self._client.start()  # interactive prompt if session invalid
        logger.info("listener: connected to Telegram as user-account")

        if catchup_offsets:
            await self._catchup(catchup_offsets)

        # Register live handler — fires on every new message in chats the operator is in
        @self._client.on(events.NewMessage())
        async def _handler(event):
            try:
                te = self._normalize(event.message)
                if te is None:
                    return
                # Filter: только группа + operator's private chats with bots
                if not self._is_relevant(te):
                    return
                await self._on_event(te)
            except Exception:
                logger.exception("listener handler crashed (continuing)")

        self._running = True
        logger.info("listener: live event handler registered")

    async def run_forever(self) -> None:
        """Block on the Telethon event loop. Returns only on supervisor shutdown."""
        await self._client.run_until_disconnected()

    async def stop(self) -> None:
        self._running = False
        await self._client.disconnect()
        logger.info("listener: disconnected")

    async def _catchup(self, offsets: dict[int, int]) -> int:
        """Fetch messages newer than offset[chat_id] per concept §7.4 catchup.

        /13: backwindow limit 1h — older messages dropped with warning.

        Returns total messages delivered.
        """
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
        delivered = 0
        for chat_id, last_seen in offsets.items():
            try:
                # iter_messages newest-first; we collect newer than last_seen
                batch: list[TelethonMessage] = []
                async for msg in self._client.iter_messages(chat_id, min_id=last_seen):
                    if msg.date and msg.date < cutoff:
                        logger.warning(
                            "catchup: dropping msg %s in chat %s (older than 1h)",
                            msg.id, chat_id,
                        )
                        continue
                    batch.append(msg)
                # Reverse to deliver oldest-first
                for msg in reversed(batch):
                    te = self._normalize(msg)
                    if te is None or not self._is_relevant(te):
                        continue
                    try:
                        await self._on_event(te)
                        delivered += 1
                    except Exception:
                        logger.exception("catchup callback crashed (continuing)")
            except Exception:
                logger.exception("catchup failed for chat %s (continuing)", chat_id)
        logger.info("listener: catchup delivered %d messages", delivered)
        return delivered

    def _is_relevant(self, event: TelegramEvent) -> bool:
        """Phase 1: deliver only group `<your_group>` events + operator's bot DMs.

        Bot DMs are private chats where the OTHER party is one of our known bots
        (i.e., chat_id < 0 is group; chat_id > 0 is a user — and if that user
        is in our bot_id_to_slug, it's a DM with one of our bots).
        """
        if event.chat_id == self._group_chat_id:
            return True
        if event.is_private:
            # The chat_id of a private chat equals the OTHER user's id; if that
            # other user is one of our bots, supervisor cares.
            if event.chat_id in self._bot_id_to_slug:
                return True
        return False

    def _normalize(self, msg: TelethonMessage) -> TelegramEvent | None:
        """Telethon Message → our TelegramEvent. Returns None on un-normalizable."""
        if msg is None or msg.id is None:
            return None
        text = msg.message or ""
        if not isinstance(text, str):
            text = str(text)

        chat_id = self._extract_chat_id(msg)
        chat_type = self._extract_chat_type(msg)

        sender = msg.sender
        from_user_id = msg.sender_id if msg.sender_id is not None else 0
        username = getattr(sender, "username", None) if sender else None
        is_bot = bool(getattr(sender, "bot", False)) if sender else False
        bot_slug = self._bot_id_to_slug.get(from_user_id) if is_bot else None

        ts = (msg.date or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)

        return TelegramEvent(
            ts=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            chat_id=chat_id,
            chat_type=chat_type,
            message_id=msg.id,
            from_=EventFrom(
                user_id=from_user_id,
                username=username,
                is_bot=is_bot,
                bot_slug=bot_slug,
            ),
            text=text,
            reply_to_message_id=msg.reply_to_msg_id if msg.is_reply else None,
            message_thread_id=None,  # forum topics — Phase 2
            mentions=tuple(extract_mentions(text)),
            raw_event_offset_id=msg.id,
        )

    @staticmethod
    def _extract_chat_id(msg: TelethonMessage) -> int:
        peer = msg.peer_id
        if isinstance(peer, PeerChannel):
            # Group/channel chat_ids in Bot API form are negative with 100-prefix
            return -1000000000000 - peer.channel_id
        if isinstance(peer, PeerChat):
            return -peer.chat_id
        if isinstance(peer, PeerUser):
            return peer.user_id
        # Fallback — Telethon's chat_id property handles peer types
        return msg.chat_id or 0

    @staticmethod
    def _extract_chat_type(msg: TelethonMessage) -> str:
        peer = msg.peer_id
        if isinstance(peer, (PeerChannel, PeerChat)):
            return "group"
        if isinstance(peer, PeerUser):
            return "private"
        return "group"  # safe default


__all__ = ["GroupListener", "EventCallback"]
