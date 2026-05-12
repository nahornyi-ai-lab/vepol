"""Bot API sender — `sendMessage` and `setMessageReaction` via async HTTP.

Concept §7.9 UX: emoji reaction at T=0, final sendMessage with reply_to + mention.
429 retry with exponential backoff 3 retries (1s/2s/4s).

Why raw HTTP instead of Telethon bot mode? Telethon bot mode requires one
TelegramClient per token (heavyweight). Raw HTTP is one httpx.AsyncClient
shared across N bot tokens — just pass different `/bot<token>/...` URL.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


_BOT_API_BASE = "https://api.telegram.org"
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
_RETRY_DELAYS = (1.0, 2.0, 4.0)  #  exponential backoff


class BotAPIError(Exception):
    """Telegram returned non-OK with non-retryable error."""

    def __init__(self, status: int, body: dict[str, Any] | str):
        self.status = status
        self.body = body
        msg = body.get("description") if isinstance(body, dict) else str(body)
        super().__init__(f"Bot API {status}: {msg}")


@dataclasses.dataclass
class SendResult:
    """Outcome of a sendMessage call. `message_id` is the Telegram-assigned id
    of the new message (needed for run state tracking)."""

    ok: bool
    message_id: int | None
    raw: dict[str, Any]


class BotApiSender:
    """Async sender for Bot API methods.

    Singleton in supervisor. Shared httpx.AsyncClient handles connection pooling
    across all N bot tokens. Methods take bot_token explicitly — sender is
    stateless w.r.t. which bot, supervisor decides.
    """

    def __init__(self, *, timeout: httpx.Timeout = _DEFAULT_TIMEOUT):
        self._client = httpx.AsyncClient(timeout=timeout, base_url=_BOT_API_BASE)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BotApiSender":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    # ----- sendMessage -----

    async def send_message(
        self,
        *,
        bot_token: str,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = True,
    ) -> SendResult:
        """POST /bot<token>/sendMessage with retry on 429/5xx.

        Returns SendResult with message_id on success. Raises BotAPIError on
        non-retryable failures (4xx other than 429 — token issues, chat not
        found, etc.).
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
            # Don't error if reply target was deleted — degrade gracefully.
            payload["allow_sending_without_reply"] = True
        if parse_mode:
            payload["parse_mode"] = parse_mode

        body = await self._post_with_retry(
            f"/bot{bot_token}/sendMessage", payload
        )
        msg = body.get("result", {}) if body.get("ok") else {}
        return SendResult(
            ok=bool(body.get("ok")),
            message_id=msg.get("message_id"),
            raw=body,
        )

    # ----- setMessageReaction (emoji ack) -----

    async def set_reaction(
        self,
        *,
        bot_token: str,
        chat_id: int,
        message_id: int,
        emoji: str = "👀",
        is_big: bool = False,
    ) -> bool:
        """POST /bot<token>/setMessageReaction — concept §7.9 emoji ack at T=0.

        Returns True on success. Soft-fails (returns False, logs warning) on
        any error — emoji ack is best-effort, must not block spawn.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": emoji}],
            "is_big": is_big,
        }
        try:
            body = await self._post_with_retry(
                f"/bot{bot_token}/setMessageReaction", payload
            )
            return bool(body.get("ok"))
        except (BotAPIError, httpx.HTTPError):
            logger.warning(
                "set_reaction failed (best-effort, ignored)", exc_info=True
            )
            return False

    # ----- Internal retry loop -----

    async def _post_with_retry(
        self, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt, delay in enumerate([0.0, *_RETRY_DELAYS]):
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                response = await self._client.post(path, json=payload)
            except httpx.HTTPError as e:
                last_exc = e
                logger.warning(
                    "HTTP error on %s (attempt %d): %s", path, attempt, e
                )
                continue

            # Parse body for retry decision
            try:
                body = response.json()
            except json.JSONDecodeError:
                body = {"raw_text": response.text}

            if response.status_code == 200 and body.get("ok"):
                return body

            # 429 with retry_after or 5xx — retry
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = body.get("parameters", {}).get("retry_after") if isinstance(body, dict) else None
                if retry_after:
                    # Respect Telegram's hint — use bigger of (hint, our backoff)
                    next_delay = max(retry_after, _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
                    await asyncio.sleep(next_delay)
                logger.warning(
                    "Retryable %s on %s (attempt %d): %s",
                    response.status_code, path, attempt, body,
                )
                continue

            # Non-retryable — raise immediately
            raise BotAPIError(response.status_code, body)

        # Exhausted retries
        if last_exc:
            raise last_exc
        raise BotAPIError(0, "all retries exhausted")


__all__ = ["BotApiSender", "BotAPIError", "SendResult"]
