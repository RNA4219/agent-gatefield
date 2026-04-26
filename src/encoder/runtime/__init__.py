"""
Runtime Adapter Layer - Abstraction for embedding/reranker runtime providers.

Supports multiple backends:
- llama.cpp: Primary default for local inference
- fallback: Deterministic hash-based (no model required)
- ollama: Development optional (placeholder)
- lm_studio: Desktop optional (placeholder)
- vllm: GPU scale optional (placeholder)
"""

from __future__ import annotations

import logging
import os
from typing import ClassVar, Dict, List, Optional, Any, Protocol
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RuntimeType(Enum):
    """Supported runtime types."""
    LLAMA_CPP = "llama.cpp"
    FALLBACK = "fallback"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    VLLM = "vllm"
    SENTENCE_TRANSFORMERS = "sentence_transformers"


@dataclass
class RuntimeConfig:
    """Configuration for a runtime instance."""
    runtime_type: RuntimeType
    host: str = "localhost"
    port: int = 8080
    model: str = "BAAI/bge-m3"
    dimensions: int = 1024
    timeout: float = 30.0
    # Additional settings
    device: Optional[str] = None
    batch_size: int = 32

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        """Create config from environment variables."""
        runtime_str = os.environ.get("EMBEDDING_RUNTIME", "llama.cpp")
        runtime_type = RuntimeType(runtime_str.lower().replace("-", "_"))

        return cls(
            runtime_type=runtime_type,
            host=os.environ.get("LLAMA_CPP_HOST", "localhost"),
            port=int(os.environ.get("LLAMA_CPP_PORT", "8080")),
            model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
            dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1024")),
            timeout=float(os.environ.get("EMBEDDING_TIMEOUT", "30.0")),
        )


class RuntimeStatus(Enum):
    """Status of runtime operations."""
    SUCCESS = "success"
    FALLBACK = "fallback"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass
class EmbeddingResult:
    """Result from embedding operation."""
    vectors: List[List[float]]
    model: str
    dimensions: int
    status: RuntimeStatus
    reason: Optional[str] = None
    provider: str = "local"
    runtime: str = "llama.cpp"


class RuntimeAdapter(Protocol):
    """Protocol for runtime adapters."""

    def is_available(self) -> bool:
        """Check if runtime is available."""
        ...

    def embed(self, texts: List[str]) -> EmbeddingResult:
        """Generate embeddings for texts."""
        ...

    def get_info(self) -> Dict[str, Any]:
        """Get runtime information."""
        ...


