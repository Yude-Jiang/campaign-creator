"""Campaign storage interface.

Campaign state is a single JSON blob per campaign plus a handful of uploaded
diagnosis files — object-shaped, not relational. The interface below is the
smallest thing that supports that shape *and* safe concurrent writes.

Concurrency is compare-and-swap, not locking. The previous implementation used
a `threading.Lock` held across a read-modify-write cycle, which only serialises
writers inside one process: with more than one Cloud Run instance (or more than
one uvicorn worker) two requests could read the same state and the second write
would silently discard the first. Every read here returns a version token, and
every write states the version it expects to replace. A mismatch raises
StorageConflict instead of clobbering.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class StorageError(Exception):
    """Base class for storage failures."""


class CampaignNotFound(StorageError):
    """The requested campaign does not exist."""


class StorageConflict(StorageError):
    """Another writer modified the campaign since it was read.

    The caller read version A, someone else committed version B, and this write
    would have thrown B away. Surfaces to the client as HTTP 409 so the work is
    re-done against current state rather than lost.
    """


@dataclass(frozen=True)
class Loaded:
    """A campaign document plus the version token needed to write it back."""

    data: dict
    version: str | None
    """Opaque, backend-specific. `None` means "expect no existing object"."""


class CampaignStore(ABC):
    """Persistence for campaign documents and their uploaded files."""

    @abstractmethod
    def read(self, campaign_id: str) -> Loaded | None:
        """Return the campaign and its version, or None if it does not exist."""

    @abstractmethod
    def write(self, campaign_id: str, data: dict, expected_version: str | None) -> str:
        """Write the campaign, but only if its stored version still matches.

        Pass `expected_version=None` to require that the campaign does not yet
        exist. Returns the new version token.

        Raises StorageConflict if the stored version has moved on.
        """

    @abstractmethod
    def delete(self, campaign_id: str) -> None:
        """Remove a campaign and everything under it. Missing is not an error."""

    @abstractmethod
    def list(self) -> list[dict]:
        """Return `{campaign_id, name, updated_at}` for every campaign."""

    @abstractmethod
    def write_diagnosis(self, campaign_id: str, filename: str, content: bytes) -> str:
        """Store an uploaded diagnosis file. Returns the stored filename."""

    @abstractmethod
    def read_diagnosis(self, campaign_id: str, filename: str) -> str | None:
        """Return a diagnosis file's text, or None if absent."""

    @abstractmethod
    def list_diagnoses(self, campaign_id: str) -> list[str]:
        """Return the filenames stored under this campaign's diagnoses."""

    def describe(self) -> str:
        """Human-readable backend identity, for startup logging."""
        return type(self).__name__
