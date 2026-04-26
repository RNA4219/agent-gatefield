"""
Tests for vector_store/__init__.py - Factory and lazy imports.
"""

import pytest
import os

from src.vector_store import (
    VectorStore,
    JudgmentKB,
    SearchResult,
    BACKEND_QDRANT,
    BACKEND_PGVECTOR,
    BACKEND_LANCEDB,
    BACKEND_SQLITE_VEC,
    DEFAULT_BACKEND,
)


class TestConstants:
    """Tests for backend constants."""

    def test_backend_constants(self):
        """Backend constants are correct."""
        assert BACKEND_QDRANT == "qdrant"
        assert BACKEND_PGVECTOR == "pgvector"
        assert BACKEND_LANCEDB == "lancedb"
        assert BACKEND_SQLITE_VEC == "sqlite_vec"

    def test_default_backend(self):
        """Default backend is qdrant."""
        assert DEFAULT_BACKEND == "qdrant"


class TestExports:
    """Tests for module exports."""

    def test_vectorstore_export(self):
        """VectorStore is exported."""
        assert VectorStore is not None

    def test_judgmentkb_export(self):
        """JudgmentKB is exported."""
        assert JudgmentKB is not None

    def test_searchresult_export(self):
        """SearchResult is exported."""
        assert SearchResult is not None


class TestLazyImports:
    """Tests for lazy imports via __getattr__."""

    def test_qdrant_vector_store_import(self):
        """QdrantVectorStore lazy import."""
        from src.vector_store import QdrantVectorStore
        assert QdrantVectorStore is not None

    def test_create_qdrant_store_import(self):
        """create_qdrant_store lazy import."""
        from src.vector_store import create_qdrant_store
        assert create_qdrant_store is not None

    def test_psycopg2_import(self):
        """psycopg2 lazy import returns None if not installed."""
        from src.vector_store import PSYCOPG2_AVAILABLE
        # PSYCOPG2_AVAILABLE may be True or False depending on installation
        assert isinstance(PSYCOPG2_AVAILABLE, bool)

    def test_missing_attribute_raises(self):
        """Missing attribute raises AttributeError."""
        import src.vector_store as vs
        with pytest.raises(AttributeError):
            vs.nonexistent_attr


class TestCreateVectorStore:
    """Tests for create_vector_store factory."""

    def test_create_qdrant_default(self):
        """Create with default backend (qdrant)."""
        from src.vector_store import create_vector_store
        store = create_vector_store()
        # Should return QdrantVectorStore instance
        assert store is not None

    def test_create_qdrant_explicit(self):
        """Create with qdrant backend."""
        from src.vector_store import create_vector_store
        store = create_vector_store(backend="qdrant")
        assert store is not None

    def test_create_pgvector(self):
        """Create with pgvector backend (mocked)."""
        from src.vector_store import create_vector_store
        from unittest.mock import patch

        with patch('src.vector_store.store.VectorStore._connect'):
            store = create_vector_store(
                connection_string="postgresql://localhost/test",
                backend="pgvector"
            )
            assert store is not None
            assert store.conn_str == "postgresql://localhost/test"

    def test_create_with_config(self):
        """Create with config dict."""
        from src.vector_store import create_vector_store
        store = create_vector_store(config={'dims': 512})
        assert store is not None

    def test_create_unknown_backend_fallback(self):
        """Unknown backend falls back to qdrant."""
        from src.vector_store import create_vector_store
        store = create_vector_store(backend="unknown")
        # Should still work (fallback to qdrant)
        assert store is not None

    def test_create_with_env_backend(self):
        """Create respects VECTOR_STORE_BACKEND env."""
        from src.vector_store import create_vector_store
        # Temporarily set env
        original = os.environ.get('VECTOR_STORE_BACKEND')
        os.environ['VECTOR_STORE_BACKEND'] = 'qdrant'
        store = create_vector_store()
        os.environ.pop('VECTOR_STORE_BACKEND', None)
        if original:
            os.environ['VECTOR_STORE_BACKEND'] = original
        assert store is not None

    def test_create_pgvector_with_env_url(self):
        """Create pgvector with DATABASE_URL env (mocked)."""
        from src.vector_store import create_vector_store
        from unittest.mock import patch

        original = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = 'postgresql://localhost/test'
        with patch('src.vector_store.store.VectorStore._connect'):
            store = create_vector_store(backend="pgvector")
        os.environ.pop('DATABASE_URL', None)
        if original:
            os.environ['DATABASE_URL'] = original
        assert store is not None


class TestSearchResultIntegration:
    """Integration tests for SearchResult."""

    def test_search_result_from_import(self):
        """SearchResult can be instantiated."""
        result = SearchResult(
            doc_id="doc-1",
            similarity=0.85,
            axis_type="taboo",
            text="test document"
        )
        assert result.doc_id == "doc-1"
        assert result.similarity == 0.85