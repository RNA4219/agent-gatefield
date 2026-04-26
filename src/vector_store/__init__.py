"""
Vector Store Interface - Multi-backend support for Judgment KB.

Default backend: Qdrant (per RUNBOOK Local Retrieval Stack)
Alternative backends: pgvector, LanceDB, sqlite-vec

This module provides:
- VectorStore: pgvector client for judgment KB (postgres backend)
- QdrantVectorStore: Qdrant client for judgment KB (default)
- JudgmentKB: Judgment Knowledge Base manager
- SearchResult: Search result dataclass
- create_vector_store: Factory function with backend selection
"""

import os
import logging
from typing import Dict, Any, Optional

from .types import SearchResult
from .store import VectorStore
from .kb import JudgmentKB

logger = logging.getLogger(__name__)

# Backend selection constants
BACKEND_QDRANT = "qdrant"
BACKEND_PGVECTOR = "pgvector"
BACKEND_LANCEDB = "lancedb"
BACKEND_SQLITE_VEC = "sqlite_vec"
DEFAULT_BACKEND = BACKEND_QDRANT

__all__ = [
    # Main classes
    'VectorStore',
    'JudgmentKB',
    'SearchResult',
    # Backend constants
    'BACKEND_QDRANT',
    'BACKEND_PGVECTOR',
    'BACKEND_LANCEDB',
    'BACKEND_SQLITE_VEC',
    'DEFAULT_BACKEND',
    # Factory function
    'create_vector_store',
]


def __getattr__(name):
    """Lazy import for psycopg2 exports and Qdrant."""
    if name in ('psycopg2', 'execute_values', 'RealDictCursor', 'PSYCOPG2_AVAILABLE'):
        from ._psycopg2 import psycopg2, execute_values, RealDictCursor, PSYCOPG2_AVAILABLE
        return {
            'psycopg2': psycopg2,
            'execute_values': execute_values,
            'RealDictCursor': RealDictCursor,
            'PSYCOPG2_AVAILABLE': PSYCOPG2_AVAILABLE,
        }.get(name)
    if name == 'QdrantVectorStore':
        from .qdrant_store import QdrantVectorStore
        return QdrantVectorStore
    if name == 'create_qdrant_store':
        from .qdrant_store import create_qdrant_store
        return create_qdrant_store
    raise AttributeError(f"module {__name__} has no attribute {name}")


def create_vector_store(
    connection_string: str = None,
    backend: str = None,
    config: Dict[str, Any] = None
) -> Any:
    """
    Create VectorStore instance with backend selection.

    Args:
        connection_string: PostgreSQL connection string (for pgvector backend).
            If None, uses environment variable DATABASE_URL
        backend: Backend type (qdrant, pgvector).
            If None, uses environment variable VECTOR_STORE_BACKEND or DEFAULT_BACKEND
        config: Configuration dict for backend-specific settings

    Returns:
        VectorStore or QdrantVectorStore instance
    """
    backend = backend or os.environ.get('VECTOR_STORE_BACKEND', DEFAULT_BACKEND)
    config = config or {}

    if backend == BACKEND_QDRANT:
        from .qdrant_store import QdrantVectorStore, create_qdrant_store
        return create_qdrant_store(config)

    if backend == BACKEND_PGVECTOR:
        if connection_string is None:
            connection_string = os.environ.get('DATABASE_URL', 'postgresql://localhost/gatefield')
        return VectorStore(connection_string)

    # Default to Qdrant for unknown backends
    logger.warning(f"Unknown backend '{backend}', falling back to Qdrant")
    from .qdrant_store import QdrantVectorStore, create_qdrant_store
    return create_qdrant_store(config)