class FallbackAdapter:
    """
    Fallback adapter using deterministic hash-based embeddings.

    Used when:
    - Model not available
    - Runtime not started
    - Testing without models

    NOTE: This is NOT semantically meaningful. Only for testing/fallback.
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.dimensions = config.dimensions

    def is_available(self) -> bool:
        """Always available (no external dependency)."""
        return True

    def embed(self, texts: List[str]) -> EmbeddingResult:
        """Generate hash-based embeddings."""
        import hashlib

        vectors = []
        for text in texts:
            # Deterministic hash-based vector
            hash_val = hashlib.sha256(text.encode('utf-8')).hexdigest()
            vector = []
            for i in range(self.dimensions):
                chunk_start = (i * 4) % len(hash_val)
                chunk = hash_val[chunk_start:chunk_start+4]
                val = int(chunk, 16) / 65535.0
                vector.append(val)
            vectors.append(vector)

        return EmbeddingResult(
            vectors=vectors,
            model="local-hash-embedding-v1",
            dimensions=self.dimensions,
            status=RuntimeStatus.FALLBACK,
            reason="Using hash-based fallback (not semantically meaningful)",
            provider="local",
            runtime="fallback"
        )

    def get_info(self) -> Dict[str, Any]:
        return {
            "runtime": "fallback",
            "model": "local-hash-embedding-v1",
            "dimensions": self.dimensions,
            "available": True,
            "semantic": False,
        }


class LlamaCppAdapter:
    """
    Adapter for llama.cpp HTTP server.

    Connects to llama.cpp server for embeddings.
    Falls back gracefully when unavailable.
    """

    _availability_cache: ClassVar[Dict[tuple[str, int], bool]] = {}

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._available = None  # Lazy check

    def is_available(self) -> bool:
        """Check if llama.cpp server is running."""
        if self._available is not None:
            return self._available
        cache_key = (self.config.host, self.config.port)
        if cache_key in self._availability_cache:
            self._available = self._availability_cache[cache_key]
            return self._available

        try:
            import requests
            url = f"http://{self.config.host}:{self.config.port}/health"
            response = requests.get(url, timeout=min(self.config.timeout, 0.1))
            self._available = response.status_code == 200
        except Exception as e:
            logger.debug(f"llama.cpp health check failed: {e}")
            self._available = False

        self._availability_cache[cache_key] = self._available
        return self._available

    @staticmethod
    def _extract_vectors(data: Any) -> List[List[float]]:
        """Normalize llama.cpp embedding response variants."""
        embeddings: List[Any]

        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                items = sorted(data["data"], key=lambda x: x.get("index", 0) if isinstance(x, dict) else 0)
                embeddings = [
                    item.get("embedding")
                    for item in items
                    if isinstance(item, dict) and item.get("embedding") is not None
                ]
            else:
                embeddings = [data.get("embedding")]
        elif isinstance(data, list):
            if all(isinstance(item, dict) for item in data):
                items = sorted(data, key=lambda x: x.get("index", 0))
                embeddings = [
                    item.get("embedding")
                    for item in items
                    if item.get("embedding") is not None
                ]
            else:
                embeddings = data
        else:
            return []

        vectors: List[List[float]] = []
        for embedding in embeddings:
            if not isinstance(embedding, list) or not embedding:
                continue
            if isinstance(embedding[0], list):
                if len(embedding) == 1:
                    vectors.append(embedding[0])
                else:
                    vectors.extend(embedding)
            else:
                vectors.append(embedding)
        return vectors

    def embed(self, texts: List[str]) -> EmbeddingResult:
        """Generate embeddings via llama.cpp HTTP API."""
        if not self.is_available():
            return EmbeddingResult(
                vectors=[],
                model=self.config.model,
                dimensions=self.config.dimensions,
                status=RuntimeStatus.UNAVAILABLE,
                reason="llama.cpp server not available",
                provider="local",
                runtime="llama.cpp"
            )

        try:
            import requests
            url = f"http://{self.config.host}:{self.config.port}/embedding"

            # llama.cpp embedding API format
            payload = {
                "content": texts[0] if len(texts) == 1 else texts,
            }

            response = requests.post(
                url,
                json=payload,
                timeout=self.config.timeout
            )

            if response.status_code != 200:
                logger.error(f"llama.cpp embedding error: {response.status_code}")
                return EmbeddingResult(
                    vectors=[],
                    model=self.config.model,
                    dimensions=self.config.dimensions,
                    status=RuntimeStatus.ERROR,
                    reason=f"HTTP {response.status_code}",
                    provider="local",
                    runtime="llama.cpp"
                )

            vectors = self._extract_vectors(response.json())
            if not vectors:
                return EmbeddingResult(
                    vectors=[],
                    model=self.config.model,
                    dimensions=self.config.dimensions,
                    status=RuntimeStatus.ERROR,
                    reason="No embeddings in llama.cpp response",
                    provider="local",
                    runtime="llama.cpp"
                )

            return EmbeddingResult(
                vectors=vectors,
                model=self.config.model,
                dimensions=len(vectors[0]) if vectors else self.config.dimensions,
                status=RuntimeStatus.SUCCESS,
                provider="local",
                runtime="llama.cpp"
            )

        except Exception as e:
            logger.error(f"llama.cpp embedding failed: {e}")
            return EmbeddingResult(
                vectors=[],
                model=self.config.model,
                dimensions=self.config.dimensions,
                status=RuntimeStatus.ERROR,
                reason=str(e),
                provider="local",
                runtime="llama.cpp"
            )

    def get_info(self) -> Dict[str, Any]:
        return {
            "runtime": "llama.cpp",
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "available": self.is_available(),
            "host": self.config.host,
            "port": self.config.port,
        }


class SentenceTransformersAdapter:
    """
    Adapter for sentence-transformers (BGE-M3 direct loading).

    Uses sentence-transformers library to load BGE-M3 directly.
    This is the primary local embedding method when llama.cpp
    server is not used.
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._model = None
        self._initialized = False

    def _init_model(self) -> bool:
        """Initialize the model (lazy loading)."""
        if self._initialized:
            return self._model is not None

        try:
            from sentence_transformers import SentenceTransformer

            device = self.config.device
            if device is None:
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                        device = "mps"
                    else:
                        device = "cpu"
                except ImportError:
                    device = "cpu"

            logger.info(f"Loading {self.config.model} on {device}...")
            self._model = SentenceTransformer(
                self.config.model,
                device=device,
                trust_remote_code=True
            )
            self._initialized = True
            logger.info(f"Model loaded: {self.config.model}")
            return True

        except Exception as e:
            logger.warning(f"Failed to load model {self.config.model}: {e}")
            self._initialized = True
            return False

    def is_available(self) -> bool:
        """Check if model can be loaded."""
        return self._init_model()

    def embed(self, texts: List[str]) -> EmbeddingResult:
        """Generate embeddings using sentence-transformers."""
        if not self._init_model():
            return EmbeddingResult(
                vectors=[],
                model=self.config.model,
                dimensions=self.config.dimensions,
                status=RuntimeStatus.UNAVAILABLE,
                reason="sentence-transformers model not loaded",
                provider="local",
                runtime="sentence_transformers"
            )

        try:
            embeddings = self._model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            vectors = [emb.tolist() for emb in embeddings]

            return EmbeddingResult(
                vectors=vectors,
                model=self.config.model,
                dimensions=len(vectors[0]) if vectors else self.config.dimensions,
                status=RuntimeStatus.SUCCESS,
                provider="local",
                runtime="sentence_transformers"
            )

        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return EmbeddingResult(
                vectors=[],
                model=self.config.model,
                dimensions=self.config.dimensions,
                status=RuntimeStatus.ERROR,
                reason=str(e),
                provider="local",
                runtime="sentence_transformers"
            )

    def get_info(self) -> Dict[str, Any]:
        return {
            "runtime": "sentence_transformers",
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "available": self._model is not None,
            "initialized": self._initialized,
        }


