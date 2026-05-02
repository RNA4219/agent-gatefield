"""
Embedding Worker - local-first semantic embedding generation.

Default stack: BGE-M3 (1024d) via llama.cpp / sentence-transformers.
Fallback: deterministic hash-based (no model required).
"""

import hashlib
import logging
import math
import os
import re
from typing import Dict, List, Any
import asyncio
import aiohttp

from .constants import DEFAULT_MODEL, DEFAULT_DIMENSIONS, DEFAULT_RUNTIME, FALLBACK_MODEL
from .types import EmbeddingJob
from ..utils import generate_mock_embedding
from ..runtime import (
    RuntimeConfig,
    RuntimeStatus,
    RuntimeType,
    create_adapter_from_config,
)

logger = logging.getLogger(__name__)


class EmbeddingWorker:
    """
    Worker for generating embeddings.

    Supports:
    - local (default): BGE-M3 via llama.cpp / sentence-transformers
    - fallback: deterministic hash-based (no model, testing/fallback)
    - openai: OpenAI-compatible embeddings API (optional alternative)
    - mock: deterministic test vectors
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        dims: int = DEFAULT_DIMENSIONS,
        provider: str = None,
        runtime: str = None,
        api_key: str = None,
        api_base: str = None
    ):
        self.provider = (provider or os.environ.get("EMBEDDING_PROVIDER", "local")).lower()
        self.runtime = (runtime or os.environ.get("EMBEDDING_RUNTIME", DEFAULT_RUNTIME)).lower()
        self.model = model
        self.dims = dims
        self.jobs: List[EmbeddingJob] = []

        # Runtime adapter for local embeddings
        self._runtime_adapter = None
        self._init_runtime_adapter()

        # Optional external API configuration.
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.api_base = api_base or os.environ.get(
            "OPENAI_API_BASE",
            "https://api.openai.com/v1"
        )

        # Validate model/dims combination
        self._validate_model_dims()

    def _init_runtime_adapter(self) -> None:
        """Initialize runtime adapter for local embeddings."""
        if self.provider != "local":
            return

        config_dict = {
            "runtime": self.runtime,
            "host": os.environ.get("LLAMA_CPP_HOST", "localhost"),
            "port": int(os.environ.get("LLAMA_CPP_PORT", "8080")),
            "model": self.model,
            "dimensions": self.dims,
            "timeout": float(os.environ.get("EMBEDDING_TIMEOUT", "30.0")),
        }
        self._runtime_adapter = create_adapter_from_config(config_dict)

    def _validate_model_dims(self) -> None:
        """Validate model and dimensions combination"""
        valid_combinations = {
            DEFAULT_MODEL: [1024],  # BGE-M3 dense
            FALLBACK_MODEL: [384, 768, 1536, 3072],
            "text-embedding-3-large": [1536, 3072],
            "text-embedding-3-small": [512, 1536],
            "text-embedding-ada-002": [1536],
        }

        if self.model in valid_combinations:
            if self.dims not in valid_combinations[self.model]:
                logger.warning(
                    f"dims={self.dims} may not be optimal for model={self.model}. "
                    f"Valid dims: {valid_combinations[self.model]}"
                )

    def compute_hash(self, text: str) -> str:
        """Compute SHA256 content hash for deduplication"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def create_job(self, doc_id: str, text: str) -> EmbeddingJob:
        """Create embedding job"""
        content_hash = self.compute_hash(text)
        return EmbeddingJob(
            doc_id=doc_id,
            text=text,
            model=self.model,
            dims=self.dims,
            content_hash=content_hash,
            status="pending"
        )

    def is_api_available(self) -> bool:
        """Check if the configured embedding provider is usable."""
        if self.provider in ("local", "mock"):
            return True
        return bool(self.api_key)

    def uses_external_api(self) -> bool:
        """Return whether embeddings require a network API call."""
        return self.provider in ("openai", "openai-compatible", "openai_compatible")

    def _get_headers(self) -> Dict[str, str]:
        """Get API headers"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def process_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text string

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector)
        """
        result = self._process_texts([text])
        return result["vectors"][0] if result["vectors"] else self._fallback_embedding(text)[0]

    def process_text_with_status(self, text: str) -> Dict[str, Any]:
        """
        Generate embedding with full status info.

        Args:
            text: Text to embed

        Returns:
            Dict with vector, model, dims, status, reason
        """
        result = self._process_texts([text])
        if result["vectors"]:
            return {
                "vector": result["vectors"][0],
                "model": result["model"],
                "dims": result["dims"],
                "status": result["status"],
                "reason": result.get("reason"),
                "provider": result.get("provider"),
                "runtime": result.get("runtime"),
            }
        else:
            # Fallback
            fallback_result = self._fallback_embedding(text)
            return {
                "vector": fallback_result[0],
                "model": FALLBACK_MODEL,
                "dims": self.dims,
                "status": "fallback",
                "reason": result.get("reason", "Primary embedding failed"),
                "provider": "local",
                "runtime": "fallback",
            }

    def _process_mock(self, texts: List[str]) -> Dict[str, Any]:
        """Process texts with mock provider."""
        return {
            "vectors": [self._mock_embedding() for _ in texts],
            "model": "mock",
            "dims": self.dims,
            "status": "success",
            "provider": "local",
            "runtime": "mock",
        }

    def _process_local(self, texts: List[str]) -> Dict[str, Any]:
        """Process texts with local runtime adapter with fallback chain."""
        if self._runtime_adapter:
            result = self._runtime_adapter.embed(texts)
            if result.status == RuntimeStatus.SUCCESS:
                return {
                    "vectors": result.vectors,
                    "model": result.model,
                    "dims": result.dimensions,
                    "status": "success",
                    "provider": result.provider,
                    "runtime": result.runtime,
                }
            if result.status == RuntimeStatus.FALLBACK:
                return {
                    "vectors": result.vectors,
                    "model": result.model,
                    "dims": result.dimensions,
                    "status": "fallback",
                    "reason": result.reason,
                    "provider": result.provider,
                    "runtime": result.runtime,
                }

            # llama.cpp unavailable - try sentence_transformers as fallback
            if self.runtime in ("llama.cpp", "llama_cpp"):
                logger.info("llama.cpp unavailable, trying sentence_transformers...")
                st_result = self._try_sentence_transformers(texts)
                if st_result["status"] == "success":
                    return st_result
                logger.warning(f"sentence_transformers also failed: {st_result.get('reason')}")

            logger.warning(f"Runtime adapter unavailable: {result.reason}")
        else:
            # No adapter - try sentence_transformers directly
            st_result = self._try_sentence_transformers(texts)
            if st_result["status"] == "success":
                return st_result

        return self._fallback_result(texts, "All runtime adapters failed")

    def _try_sentence_transformers(self, texts: List[str]) -> Dict[str, Any]:
        """Try sentence_transformers adapter as fallback."""
        from ..runtime import SentenceTransformersAdapter

        config = RuntimeConfig(
            runtime_type=RuntimeType.SENTENCE_TRANSFORMERS,
            model=self.model,
            dimensions=self.dims,
        )
        adapter = SentenceTransformersAdapter(config)

        if adapter.is_available():
            result = adapter.embed(texts)
            if result.status == RuntimeStatus.SUCCESS:
                return {
                    "vectors": result.vectors,
                    "model": result.model,
                    "dims": result.dimensions,
                    "status": "success",
                    "provider": result.provider,
                    "runtime": result.runtime,
                }
            return {
                "vectors": [],
                "model": result.model,
                "dims": result.dimensions,
                "status": "fallback",
                "reason": result.reason,
                "provider": result.provider,
                "runtime": result.runtime,
            }
        return self._fallback_result(texts, "sentence_transformers unavailable")

    def _process_api(self, texts: List[str]) -> Dict[str, Any]:
        """Process texts with external API."""
        if not self.is_api_available():
            logger.warning("Embedding API key not configured, returning fallback")
            return self._fallback_result(texts, "API key not configured", "external", "api")

        embeddings = self._call_embedding_api(texts)
        if embeddings:
            return {
                "vectors": embeddings,
                "model": self.model,
                "dims": self.dims,
                "status": "success",
                "provider": "openai",
                "runtime": "api",
            }
        return self._fallback_result(texts, "API call failed", "external", "api")

    def _fallback_result(self, texts: List[str], reason: str,
                         provider: str = "local", runtime: str = "fallback") -> Dict[str, Any]:
        """Generate fallback result dict."""
        return {
            "vectors": self._fallback_embedding_bulk(texts),
            "model": FALLBACK_MODEL,
            "dims": self.dims,
            "status": "fallback",
            "reason": reason,
            "provider": provider,
            "runtime": runtime,
        }

    def _process_texts(self, texts: List[str]) -> Dict[str, Any]:
        """Process texts with runtime adapter or API."""
        PROVIDER_HANDLERS = {
            "mock": self._process_mock,
            "local": self._process_local,
        }
        handler = PROVIDER_HANDLERS.get(self.provider, self._process_api)
        return handler(texts)

    def _call_embedding_api(self, texts: List[str]) -> List[List[float]]:
        """
        Call OpenAI embedding API

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        import requests

        url = f"{self.api_base}/embeddings"
        payload = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dims
        }

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                return []

            data = response.json()
            embeddings = []

            # Sort by index to maintain order
            sorted_data = sorted(data.get('data', []), key=lambda x: x.get('index', 0))
            for item in sorted_data:
                embeddings.append(item.get('embedding', []))

            logger.info(f"Generated {len(embeddings)} embeddings with model={self.model}")
            return embeddings

        except requests.exceptions.Timeout:
            logger.error("Embedding API timeout")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Embedding API request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Embedding API unexpected error: {e}")
            return []

    async def _call_embedding_api_async(
        self,
        texts: List[str],
        session: aiohttp.ClientSession
    ) -> List[List[float]]:
        """
        Async version of embedding API call

        Args:
            texts: List of texts to embed
            session: aiohttp session

        Returns:
            List of embedding vectors
        """
        url = f"{self.api_base}/embeddings"
        payload = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dims
        }

        try:
            async with session.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"Async embedding API error: {response.status} - {text}")
                    return []

                data = await response.json()
                embeddings = []
                sorted_data = sorted(data.get('data', []), key=lambda x: x.get('index', 0))
                for item in sorted_data:
                    embeddings.append(item.get('embedding', []))

                return embeddings

        except asyncio.TimeoutError:
            logger.error("Async embedding API timeout")
            return []
        except Exception as e:
            logger.error(f"Async embedding API error: {e}")
            return []

    def process_job(self, job: EmbeddingJob) -> List[float]:
        """
        Process single embedding job

        Args:
            job: EmbeddingJob to process

        Returns:
            Embedding vector
        """
        job.status = "processing"

        try:
            result = self.process_text_with_status(job.text)
            job.embedding = result["vector"]
            job.status = result["status"]
            job.fallback_reason = result.get("reason")
            return result["vector"]
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            logger.error(f"Job {job.doc_id} failed: {e}")
            return self._mock_embedding()

    def batch_process(
        self,
        jobs: List[EmbeddingJob],
        batch_size: int = 100
    ) -> Dict[str, List[float]]:
        """
        Process multiple jobs in batches

        Args:
            jobs: List of EmbeddingJobs
            batch_size: Number of texts per API call (OpenAI limit is 2048)

        Returns:
            Dict mapping doc_id to embedding
        """
        results = {}

        # Process all texts through _process_texts
        texts = [job.text for job in jobs]
        batch_result = self._process_texts(texts)

        if batch_result["vectors"]:
            # All processed successfully
            status = batch_result["status"]
            for i, job in enumerate(jobs):
                if i < len(batch_result["vectors"]):
                    job.embedding = batch_result["vectors"][i]
                    job.status = status
                    job.fallback_reason = batch_result.get("reason")
                    results[job.doc_id] = job.embedding
        else:
            # Fallback for each job
            for job in jobs:
                job.embedding = self._fallback_embedding(job.text)
                job.status = "fallback"
                job.fallback_reason = "Batch processing failed"
                results[job.doc_id] = job.embedding

        return results

    async def batch_process_async(
        self,
        jobs: List[EmbeddingJob],
        batch_size: int = 100
    ) -> Dict[str, List[float]]:
        """
        Async batch processing for better throughput

        Args:
            jobs: List of EmbeddingJobs
            batch_size: Number of texts per API call

        Returns:
            Dict mapping doc_id to embedding
        """
        results = {}

        # For local provider, use synchronous _process_texts (no async needed for local)
        if self.provider in ("local", "mock"):
            texts = [job.text for job in jobs]
            batch_result = self._process_texts(texts)
            for i, job in enumerate(jobs):
                if i < len(batch_result["vectors"]):
                    job.embedding = batch_result["vectors"][i]
                    job.status = batch_result["status"]
                    job.fallback_reason = batch_result.get("reason")
                    results[job.doc_id] = job.embedding
            return results

        if not self.is_api_available():
            for job in jobs:
                job.embedding = self._fallback_embedding(job.text)
                job.status = "fallback"
                job.fallback_reason = "API not available"
                results[job.doc_id] = job.embedding
            return results

        texts_by_job = [(job.doc_id, job.text) for job in jobs]
        batches = []

        for i in range(0, len(texts_by_job), batch_size):
            batches.append(texts_by_job[i:i + batch_size])

        async with aiohttp.ClientSession() as session:
            tasks = []
            for batch in batches:
                texts = [j[1] for j in batch]
                task = self._call_embedding_api_async(texts, session)
                tasks.append((batch, task))

            # Execute all batches concurrently
            for batch, task in tasks:
                embeddings = await task
                doc_ids = [j[0] for j in batch]

                for j, doc_id in enumerate(doc_ids):
                    if j < len(embeddings):
                        results[doc_id] = embeddings[j]
                        for job in jobs:
                            if job.doc_id == doc_id:
                                job.embedding = embeddings[j]
                                job.status = "success"
                    else:
                        source_text = next((job.text for job in jobs if job.doc_id == doc_id), "")
                        results[doc_id] = self._fallback_embedding(source_text)
                        for job in jobs:
                            if job.doc_id == doc_id:
                                job.status = "fallback"
                                job.fallback_reason = "Missing embedding in async response"

        return results

    def _fallback_embedding(self, text: str) -> List[float]:
        """
        Generate a deterministic hash-based fallback embedding.

        NOTE: This is NOT semantically meaningful. Only for testing/fallback.
        """
        return self._fallback_embedding_bulk([text])[0]

    def _fallback_embedding_bulk(self, texts: List[str]) -> List[List[float]]:
        """
        Generate deterministic hash-based fallback embeddings for multiple texts.

        NOTE: These are NOT semantically meaningful. Only for testing/fallback.
        """
        vectors = []
        for text in texts:
            vector = [0.0] * self.dims
            normalized = str(text or "").lower()
            tokens = re.findall(r"\w+|[^\s\w]", normalized, flags=re.UNICODE)
            if not tokens:
                tokens = [normalized]

            for position, token in enumerate(tokens):
                digest = hashlib.sha256(f"{FALLBACK_MODEL}:{position}:{token}".encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dims
                sign = 1.0 if digest[4] & 1 else -1.0
                weight = 1.0 + min(len(token), 32) / 32.0
                vector[index] += sign * weight

            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                vectors.append(vector)
            else:
                vectors.append([value / norm for value in vector])

        return vectors

    def _mock_embedding(self) -> List[float]:
        """Generate mock embedding for testing without API"""
        return generate_mock_embedding(self.dims, distribution="uniform")

    def re_embed_all(
        self,
        axis_type: str,
        new_model: str,
        new_dims: int,
        vector_store: 'VectorStore' = None
    ) -> Dict:
        """
        Re-embed all documents for an axis with new model

        Dual-write period: keep both old and new embeddings

        Args:
            axis_type: Axis to re-embed (constitution, taboo, accepted, rejected)
            new_model: New embedding model
            new_dims: New dimensions
            vector_store: VectorStore instance for persistence

        Returns:
            Dict with status and counts
        """
        if not vector_store:
            logger.warning("No vector_store provided, re-embed will not persist")
            return {"status": "skipped", "reason": "no_vector_store"}

        # Get all active embeddings
        old_embeddings = vector_store.get_active_embeddings(axis_type)

        if not old_embeddings:
            return {"status": "skipped", "reason": "no_documents"}

        logger.info(
            f"Re-embedding {len(old_embeddings)} documents for axis={axis_type} "
            f"with model={new_model}, dims={new_dims}"
        )

        # Create temporary worker with new model
        new_worker = EmbeddingWorker(model=new_model, dims=new_dims, provider=self.provider)

        # Create jobs
        jobs = []
        for emb_data in old_embeddings:
            doc_id = emb_data.get('doc_id')
            text = emb_data.get('text', '')
            if text:
                jobs.append(new_worker.create_job(doc_id, text))

        # Process
        results = new_worker.batch_process(jobs)

        # Persist new embeddings (dual-write)
        persisted = 0
        for doc_id, embedding in results.items():
            if embedding and len(embedding) == new_dims:
                content_hash = new_worker.compute_hash(
                    next((e.get('text') for e in old_embeddings if e.get('doc_id') == doc_id), '')
                )
                try:
                    vector_store.insert_embedding(
                        doc_id=doc_id,
                        model=new_model,
                        dims=new_dims,
                        embedding=embedding,
                        content_hash=content_hash
                    )
                    persisted += 1
                except Exception as e:
                    logger.error(f"Failed to persist embedding for {doc_id}: {e}")

        return {
            "status": "completed",
            "total_documents": len(old_embeddings),
            "processed": len(results),
            "persisted": persisted,
            "new_model": new_model,
            "new_dims": new_dims
        }


__all__ = ["EmbeddingWorker"]