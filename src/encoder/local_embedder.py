"""
Local Embedder - BGE-M3 integration for local-first semantic retrieval.

No external API required. Uses sentence-transformers with BAAI/bge-m3.
"""

import hashlib
import logging
import os
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Model configuration per RUNBOOK
DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_DIMENSIONS = 1024  # BGE-M3 dense dimensions
FALLBACK_MODEL = "local-hash-embedding-v1"
FALLBACK_DIMENSIONS = 1536


class LocalEmbedder:
    """
    Local embedding using BGE-M3 without external API calls.

    Implements RUNBOOK Local Retrieval Stack requirements.
    """

    def __init__(
        self,
        model_name: str = None,
        dimensions: int = None,
        device: str = None,
        use_fallback: bool = False
    ):
        """
        Initialize local embedder.

        Args:
            model_name: Model name (default: BAAI/bge-m3)
            dimensions: Output dimensions (default: 1024 for BGE-M3 dense)
            device: Device to use (cuda, cpu, mps). Auto-detect if None.
            use_fallback: Use hash-based fallback instead of BGE-M3
        """
        self.model_name = model_name or DEFAULT_MODEL
        self.dimensions = dimensions or DEFAULT_DIMENSIONS
        self.use_fallback = use_fallback

        # Device configuration (defer torch import)
        self._configured_device = device
        self._device = None  # Will be set on first use

        self._model = None
        self._initialized = False

        logger.info(f"LocalEmbedder configured: model={self.model_name}, dims={self.dimensions}")

    @property
    def device(self) -> str:
        """Get device, auto-detect if needed."""
        if self._device is None:
            if self._configured_device:
                self._device = self._configured_device
            else:
                # Lazy import torch only when needed
                try:
                    import torch
                    if torch.cuda.is_available():
                        self._device = "cuda"
                    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                        self._device = "mps"
                    else:
                        self._device = "cpu"
                except ImportError:
                    self._device = "cpu"
        return self._device

    def _init_model(self) -> bool:
        """Initialize the embedding model (lazy loading)."""
        if self._initialized:
            return self._model is not None

        if self.use_fallback:
            logger.info("Using hash-based fallback embedding (no model loading)")
            self._initialized = True
            return False  # No model, use hash

        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading {self.model_name} on {self.device}...")
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                trust_remote_code=True
            )
            self._initialized = True
            logger.info(f"Model loaded successfully: {self.model_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load BGE-M3: {e}. Using fallback embedding.")
            self.use_fallback = True
            self.dimensions = FALLBACK_DIMENSIONS
            self._initialized = True
            return False

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each is list of floats)
        """
        if not texts:
            return []

        # Lazy initialize
        has_model = self._init_model()

        if has_model and self._model is not None:
            # Use BGE-M3
            try:
                embeddings = self._model.encode(
                    texts,
                    normalize_embeddings=True,
                    show_progress_bar=False
                )
                # Convert to list of lists
                return [emb.tolist() for emb in embeddings]
            except Exception as e:
                logger.error(f"Embedding error: {e}")
                # Fall back to hash
                return self._hash_embed(texts)
        else:
            # Use hash-based fallback
            return self._hash_embed(texts)

    def embed_single(self, text: str) -> List[float]:
        """Generate embedding for single text."""
        return self.embed([text])[0]

    def _hash_embed(self, texts: List[str]) -> List[List[float]]:
        """
        Deterministic hash-based embedding (fallback / test fixture).

        This is NOT semantically meaningful, only for testing.
        """
        embeddings = []
        for text in texts:
            # Create deterministic hash-based vector
            hash_val = hashlib.sha256(text.encode('utf-8')).hexdigest()
            # Convert to floats
            vector = []
            for i in range(self.dimensions):
                # Use chunks of hash to generate values
                chunk_start = (i * 4) % len(hash_val)
                chunk = hash_val[chunk_start:chunk_start+4]
                val = int(chunk, 16) / 65535.0  # Normalize to [0, 1]
                vector.append(val)
            embeddings.append(vector)
        return embeddings

    def get_model_info(self) -> Dict[str, Any]:
        """Get current model configuration info."""
        return {
            'model': self.model_name if not self.use_fallback else FALLBACK_MODEL,
            'dimensions': self.dimensions,
            'device': self.device,
            'initialized': self._initialized,
            'using_fallback': self.use_fallback,
            'provider': 'local',
        }


class Reranker:
    """
    Local reranker using bge-reranker-v2-m3.

    Implements RUNBOOK reranker requirements.
    """

    DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"

    def __init__(
        self,
        model_name: str = None,
        device: str = None,
        enabled: bool = True
    ):
        """
        Initialize reranker.

        Args:
            model_name: Reranker model (default: bge-reranker-v2-m3)
            device: Device to use (auto-detect if None)
            enabled: Whether reranker is enabled
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.enabled = enabled
        self._model = None
        self._initialized = False

        # Device configuration (defer torch import)
        self._configured_device = device
        self._device = None

        logger.info(f"Reranker configured: model={self.model_name}, enabled={self.enabled}")

    @property
    def device(self) -> str:
        """Get device, auto-detect if needed."""
        if self._device is None:
            if self._configured_device:
                self._device = self._configured_device
            else:
                try:
                    import torch
                    if torch.cuda.is_available():
                        self._device = "cuda"
                    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                        self._device = "mps"
                    else:
                        self._device = "cpu"
                except ImportError:
                    self._device = "cpu"
        return self._device

    def _init_model(self) -> bool:
        """Initialize reranker model (lazy loading)."""
        if self._initialized:
            return self._model is not None

        if not self.enabled:
            self._initialized = True
            return False

        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker {self.model_name}...")
            self._model = CrossEncoder(
                self.model_name,
                device=self.device,
                trust_remote_code=True
            )
            self._initialized = True
            logger.info(f"Reranker loaded: {self.model_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load reranker: {e}. Reranking disabled.")
            self.enabled = False
            self._initialized = True
            return False

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Rerank candidates based on query.

        Args:
            query: Query text
            candidates: List of candidates with 'text' field
            top_k: Number of top results to return

        Returns:
            Reranked candidates with added 'reranker_score' field
        """
        if not candidates or not self.enabled:
            return candidates[:top_k]

        has_model = self._init_model()

        if not has_model or self._model is None:
            return candidates[:top_k]

        try:
            # Prepare pairs for cross-encoder
            pairs = [(query, c.get('text', '')) for c in candidates]

            # Get reranker scores
            scores = self._model.predict(pairs)

            # Add scores to candidates
            scored_candidates = []
            for i, candidate in enumerate(candidates):
                candidate['reranker_score'] = float(scores[i])
                scored_candidates.append(candidate)

            # Sort by reranker score (descending)
            scored_candidates.sort(key=lambda x: x.get('reranker_score', 0), reverse=True)

            return scored_candidates[:top_k]
        except Exception as e:
            logger.error(f"Reranking error: {e}")
            return candidates[:top_k]

    def get_info(self) -> Dict[str, Any]:
        """Get reranker info."""
        return {
            'model': self.model_name,
            'enabled': self.enabled,
            'device': self.device,
            'initialized': self._initialized,
        }


# Convenience function
def create_local_embedder(config: Dict[str, Any] = None) -> LocalEmbedder:
    """
    Create LocalEmbedder from config.

    Args:
        config: Configuration dict with optional keys:
            - model: Model name
            - dimensions: Vector dimensions
            - device: Device to use
            - fallback: Use fallback mode
    """
    if config is None:
        config = {}

    return LocalEmbedder(
        model_name=config.get('model'),
        dimensions=config.get('dimensions'),
        device=config.get('device'),
        use_fallback=config.get('fallback', False)
    )


__all__ = [
    'LocalEmbedder',
    'Reranker',
    'create_local_embedder',
    'DEFAULT_MODEL',
    'DEFAULT_DIMENSIONS',
    'FALLBACK_MODEL',
    'FALLBACK_DIMENSIONS',
]