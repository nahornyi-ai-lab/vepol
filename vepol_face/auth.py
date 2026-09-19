"""Local auth boundary. MVP-8.

Per-launch token held in process memory only, rotated on every restart,
never written to disk. Origin checks are default-deny.
"""
from __future__ import annotations

import hmac
import secrets


class Auth:
    def __init__(self, port: int = 8781) -> None:
        self.port = int(port)
        # 32 bytes -> 43-char urlsafe string. Memory only: nothing writes it out.
        self._token = secrets.token_urlsafe(32)

    @property
    def token(self) -> str:
        return self._token

    def verify(self, presented: str | None) -> bool:
        if not isinstance(presented, str) or not presented:
            return False
        return hmac.compare_digest(presented, self._token)

    def allowed_origins(self) -> set[str]:
        return {
            f"http://127.0.0.1:{self.port}",
            f"http://localhost:{self.port}",
            f"http://[::1]:{self.port}",
        }

    def origin_allowed(self, origin: str | None) -> bool:
        if not isinstance(origin, str) or not origin:
            return False
        return origin in self.allowed_origins()
