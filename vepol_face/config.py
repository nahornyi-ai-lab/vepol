"""Bind configuration. MVP-7: loopback only, external bind refused."""
from __future__ import annotations

from dataclasses import dataclass, field

LOOPBACK_ALIASES = {
    "127.0.0.1": "127.0.0.1",
    "localhost": "127.0.0.1",
    "::1": "::1",
}


class ExternalBindRefused(ValueError):
    """Raised when a non-loopback bind address is requested."""


def _normalise_host(host: str) -> str:
    if not isinstance(host, str) or not host.strip():
        raise ExternalBindRefused(
            "empty bind host; Vepol Face binds 127.0.0.1 only"
        )
    key = host.strip().lower()
    if key not in LOOPBACK_ALIASES:
        raise ExternalBindRefused(
            f"refusing to bind {host!r}: Vepol Face binds 127.0.0.1 only. "
            "External bind requires a separate security spec."
        )
    return LOOPBACK_ALIASES[key]


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8781
    max_body_bytes: int = 64 * 1024
    allowed_runtimes: tuple[str, ...] = field(default=("claude", "codex"))
    desktop: bool = False

    def __post_init__(self) -> None:
        self.host = _normalise_host(self.host)
        if not (1 <= int(self.port) <= 65535):
            raise ValueError(f"bad port {self.port}")
        self.port = int(self.port)
