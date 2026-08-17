import hashlib

import pytest

from astrag.storage.artifacts import LocalArtifactStore


@pytest.fixture
def store(tmp_path):
    return LocalArtifactStore(tmp_path)


def test_put_is_content_addressed_and_roundtrips(store):
    key = store.put(b"normalized document")

    digest = hashlib.sha256(b"normalized document").hexdigest()
    assert key == f"{digest[:2]}/{digest}"
    assert store.get(key) == b"normalized document"


def test_put_is_idempotent_for_identical_bytes(store):
    assert store.put(b"same") == store.put(b"same")


def test_get_of_unknown_key_raises(store):
    with pytest.raises(KeyError):
        store.get("ab/" + "0" * 64)


def test_delete_is_best_effort(store):
    key = store.put(b"gone")
    store.delete(key)
    store.delete(key)  # orphan cleanup runs after commit; absence is not an error
    with pytest.raises(KeyError):
        store.get(key)


@pytest.mark.parametrize("key", ["../etc/passwd", "ab/../../etc/passwd", "abc", ""])
def test_malformed_keys_are_rejected(store, key):
    with pytest.raises(ValueError):
        store.get(key)
