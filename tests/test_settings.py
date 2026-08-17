from astrag.settings import Settings


def test_env_overrides_nested_chunking(monkeypatch):
    monkeypatch.setenv("ASTRAG_CHUNKING__TARGET_TOKENS", "256")
    s = Settings(_env_file=None)
    assert s.chunking.target_tokens == 256
    assert s.chunking.max_tokens == 800


def test_defaults_are_the_settled_chunking_parameters():
    s = Settings(_env_file=None)
    assert (s.chunking.target_tokens, s.chunking.max_tokens) == (512, 800)
    assert s.chunking.overlap_tokens == 64
    assert s.embedding_dimensions == 1536
