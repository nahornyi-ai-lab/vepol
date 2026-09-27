"""Money as integer cents plus a currency code. Floats never touch an amount."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal


@dataclass(frozen=True)
class Money:
    cents: int
    currency: str

    @classmethod
    def parse(cls, amount: str, currency: str) -> "Money":
        """Convert an API string like "19.99" at the edge; never accept a float."""
        cents = (Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
        return cls(int(cents), currency)

    def split(self, parts: int) -> list["Money"]:
        """Split without losing a cent: the first shares absorb the remainder."""
        base, extra = divmod(self.cents, parts)
        return [Money(base + (1 if i < extra else 0), self.currency) for i in range(parts)]