class OllamaAdapter:
    """
    Placeholder adapter for Ollama.

    Ollama can serve embedding models via its API.
    This is a placeholder for development optional profile.
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config
        config.port = 11434  # Ollama default port

    def is_available(self) -> bool:
        """Placeholder - not implemented."""
        return False

    def embed(self, texts: List[str]) -> EmbeddingResult:
        """Placeholder - returns unavailable."""
        return EmbeddingResult(
            vectors=[],
            model=self.config.model,
            dimensions=self.config.dimensions,
            status=RuntimeStatus.UNAVAILABLE,
            reason="Ollama adapter not implemented (placeholder)",
            provider="local",
            runtime="ollama"
        )

    def get_info(self) -> Dict[str, Any]:
        return {
            "runtime": "ollama",
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "available": False,
            "note": "placeholder for dev_optional profile",
        }


class LMStudioAdapter:
    """
    Placeholder adapter for LM Studio.

    LM Studio provides local inference server.
    This is a placeholder for desktop optional profile.
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config

    def is_available(self) -> bool:
        """Placeholder - not implemented."""
        return False

    def embed(self, texts: List[str]) -> EmbeddingResult:
        """Placeholder - returns unavailable."""
        return EmbeddingResult(
            vectors=[],
            model=self.config.model,
            dimensions=self.config.dimensions,
            status=RuntimeStatus.UNAVAILABLE,
            reason="LM Studio adapter not implemented (placeholder)",
            provider="local",
            runtime="lm_studio"
        )

    def get_info(self) -> Dict[str, Any]:
        return {
            "runtime": "lm_studio",
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "available": False,
            "note": "placeholder for desktop_optional profile",
        }


class VLLMAdapter:
    """
    Placeholder adapter for vLLM.

    vLLM is optimized for GPU scale inference.
    This is a placeholder for scale optional profile.
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config

    def is_available(self) -> bool:
        """Placeholder - not implemented."""
        return False

    def embed(self, texts: List[str]) -> EmbeddingResult:
        """Placeholder - returns unavailable."""
        return EmbeddingResult(
            vectors=[],
            model=self.config.model,
            dimensions=self.config.dimensions,
            status=RuntimeStatus.UNAVAILABLE,
            reason="vLLM adapter not implemented (placeholder)",
            provider="local",
            runtime="vllm"
        )

    def get_info(self) -> Dict[str, Any]:
        return {
            "runtime": "vllm",
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "available": False,
            "note": "placeholder for scale_optional profile",
        }


def create_runtime_adapter(config: RuntimeConfig) -> RuntimeAdapter:
    """
    Create appropriate runtime adapter based on config.

    Args:
        config: Runtime configuration

    Returns:
        RuntimeAdapter instance
    """
    adapters = {
        RuntimeType.FALLBACK: FallbackAdapter,
        RuntimeType.LLAMA_CPP: LlamaCppAdapter,
        RuntimeType.SENTENCE_TRANSFORMERS: SentenceTransformersAdapter,
        RuntimeType.OLLAMA: OllamaAdapter,
        RuntimeType.LM_STUDIO: LMStudioAdapter,
        RuntimeType.VLLM: VLLMAdapter,
    }

    adapter_class = adapters.get(config.runtime_type, FallbackAdapter)
    return adapter_class(config)


def create_adapter_from_config(config_dict: Dict[str, Any]) -> RuntimeAdapter:
    """
    Create adapter from configuration dict.

    Args:
        config_dict: Configuration with runtime settings

    Returns:
        RuntimeAdapter instance
    """
    runtime_str = config_dict.get("runtime", "llama.cpp")
    runtime_type = RuntimeType(runtime_str.lower().replace("-", "_"))

    runtime_config = RuntimeConfig(
        runtime_type=runtime_type,
        host=config_dict.get("host", "localhost"),
        port=config_dict.get("port", 8080),
        model=config_dict.get("model", "BAAI/bge-m3"),
        dimensions=config_dict.get("dimensions", 1024),
        timeout=config_dict.get("timeout", 30.0),
        device=config_dict.get("device"),
        batch_size=config_dict.get("batch_size", 32),
    )

    return create_runtime_adapter(runtime_config)


__all__ = [
    'RuntimeType',
    'RuntimeConfig',
    'RuntimeStatus',
    'EmbeddingResult',
    'RuntimeAdapter',
    'FallbackAdapter',
    'LlamaCppAdapter',
    'SentenceTransformersAdapter',
    'OllamaAdapter',
    'LMStudioAdapter',
    'VLLMAdapter',
    'create_runtime_adapter',
    'create_adapter_from_config',
]
