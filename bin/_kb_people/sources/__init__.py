"""Contact source protocol."""


class ContactSource:
    """Base interface for contact ingestion sources. Gmail, Calendar etc. implement this."""

    def get_contacts(self) -> list[dict]:
        """
        Returns list of dicts with keys:
          name, email, context, date (ISO), source_type
        """
        raise NotImplementedError
