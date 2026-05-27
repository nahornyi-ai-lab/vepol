"""Per-input-hash verdict cache (spec PATCH 5).

Composite key: (input_id, catalogue_revision, scanner_version).
Per-verdict TTL:
  clean:   86400  (1 day)
  flagged: 86400  (1 day)
  refused: 14400  (4 hours — anti-DoS asymmetric per OQ-V2-2)

Cache invalidation on catalogue/scanner version bump is *automatic via the
composite key* — no purge step required.

Storage: ~/knowledge/security/scanner-cache/<first-2-hex>/<input_id>.txt
A trivial line-based serialization is used (stdlib, no YAML emit).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .types import Verdict, SignatureHit, VERDICTS, VERDICT_REASONS

CACHE_ROOT = Path(os.path.expanduser("~/knowledge/security/scanner-cache"))

TTL_SECONDS = {
    "clean": 86400,
    "flagged": 86400,
    "refused": 14400,
}


def _cache_path(input_id: str, revision: str, version: str) -> Path:
    composite = f"{input_id}__{revision}__{version}"
    return CACHE_ROOT / input_id[:2] / f"{composite}.txt"


def _serialize(verdict: Verdict, expires_at: float) -> str:
    hits = ";".join(
        f"{h.signature_id}|{h.via_decoder or ''}" for h in verdict.signatures_hit
    )
    return (
        f"verdict={verdict.verdict}\n"
        f"verdict_reason={verdict.verdict_reason}\n"
        f"signatures_hit={hits}\n"
        f"input_id={verdict.input_id}\n"
        f"input_byte_length={verdict.input_byte_length}\n"
        f"input_origin={verdict.input_origin}\n"
        f"scanner_version={verdict.scanner_version}\n"
        f"catalogue_revision={verdict.catalogue_revision}\n"
        f"scanned_at={verdict.scanned_at}\n"
        f"calling_capability_slug={verdict.calling_capability_slug}\n"
        f"decode_budget_exhausted={int(verdict.decode_budget_exhausted)}\n"
        f"expires_at={expires_at:.0f}\n"
    )


def _deserialize(text: str) -> Optional[Verdict]:
    fields = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        fields[k] = v
    try:
        verdict = fields["verdict"]
        reason = fields["verdict_reason"]
        if verdict not in VERDICTS or reason not in VERDICT_REASONS:
            return None
        raw_hits = fields.get("signatures_hit", "")
        hits = []
        if raw_hits:
            for tok in raw_hits.split(";"):
                if not tok:
                    continue
                sid, _, dec = tok.partition("|")
                hits.append(SignatureHit(signature_id=sid, via_decoder=(dec or None)))
        return Verdict(
            verdict=verdict,
            verdict_reason=reason,
            signatures_hit=hits,
            input_id=fields["input_id"],
            input_byte_length=int(fields["input_byte_length"]),
            input_origin=fields["input_origin"],
            scanner_version=fields["scanner_version"],
            catalogue_revision=fields["catalogue_revision"],
            scanned_at=fields["scanned_at"],
            calling_capability_slug=fields["calling_capability_slug"],
            cache_status="hit",
            decode_budget_exhausted=bool(int(fields.get("decode_budget_exhausted", "0"))),
        )
    except (KeyError, ValueError):
        return None


@dataclass
class VerdictCache:
    """Composite-key cache with per-verdict TTL. Disk-backed; in-memory
    optional layer keeps batch hot path fast.

    Pass `disk_root=None` to disable disk persistence (useful in tests).
    """

    in_memory: dict = None
    disk_root: Optional[Path] = CACHE_ROOT

    def __post_init__(self):
        if self.in_memory is None:
            self.in_memory = {}

    def _disk_path(self, input_id: str, revision: str, version: str) -> Optional[Path]:
        if self.disk_root is None:
            return None
        composite = f"{input_id}__{revision}__{version}"
        return self.disk_root / input_id[:2] / f"{composite}.txt"

    def _key(self, input_id: str, revision: str, version: str) -> str:
        return f"{input_id}|{revision}|{version}"

    def lookup(self, input_id: str, revision: str, version: str) -> Optional[Verdict]:
        now = time.time()
        # In-memory first
        key = self._key(input_id, revision, version)
        entry = self.in_memory.get(key)
        if entry is not None:
            verdict, expires_at = entry
            if expires_at > now:
                # Copy to mark as hit
                verdict.cache_status = "hit"
                return verdict
            else:
                self.in_memory.pop(key, None)
        # Disk fallback
        path = self._disk_path(input_id, revision, version)
        if path is None or not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        verdict = _deserialize(text)
        if verdict is None:
            return None
        # Extract expires_at from text directly
        expires_at = None
        for line in text.splitlines():
            if line.startswith("expires_at="):
                try:
                    expires_at = float(line.partition("=")[2])
                except ValueError:
                    pass
                break
        if expires_at is None or expires_at <= now:
            # Stale — best-effort cleanup
            try:
                path.unlink()
            except OSError:
                pass
            return None
        # Populate in-memory for future calls
        self.in_memory[key] = (verdict, expires_at)
        return verdict

    def store(self, verdict: Verdict) -> None:
        ttl = TTL_SECONDS.get(verdict.verdict)
        if ttl is None:
            return
        expires_at = time.time() + ttl
        key = self._key(verdict.input_id, verdict.catalogue_revision, verdict.scanner_version)
        # Store a copy with cache_status=miss so subsequent reads can re-mark hit
        snapshot = Verdict(**{**verdict.__dict__})
        snapshot.cache_status = "miss"
        self.in_memory[key] = (snapshot, expires_at)
        # Disk write — atomic via tmp + rename
        path = self._disk_path(verdict.input_id, verdict.catalogue_revision, verdict.scanner_version)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(_serialize(snapshot, expires_at), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            # Disk failure does not break the scanner; in-memory cache still serves.
            pass
