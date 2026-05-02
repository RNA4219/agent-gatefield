"""
Embedding Worker Package

Local-first semantic embedding generation.

Default stack: BGE-M3 (1024d) via llama.cpp / sentence-transformers.
Fallback: deterministic hash-based (no model required).

Provides backward-compatible imports from embedding_worker.py.
"""

from .constants import (
    DEFAULT_MODEL,
    DEFAULT_DIMENSIONS,
    DEFAULT_RUNTIME,
    FALLBACK_MODEL,
    FALLBACK_DIMENSIONS,
)
from .types import EmbeddingJob, EmbeddingConfig
from .worker import EmbeddingWorker
from .reembed import ReEmbedJob
from .config import create_embedding_worker_from_config


__all__ = [
    # Constants
    "DEFAULT_MODEL",
    "DEFAULT_DIMENSIONS",
    "DEFAULT_RUNTIME",
    "FALLBACK_MODEL",
    "FALLBACK_DIMENSIONS",
    # Types
    "EmbeddingJob",
    "EmbeddingConfig",
    # Classes
    "EmbeddingWorker",
    "ReEmbedJob",
    # Factory
    "create_embedding_worker_from_config",
]