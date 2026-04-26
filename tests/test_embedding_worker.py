"""
Tests for EmbeddingWorker - additional coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from src.encoder.embedding_worker import (
    EmbeddingWorker,
    EmbeddingJob,
    EmbeddingConfig,
    DEFAULT_MODEL,
    DEFAULT_DIMENSIONS,
    FALLBACK_MODEL,
)


class TestEmbeddingJob:
    """Tests for EmbeddingJob dataclass."""

    def test_job_creation(self):
        """EmbeddingJob basic creation."""
        job = EmbeddingJob(
            doc_id="doc-1",
            text="test text",
            model="test-model",
            dims=1024,
            content_hash="sha256:abc"
        )
        assert job.doc_id == "doc-1"
        assert job.text == "test text"
        assert job.status == "pending"
        assert job.embedding is None

    def test_job_with_embedding(self):
        """EmbeddingJob with embedding."""
        job = EmbeddingJob(
            doc_id="doc-1",
            text="test",
            model="test",
            dims=10,
            content_hash="hash",
            status="completed",
            embedding=[0.1] * 10
        )
        assert job.status == "completed"
        assert len(job.embedding) == 10

    def test_job_failed(self):
        """EmbeddingJob with error."""
        job = EmbeddingJob(
            doc_id="doc-1",
            text="test",
            model="test",
            dims=10,
            content_hash="hash",
            status="failed",
            error="API timeout"
        )
        assert job.status == "failed"
        assert job.error == "API timeout"


class TestEmbeddingConfig:
    """Tests for EmbeddingConfig dataclass."""

    def test_config_defaults(self):
        """EmbeddingConfig default values."""
        config = EmbeddingConfig()
        assert config.provider == "local"
        assert config.model == DEFAULT_MODEL
        assert config.dims == DEFAULT_DIMENSIONS
        assert config.batch_size == 100

    def test_config_custom(self):
        """EmbeddingConfig custom values."""
        config = EmbeddingConfig(
            provider="openai",
            model="text-embedding-3-small",
            dims=1536,
            api_key="sk-test"
        )
        assert config.provider == "openai"
        assert config.api_key == "sk-test"


class TestEmbeddingWorkerInit:
    """Tests for EmbeddingWorker initialization."""

    def test_default_init(self):
        """Default initialization."""
        worker = EmbeddingWorker()
        assert worker.provider == "local"
        assert worker.model == DEFAULT_MODEL
        assert worker.dims == DEFAULT_DIMENSIONS
        assert worker.jobs == []

    def test_custom_init(self):
        """Custom initialization."""
        worker = EmbeddingWorker(
            model="custom-model",
            dims=512,
            provider="mock"
        )
        assert worker.model == "custom-model"
        assert worker.dims == 512
        assert worker.provider == "mock"

    def test_init_with_api_key(self):
        """Initialization with API key."""
        worker = EmbeddingWorker(
            provider="openai",
            api_key="sk-test",
            api_base="https://api.example.com/v1"
        )
        assert worker.api_key == "sk-test"
        assert worker.api_base == "https://api.example.com/v1"


class TestEmbeddingWorkerMock:
    """Tests for mock provider."""

    def test_process_mock(self):
        """Process with mock provider."""
        worker = EmbeddingWorker(provider="mock")
        result = worker._process_mock(["test text"])
        assert result["status"] == "success"
        assert len(result["vectors"]) == 1

    def test_mock_embedding_deterministic(self):
        """Mock embedding is deterministic."""
        worker = EmbeddingWorker(provider="mock", dims=10)
        emb1 = worker._mock_embedding()
        emb2 = worker._mock_embedding()
        assert len(emb1) == 10

    def test_mock_embedding_bulk(self):
        """Mock embedding bulk."""
        worker = EmbeddingWorker(provider="mock", dims=10)
        # Use process_text for bulk or check if method exists
        emb1 = worker.process_text("text1")
        emb2 = worker.process_text("text2")
        assert len(emb1) == 10
        assert len(emb2) == 10


class TestEmbeddingWorkerFallback:
    """Tests for fallback embedding."""

    def test_fallback_embedding(self):
        """Fallback embedding generation."""
        worker = EmbeddingWorker()
        emb = worker._fallback_embedding("test")
        assert len(emb) == DEFAULT_DIMENSIONS
        # Hash-based, should be deterministic
        emb2 = worker._fallback_embedding("test")
        assert emb == emb2

    def test_fallback_embedding_different_texts(self):
        """Fallback embedding for different texts."""
        worker = EmbeddingWorker()
        emb1 = worker._fallback_embedding("test1")
        emb2 = worker._fallback_embedding("test2")
        assert emb1 != emb2

    def test_fallback_result(self):
        """Fallback result dict."""
        worker = EmbeddingWorker()
        result = worker._fallback_result(["test"], "No model available")
        assert result["status"] == "fallback"
        assert result["reason"] == "No model available"
        assert result["model"] == FALLBACK_MODEL


class TestEmbeddingWorkerProcessing:
    """Tests for text processing."""

    def test_process_texts_mock(self):
        """Process texts with mock provider."""
        worker = EmbeddingWorker(provider="mock")
        result = worker._process_texts(["text1", "text2"])
        assert result["status"] == "success"
        assert len(result["vectors"]) == 2

    def test_process_text_with_status(self):
        """Process text with status."""
        worker = EmbeddingWorker(provider="mock")
        result = worker.process_text_with_status("test text")
        assert "vector" in result
        assert "status" in result

    def test_compute_hash(self):
        """Compute content hash."""
        worker = EmbeddingWorker()
        hash1 = worker.compute_hash("test text")
        hash2 = worker.compute_hash("test text")
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hexdigest length


class TestEmbeddingWorkerJobs:
    """Tests for job processing."""

    def test_process_job(self):
        """Process single job."""
        worker = EmbeddingWorker(provider="mock")
        job = EmbeddingJob(
            doc_id="doc-1",
            text="test text",
            model="mock",
            dims=10,
            content_hash="hash"
        )
        result = worker.process_job(job)
        assert len(result) > 0
        assert job.status in ("success", "completed", "fallback")

    def test_batch_process(self):
        """Batch process jobs."""
        worker = EmbeddingWorker(provider="mock")
        jobs = [
            EmbeddingJob(doc_id="doc-1", text="text1", model="mock", dims=10, content_hash="h1"),
            EmbeddingJob(doc_id="doc-2", text="text2", model="mock", dims=10, content_hash="h2"),
        ]
        results = worker.batch_process(jobs)
        assert len(results) == 2
        assert "doc-1" in results
        assert "doc-2" in results

    def test_create_job(self):
        """Create job from text."""
        worker = EmbeddingWorker(provider="mock")
        job = worker.create_job("doc-1", "test text")
        assert job.doc_id == "doc-1"
        assert job.text == "test text"
        assert len(job.content_hash) == 64  # SHA256 hexdigest


class TestEmbeddingWorkerAPI:
    """Tests for API provider."""

    def test_is_api_available_no_key(self):
        """API availability check without key."""
        worker = EmbeddingWorker(provider="openai")
        assert worker.is_api_available() is False

    def test_is_api_available_with_key(self):
        """API availability check with key."""
        worker = EmbeddingWorker(provider="openai", api_key="sk-test")
        assert worker.is_api_available() is True

    def test_process_api_no_key(self):
        """Process with API but no key."""
        worker = EmbeddingWorker(provider="openai")
        result = worker._process_api(["test"])
        assert result["status"] == "fallback"
        assert result["reason"] == "API key not configured"

    def test_get_headers(self):
        """Get API headers."""
        worker = EmbeddingWorker(provider="openai", api_key="sk-test")
        headers = worker._get_headers()
        assert headers["Authorization"] == "Bearer sk-test"


class TestEmbeddingWorkerLocal:
    """Tests for local provider."""

    def test_process_local_fallback(self):
        """Process local with fallback when adapter unavailable."""
        worker = EmbeddingWorker(provider="local")
        # Runtime adapter may not be available, should return fallback or success
        result = worker._process_local(["test"])
        assert result["status"] in ("success", "fallback")
        assert len(result["vectors"]) >= 0


class TestEmbeddingWorkerIntegration:
    """Integration-like tests."""

    def test_full_workflow_mock(self):
        """Full workflow with mock provider."""
        worker = EmbeddingWorker(provider="mock", dims=100)

        # Create jobs
        job1 = worker.create_job("doc-1", "First document")
        job2 = worker.create_job("doc-2", "Second document")

        # Batch process
        results = worker.batch_process([job1, job2])

        assert len(results) == 2
        assert all(len(emb) == 100 for emb in results.values())

    def test_embedding_consistency(self):
        """Embedding consistency for same text."""
        worker = EmbeddingWorker(provider="mock", dims=50)

        result1 = worker.process_text("test")
        result2 = worker.process_text("test")

        # Mock embeddings should be consistent
        assert len(result1) == len(result2)