"""Dense embedding generation (§14).

Two implementations behind one contract: the real provider, and a deterministic
hash-based fake that makes tests and the Stage 7 evaluation harness offline,
free and reproducible. The fake is not a mock — it is selected by configuration
and runs the same code path the provider does.

Batching, per-chunk skip-on-retry and generation identity live in the stage that
calls this; an embedder only turns texts into vectors.
"""

import hashlib
import math
from abc import ABC, abstractmethod
from functools import lru_cache

from astrag.models.representation import DIMENSIONS
from astrag.settings import get_settings


class EmbeddingError(Exception):
    """The provider did not return usable vectors. Retryable: the same text may
    well embed fine once the provider is healthy again."""


class Embedder(ABC):
    model: str
    dimensions: int = DIMENSIONS

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per input, in input order."""

    def _checked(self, vectors: list[list[float]], texts: list[str]) -> list[list[float]]:
        if len(vectors) != len(texts) or any(len(v) != self.dimensions for v in vectors):
            raise EmbeddingError(
                f"{self.model} returned {len(vectors)} vectors for {len(texts)} texts"
            )
        return vectors


class FakeEmbedder(Embedder):
    """Deterministic pseudo-embeddings derived from the text itself.

    Same text always gives the same unit vector and different texts give
    different ones, which is all an ingestion or plumbing test can assert. It
    carries no semantics, so relevance quality is never measured against it.
    """

    model = "fake-deterministic"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._checked([self._vector(text) for text in texts], texts)

    def _vector(self, text: str) -> list[float]:
        raw = bytearray()
        seed = text.encode()
        # SHA-256 in counter mode: cheap, stable across processes and versions,
        # and unlike hash() it is not salted per interpreter run.
        while len(raw) < self.dimensions * 2:
            seed = hashlib.sha256(seed).digest()
            raw += seed
        values = [
            int.from_bytes(raw[i : i + 2], "big") / 65535 - 0.5
            for i in range(0, self.dimensions * 2, 2)
        ]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]


class OpenAIEmbedder(Embedder):
    def __init__(self, model: str, api_key: str | None, dimensions: int) -> None:
        from openai import OpenAI

        self.model = model
        self.dimensions = dimensions
        self._client = OpenAI(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(
                model=self.model, input=texts, dimensions=self.dimensions
            )
        except Exception as error:  # noqa: BLE001 — provider taxonomy is not ours
            raise EmbeddingError(f"{self.model}: {error}") from error
        # Sorted by index because the API does not promise input order.
        vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        return self._checked(vectors, texts)


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_dimensions != DIMENSIONS:
        # The vector column width is DDL: a mismatch would fail on insert, one
        # upload later, with a far less obvious message than this one.
        raise EmbeddingError(
            f"configured dimensions {settings.embedding_dimensions} do not match the "
            f"chunk_representations column width {DIMENSIONS}"
        )
    if settings.embedding_provider == "fake":
        return FakeEmbedder()
    return OpenAIEmbedder(
        settings.embedding_model, settings.openai_api_key, settings.embedding_dimensions
    )
