"""Contact source protocol."""


class ContactSource:
    """Base interface for contact ingestion sources. Each source (Calendar,
    Mail, Chat, ...) is a thin adapter over the MCP host — see
    docs/methodology/mcp-first-sources.md for the principle.
    """

    def get_contacts(self) -> list[dict]:
        """Return a list of contact dicts. Common fields:

            name        : str (display name; may be empty)
            email       : str (lowercased, RFC-5322-validated)
            date        : str (ISO YYYY-MM-DD of the observation)
            context     : str (event title, message subject, etc.)
            request_id  : str (provenance — the MCP fetch this came from)

        Implementations may add additional source-specific fields.
        Per-item validation is permissive: malformed items are dropped,
        well-formed rest is returned. See methodology § Strict envelope,
        permissive items.
        """
        raise NotImplementedError
