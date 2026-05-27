"""Context-injection scanner v2 — Vepol untrusted-input semantic gate.

Implementation of the approved-with-concerns spec at
`/Users/macbook/vepol-dev/knowledge/decisions/context-injection-scanner-v2.md`.

Public surface:
    from _kb_scanner.scanner import scan, scan_batch
    from _kb_scanner.types import Verdict, ScanRecord, Signature

Stdlib-only. Strictly rule-based. Fail-closed. No bypass paths.

Per autonomy-mode v2.1 § Mode autonomous requirement 8 and security-model v2
Principle 7: this module is a hard gate for any autonomous capability
ingesting non-`runtime-generated` input, and for any hub-writer autonomous
capability regardless of input_origins declaration.
"""

SCANNER_VERSION = "2.0.0"
SCHEMA_VERSION = 2
