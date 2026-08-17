"""Process configuration. Read from the environment, prefix ASTRAG_."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChunkingConfig(BaseModel):
    """One object so stage 7 can sweep these as a unit.

    These are tunable configuration validated by evaluation, not architectural
    constants. Every field belongs to the ProcessingGeneration config.
    """

    target_tokens: int = 512
    max_tokens: int = 800
    # Applied only when a single structural unit exceeds max_tokens.
    overlap_tokens: int = 64
    tokenizer: str = "cl100k_base"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASTRAG_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://astrag:astrag@localhost:5433/astrag"

    artifact_store_root: Path = Path("var/artifacts")
    # Cheap synchronous upload validation (§18): reject before hashing.
    max_upload_bytes: int = 10 * 1024 * 1024

    # "fake" is deterministic and offline: tests and evaluation runs use it.
    embedding_provider: Literal["openai", "fake"] = "fake"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    openai_api_key: str | None = None

    chunking: ChunkingConfig = ChunkingConfig()


@lru_cache
def get_settings() -> Settings:
    return Settings()
