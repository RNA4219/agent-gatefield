"""
Tests for QdrantVectorStore - additional coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.vector_store.qdrant_store import (
    QdrantVectorStore,
    SearchResult,
    create_qdrant_store,
    DEFAULT_COLLECTION,
    DEFAULT_DIMS,
    DEFAULT_DISTANCE,
)


class TestQdrantConstants:
    """Tests for constants."""

    def test_default_collection(self):
        """Default collection name."""
        assert DEFAULT_COLLECTION == "gatefield_judgments"

    def test_default_dims(self):
        """Default embedding dimensions."""
        assert DEFAULT_DIMS == 1024

    def test_default_distance(self):
        """Default distance metric."""
        assert DEFAULT_DISTANCE == "Cosine"


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result_creation(self):
        """SearchResult basic creation."""
        result = SearchResult(
            doc_id="doc-1",
            similarity=0.85,
            axis_type="taboo",
            text="test document"
        )
        assert result.doc_id == "doc-1"
        assert result.similarity == 0.85
        assert result.axis_type == "taboo"

    def test_search_result_with_optional_fields(self):
        """SearchResult with optional fields."""
        result = SearchResult(
            doc_id="doc-1",
            similarity=0.85,
            axis_type="taboo",
            text="test",
            labels={"severity": "high"},
            source_type="import",
            scope="global",
            version=1,
            reranker_score=0.90
        )
        assert result.labels == {"severity": "high"}
        assert result.reranker_score == 0.90


class TestQdrantVectorStoreInit:
    """Tests for QdrantVectorStore initialization."""

    def test_default_init(self):
        """Default initialization."""
        store = QdrantVectorStore()
        assert store.collection_name == DEFAULT_COLLECTION
        assert store.embedding_dims == DEFAULT_DIMS
        assert store.distance == DEFAULT_DISTANCE
        assert store._client is None
        assert store._initialized is False

    def test_custom_init(self):
        """Custom initialization."""
        store = QdrantVectorStore(
            collection_name="custom_collection",
            embedding_dims=512,
            distance="Euclidean"
        )
        assert store.collection_name == "custom_collection"
        assert store.embedding_dims == 512
        assert store.distance == "Euclidean"

    def test_in_memory_init(self):
        """In-memory mode initialization."""
        store = QdrantVectorStore(in_memory=True)
        assert store.in_memory is True
        assert store.location == ":memory:"
        assert store.host is None
        assert store.port is None

    def test_url_init(self):
        """URL-based initialization."""
        store = QdrantVectorStore(url="http://qdrant.example.com:6333")
        assert store.url == "http://qdrant.example.com:6333"
        assert store.host is None
        assert store.port is None

    def test_host_port_init(self):
        """Host/port initialization."""
        store = QdrantVectorStore(host="localhost", port=6334)
        assert store.host == "localhost"
        assert store.port == 6334


class TestQdrantVectorStoreMockMode:
    """Tests for mock mode when Qdrant unavailable."""

    def test_mock_search(self):
        """Mock search returns mock results."""
        store = QdrantVectorStore(in_memory=True)
        results = store._mock_search("taboo", 5)
        assert len(results) == 5
        assert all(r.axis_type == "taboo" for r in results)

    def test_mock_search_similarity_order(self):
        """Mock search results have decreasing similarity."""
        store = QdrantVectorStore(in_memory=True)
        results = store._mock_search("taboo", 3)
        assert results[0].similarity > results[1].similarity
        assert results[1].similarity > results[2].similarity

    def test_search_without_client_returns_mock(self):
        """Search without client returns mock."""
        store = QdrantVectorStore()
        # Force initialized but no client
        store._initialized = True
        store._client = None

        results = store.search_similar([0.1] * 1024, "taboo")
        assert len(results) > 0
        assert all(r.doc_id.startswith("mock-") for r in results)

    def test_insert_without_client_returns_mock_id(self):
        """Insert without client returns mock doc_id."""
        store = QdrantVectorStore()
        store._initialized = True
        store._client = None

        doc_id = store.insert_document("taboo", "test", [0.1] * 1024)
        assert doc_id.startswith("mock-doc-")

    def test_batch_insert_without_client(self):
        """Batch insert without client returns mock IDs."""
        store = QdrantVectorStore()
        store._initialized = True
        store._client = None

        docs = [{"axis_type": "taboo", "text": "test1"}]
        embeddings = [[0.1] * 1024]
        doc_ids = store.batch_insert(docs, embeddings)
        assert len(doc_ids) == 1
        assert doc_ids[0].startswith("mock-doc-")

    def test_deprecate_without_client(self):
        """Deprecate without client returns True."""
        store = QdrantVectorStore()
        store._initialized = True
        store._client = None

        result = store.deprecate_document("doc-1")
        assert result is True

    def test_get_centroid_without_client(self):
        """Get centroid without client returns mock."""
        store = QdrantVectorStore()
        store._initialized = True
        store._client = None

        centroid = store.get_centroid("taboo")
        assert centroid is not None
        assert len(centroid) == DEFAULT_DIMS

    def test_get_collection_info_without_client(self):
        """Get collection info without client returns mock."""
        store = QdrantVectorStore()
        store._initialized = True
        store._client = None

        info = store.get_collection_info()
        assert info['status'] == 'mock'
        assert info['points_count'] == 0


class TestCreateQdrantStore:
    """Tests for create_qdrant_store function."""

    def test_create_from_empty_config(self):
        """Create from empty config."""
        store = create_qdrant_store({})
        assert store.collection_name == DEFAULT_COLLECTION
        assert store.embedding_dims == DEFAULT_DIMS

    def test_create_from_config(self):
        """Create from config dict."""
        store = create_qdrant_store({
            'collection': 'custom',
            'dims': 512,
            'host': 'localhost',
            'port': 6334,
            'in_memory': True
        })
        assert store.collection_name == 'custom'
        assert store.embedding_dims == 512

    def test_create_with_dimensions_alias(self):
        """Create with dimensions alias."""
        store = create_qdrant_store({'dimensions': 768})
        assert store.embedding_dims == 768

    def test_create_with_collection_name(self):
        """Create with collection_name key."""
        store = create_qdrant_store({'collection_name': 'my_collection'})
        assert store.collection_name == 'my_collection'


class TestQdrantVectorStoreClose:
    """Tests for close method."""

    def test_close_with_client(self):
        """Close with client."""
        store = QdrantVectorStore(in_memory=True)
        mock_client = Mock()
        mock_client.close.return_value = None
        store._client = mock_client

        store.close()
        mock_client.close.assert_called_once()
        assert store._client is None

    def test_close_without_client(self):
        """Close without client."""
        store = QdrantVectorStore()
        store._client = None
        store.close()
        assert store._client is None


class TestQdrantVectorStoreErrorHandling:
    """Tests for error handling."""

    def test_search_error_returns_empty(self):
        """Search error returns empty list."""
        store = QdrantVectorStore(in_memory=True)
        mock_client = Mock()
        mock_client.search.side_effect = Exception("Search failed")

        store._client = mock_client
        store._initialized = True

        results = store.search_similar([0.1] * 1024, "taboo")
        assert results == []

    def test_insert_error_returns_mock(self):
        """Insert error returns mock doc_id."""
        store = QdrantVectorStore(in_memory=True)
        mock_client = Mock()
        mock_client.upsert.side_effect = Exception("Insert failed")

        store._client = mock_client
        store._initialized = True

        doc_id = store.insert_document("taboo", "test", [0.1] * 1024)
        assert doc_id.startswith("mock-doc-")

    def test_batch_insert_error_returns_mock(self):
        """Batch insert error returns mock IDs."""
        store = QdrantVectorStore(in_memory=True)
        mock_client = Mock()
        mock_client.upsert.side_effect = Exception("Batch failed")

        store._client = mock_client
        store._initialized = True

        docs = [{"axis_type": "taboo", "text": "test"}]
        embeddings = [[0.1] * 1024]
        doc_ids = store.batch_insert(docs, embeddings)
        assert doc_ids[0].startswith("mock-doc-")

    def test_centroid_error_returns_none(self):
        """Get centroid error returns None."""
        store = QdrantVectorStore(in_memory=True)
        mock_client = Mock()
        mock_client.scroll.side_effect = Exception("Scroll failed")

        store._client = mock_client
        store._initialized = True

        centroid = store.get_centroid("taboo")
        assert centroid is None

    def test_collection_info_error(self):
        """Collection info error returns error dict."""
        store = QdrantVectorStore(in_memory=True)
        mock_client = Mock()
        mock_client.get_collection.side_effect = Exception("Info failed")

        store._client = mock_client
        store._initialized = True

        info = store.get_collection_info()
        assert info['status'] == 'error'
        assert 'error' in info