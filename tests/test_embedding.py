"""The embedder contract, and the fake that makes tests and evaluation offline."""

import pytest

from astrag.ingest.embedding import (
    EmbeddingError,
    FakeEmbedder,
    OpenAIEmbedder,
    get_embedder,
)
from astrag.models.representation import DIMENSIONS


def test_the_fake_is_deterministic_across_calls():
    """Stage 7 replays evaluations: the same text must embed the same way."""
    first, second = FakeEmbedder().embed(["a chunk"]), FakeEmbedder().embed(["a chunk"])

    assert first == second
    assert len(first[0]) == DIMENSIONS


def test_different_texts_embed_differently():
    one, two = FakeEmbedder().embed(["the Republic", "the Empire"])

    assert one != two


def test_the_fake_returns_unit_vectors():
    """Cosine distance is what the HNSW index is built for."""
    (vector,) = FakeEmbedder().embed(["the Republic was founded in 509 BCE"])

    assert sum(v * v for v in vector) == pytest.approx(1.0)


def test_input_order_is_preserved():
    texts = ["one", "two", "three"]

    vectors = FakeEmbedder().embed(texts)

    assert vectors == [FakeEmbedder().embed([text])[0] for text in texts]


def test_a_short_provider_response_is_an_embedding_error():
    """A silently missing vector would publish a chunk with no representation."""

    class Truncating(FakeEmbedder):
        def embed(self, texts):
            return self._checked([[0.0] * DIMENSIONS], texts)

    with pytest.raises(EmbeddingError, match="1 vectors for 2 texts"):
        Truncating().embed(["one", "two"])


def test_a_provider_failure_is_wrapped(monkeypatch):
    embedder = FakeEmbedder.__new__(OpenAIEmbedder)
    embedder.model, embedder.dimensions = "text-embedding-3-small", DIMENSIONS

    class Exploding:
        embeddings = property(lambda self: self)

        def create(self, **_):
            raise RuntimeError("provider is down")

    embedder._client = Exploding()

    with pytest.raises(EmbeddingError, match="provider is down"):
        embedder.embed(["one"])


def test_the_configured_provider_is_the_fake_by_default():
    assert isinstance(get_embedder(), FakeEmbedder)
