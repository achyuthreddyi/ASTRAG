"""Content-addressed artifact storage.

Holds the derived blobs that are rebuildable but expensive to recompute — the
NormalizedDocument JSON first. Keys are `sha256[:2]/sha256` of the content, so
writing the same bytes twice is a no-op and a key cannot outlive its content.

One abstract base with a local-filesystem implementation; object storage slots
in at stage 10.
"""

import hashlib
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

_KEY = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{64}$")


class ArtifactStore(ABC):
    @abstractmethod
    def put(self, data: bytes) -> str:
        """Store `data` and return its key."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Return the stored bytes. Raises KeyError if the key is unknown."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the artifact. Best effort: a missing key is not an error."""


class LocalArtifactStore(ArtifactStore):
    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def put(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        key = f"{digest[:2]}/{digest}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Same content-addressed key can be written concurrently by two workers;
        # replace() is atomic so a reader never sees a partial artifact.
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return key

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise KeyError(key) from None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        # Keys reach us from the database, so validate before touching the
        # filesystem rather than trusting the shape.
        if not _KEY.match(key):
            raise ValueError(f"malformed artifact key: {key!r}")
        return self._root / key
