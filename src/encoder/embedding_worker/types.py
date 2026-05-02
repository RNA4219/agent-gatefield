"""
Embedding Worker Types

Dataclasses for embedding jobs and configuration.
"""

from dataclasses import dataclass
from typing import List, Optional

from .constants import DEFAULT_MODEL, DEFAULT_DIMENSIONS, DEFAULT_RUNTIME, FALLBACK_MODEL


@dataclass
class EmbeddingJob:
    """Embedding job data"""
    doc_id: str
    text: str
    model: str
    dims: int
    content_hash: str
    status: str = "pending"  # pending, processing, completed, failed, fallback
    error: Optional[str] = None
    embedding: Optional[List[float]] = None
    fallback_reason: Optional[str] = None


@dataclass
class EmbeddingConfig:
    """Embedding configuration"""
    provider: str = "local"
    runtime: str = DEFAULT_RUNTIME
    model: str = DEFAULT_MODEL
    dims: int = DEFAULT_DIMENSIONS
    fallback_model: str = FALLBACK_MODEL
    api_key: Optional[str] = None
    api_base: str = "https://api.openai.com/v1"
    batch_size: int = 100
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 30.0


__all__ = ["EmbeddingJob", "EmbeddingConfig"]