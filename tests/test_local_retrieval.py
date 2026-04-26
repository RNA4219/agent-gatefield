"""
Tests for Local Retrieval Stack - BGE-M3 + Qdrant.

Tests cover:
- LocalEmbedder (BGE-M3 embedding)
- Reranker (bge-reranker-v2-m3)
- QdrantVectorStore
- QdrantJudgmentKB
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys

# Test imports (skip if dependencies unavailable)
try:
    from src.encoder.local_embedder import LocalEmbedder, Reranker, create_local_embedder
    HAS_LOCAL_EMBEDDER = True
except ImportError:
    HAS_LOCAL_EMBEDDER = False

try:
    from src.vector_store.qdrant_store import QdrantVectorStore, SearchResult, create_qdrant_store
    HAS_QDRANT_STORE = True
except ImportError:
    HAS_QDRANT_STORE = False

try:
    from src.vector_store.qdrant_kb import QdrantJudgmentKB, create_qdrant_kb
    HAS_QDRANT_KB = True
except ImportError:
    HAS_QDRANT_KB = False


# ============================================================================
# LocalEmbedder Tests
# ============================================================================

@pytest.mark.skipif(not HAS_LOCAL_EMBEDDER, reason="LocalEmbedder dependencies unavailable")
class TestLocalEmbedder:
    """Tests for LocalEmbedder."""

    def test_initialization_defaults(self):
        """Default configuration."""
        embedder = LocalEmbedder()
        assert embedder.model_name == "BAAI/bge-m3"
        assert embedder.dimensions == 1024
        assert embedder.use_fallback == False

    def test_initialization_custom(self):
        """Custom configuration."""
        embedder = LocalEmbedder(
            model_name="custom-model",
            dimensions=512,
            device="cpu"
        )
        assert embedder.model_name == "custom-model"
        assert embedder.dimensions == 512
        assert embedder.device == "cpu"

    def test_fallback_mode(self):
        """Fallback mode uses hash embedding."""
        embedder = LocalEmbedder(use_fallback=True, dimensions=1536)
        assert embedder.use_fallback == True

        # Generate fallback embedding
        texts = ["test text", "another text"]
        embeddings = embedder.embed(texts)

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 1536  # Fallback uses specified dims
        # Deterministic: same text = same embedding
        assert embeddings[0] == embedder.embed([texts[0]])[0]

    def test_hash_embed_deterministic(self):
        """Hash embedding is deterministic."""
        embedder = LocalEmbedder(use_fallback=True)

        text = "deterministic test"
        emb1 = embedder.embed_single(text)
        emb2 = embedder.embed_single(text)

        assert emb1 == emb2

    def test_hash_embed_different_texts(self):
        """Different texts produce different embeddings."""
        embedder = LocalEmbedder(use_fallback=True)

        emb1 = embedder.embed_single("text one")
        emb2 = embedder.embed_single("text two")

        assert emb1 != emb2

    def test_get_model_info(self):
        """Model info returns configuration."""
        embedder = LocalEmbedder(device="cpu")
        info = embedder.get_model_info()

        assert info['model'] == "BAAI/bge-m3"
        assert info['dimensions'] == 1024
        assert info['device'] == "cpu"
        assert info['provider'] == "local"

    def test_empty_text_list(self):
        """Empty input returns empty output."""
        embedder = LocalEmbedder(use_fallback=True)
        embeddings = embedder.embed([])
        assert embeddings == []

    def test_create_local_embedder_factory(self):
        """Factory function creates embedder."""
        embedder = create_local_embedder({
            'dimensions': 512,
            'device': 'cpu'
        })
        assert embedder.dimensions == 512
        assert embedder.device == 'cpu'


# ============================================================================
# Reranker Tests
# ============================================================================

@pytest.mark.skipif(not HAS_LOCAL_EMBEDDER, reason="Reranker dependencies unavailable")
class TestReranker:
    """Tests for Reranker."""

    def test_initialization_defaults(self):
        """Default configuration."""
        reranker = Reranker()
        assert reranker.model_name == "BAAI/bge-reranker-v2-m3"
        assert reranker.enabled == True

    def test_disabled_reranker(self):
        """Disabled reranker returns input unchanged."""
        reranker = Reranker(enabled=False)

        candidates = [
            {'doc_id': '1', 'text': 'doc1', 'similarity': 0.9},
            {'doc_id': '2', 'text': 'doc2', 'similarity': 0.8},
        ]
        results = reranker.rerank("query", candidates, top_k=10)

        assert results == candidates
        assert len(results) == 2

    def test_empty_candidates(self):
        """Empty candidates returns empty."""
        reranker = Reranker(enabled=False)
        results = reranker.rerank("query", [], top_k=10)
        assert results == []

    def test_get_info(self):
        """Info returns configuration."""
        reranker = Reranker(enabled=True, device="cpu")
        info = reranker.get_info()

        assert info['model'] == "BAAI/bge-reranker-v2-m3"
        assert info['enabled'] == True
        assert info['device'] == "cpu"


# ============================================================================
# QdrantVectorStore Tests
# ============================================================================

@pytest.mark.skipif(not HAS_QDRANT_STORE, reason="Qdrant dependencies unavailable")
class TestQdrantVectorStore:
    """Tests for QdrantVectorStore."""

    def test_initialization_defaults(self):
        """Default configuration."""
        store = QdrantVectorStore()
        assert store.collection_name == "gatefield_judgments"
        assert store.embedding_dims == 1024
        assert store.distance == "Cosine"

    def test_initialization_custom(self):
        """Custom configuration."""
        store = QdrantVectorStore(
            collection_name="custom_collection",
            embedding_dims=512,
            distance="Euclidean"
        )
        assert store.collection_name == "custom_collection"
        assert store.embedding_dims == 512
        assert store.distance == "Euclidean"

    def test_initialization_in_memory(self):
        """In-memory mode."""
        store = QdrantVectorStore(in_memory=True)
        assert store.location == ":memory:"
        assert store.host is None

    def test_mock_search_when_unavailable(self):
        """Mock search when Qdrant unavailable."""
        store = QdrantVectorStore(in_memory=True)
        # Don't initialize client
        store._initialized = True
        store._client = None

        results = store.search_similar([0.1] * 1024, "taboo", limit=5)

        assert len(results) == 5
        assert results[0].axis_type == "taboo"
        assert results[0].doc_id.startswith("mock-")

    def test_mock_insert_when_unavailable(self):
        """Mock insert when Qdrant unavailable."""
        store = QdrantVectorStore(in_memory=True)
        store._initialized = True
        store._client = None

        doc_id = store.insert_document(
            axis_type="taboo",
            text="test",
            embedding=[0.1] * 1024
        )

        assert doc_id.startswith("mock-doc-")

    def test_mock_centroid_when_unavailable(self):
        """Mock centroid when Qdrant unavailable."""
        store = QdrantVectorStore(in_memory=True)
        store._initialized = True
        store._client = None

        centroid = store.get_centroid("taboo")

        assert len(centroid) == 1024
        assert all(v == 0.5 for v in centroid)

    def test_search_result_dataclass(self):
        """SearchResult creation."""
        result = SearchResult(
            doc_id="doc-123",
            similarity=0.85,
            axis_type="taboo",
            text="test text",
            labels={"key": "value"},
            source_type="manual"
        )
        assert result.doc_id == "doc-123"
        assert result.similarity == 0.85
        assert result.axis_type == "taboo"
        assert result.text == "test text"
        assert result.labels == {"key": "value"}

    def test_search_result_with_reranker_score(self):
        """SearchResult with reranker score."""
        result = SearchResult(
            doc_id="doc-123",
            similarity=0.85,
            axis_type="taboo",
            text="test",
            reranker_score=0.92
        )
        assert result.reranker_score == 0.92

    def test_create_qdrant_store_factory(self):
        """Factory function creates store."""
        store = create_qdrant_store({
            'collection': 'test_collection',
            'dims': 512,
            'in_memory': True
        })
        assert store.collection_name == 'test_collection'
        assert store.embedding_dims == 512


# ============================================================================
# QdrantJudgmentKB Tests
# ============================================================================

@pytest.mark.skipif(not HAS_QDRANT_KB, reason="QdrantJudgmentKB dependencies unavailable")
class TestQdrantJudgmentKB:
    """Tests for QdrantJudgmentKB."""

    def test_initialization(self):
        """Default initialization."""
        kb = QdrantJudgmentKB()
        assert kb.top_k_input == 50
        assert kb.top_k_output == 10

    def test_initialization_with_config(self):
        """Initialization with config."""
        kb = QdrantJudgmentKB(config={
            'dimensions': 512,
            'reranker_enabled': False,
            'top_k_input': 100,
            'top_k_output': 20,
        })
        assert kb.embedder.dimensions == 512
        assert kb.reranker.enabled == False
        assert kb.top_k_input == 100
        assert kb.top_k_output == 20

    def test_get_model_info(self):
        """Model info returns all component info."""
        kb = QdrantJudgmentKB()
        info = kb.get_model_info()

        assert 'embedding' in info
        assert 'reranker' in info
        assert 'vector_store' in info
        assert 'top_k' in info

    def test_search_axis_methods(self):
        """Axis-specific search methods."""
        kb = QdrantJudgmentKB()
        kb.embedder.use_fallback = True
        kb.embedder._initialized = True
        kb.vector_store._initialized = True
        kb.vector_store._client = None

        # Mock search (fallback mode)
        taboo_results = kb.get_taboo_topk("test query")
        assert taboo_results[0].axis_type == "taboo"

    def test_create_qdrant_kb_factory(self):
        """Factory function creates KB."""
        kb = create_qdrant_kb({
            'dimensions': 512,
            'in_memory': True
        })
        assert kb.embedder.dimensions == 512


# ============================================================================
# Integration Tests (with real components when available)
# ============================================================================

class TestLocalRetrievalStackIntegration:
    """Integration tests for local retrieval stack."""

    @pytest.mark.skipif(not HAS_LOCAL_EMBEDDER, reason="Dependencies unavailable")
    def test_fallback_embedding_pipeline(self):
        """Complete pipeline with fallback embedding."""
        # Create KB with fallback
        kb = QdrantJudgmentKB(config={
            'dimensions': 1536,  # Fallback dims
            'reranker_enabled': False,
            'in_memory': True,
        })

        # Force fallback mode
        kb.embedder.use_fallback = True
        kb.embedder.dimensions = 1536
        kb.embedder._initialized = True

        # Mock vector store
        kb.vector_store._initialized = True
        kb.vector_store._client = None
        kb.vector_store.embedding_dims = 1536

        # Search
        results = kb.search("test query", "taboo", limit=5)

        assert len(results) > 0
        assert results[0].axis_type == "taboo"

    @pytest.mark.skipif(not HAS_LOCAL_EMBEDDER, reason="Dependencies unavailable")
    def test_model_info_complete(self):
        """Complete model info for monitoring."""
        kb = QdrantJudgmentKB(config={
            'in_memory': True,
        })
        info = kb.get_model_info()

        # Check structure
        assert info['embedding']['provider'] == 'local'
        assert info['top_k']['input'] == 50
        assert info['top_k']['output'] == 10


# ============================================================================
# Coverage Summary
# ============================================================================

def test_coverage_summary():
    """Coverage summary marker."""
    # This test just marks coverage requirements are defined
    assert True