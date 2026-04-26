"""
Reranker Module - bge-reranker-v2-m3 integration for candidate reranking.

Default model: BAAI/bge-reranker-v2-m3
Fallback: Deterministic similarity-based ranking (no model required)

Reranker scores are included in decision explanations and exemplar refs.
"""

import logging
import os
from typing import Dict, List, Optional, Any, Protocol
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Default model per RUNBOOK
DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_TOP_K_INPUT = 50
DEFAULT_TOP_K_OUTPUT = 10


class RerankerStatus(Enum):
    """Status of reranking operations."""
    SUCCESS = "success"
    FALLBACK = "fallback"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass
class RerankResult:
    """Result from reranking operation."""
    candidates: List[Dict[str, Any]]
    model: str
    status: RerankerStatus
    reason: Optional[str] = None
    provider: str = "local"
    runtime: str = "sentence_transformers"


class RerankerAdapter(Protocol):
    """Protocol for reranker adapters."""

    def is_available(self) -> bool:
        """Check if reranker is available."""
        ...

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10
    ) -> RerankResult:
        """Rerank candidates based on query."""
        ...

    def get_info(self) -> Dict[str, Any]:
        """Get reranker info."""
        ...


class SentenceTransformersReranker:
    """
    Reranker using sentence-transformers CrossEncoder.

    Uses BAAI/bge-reranker-v2-m3 by default.
    """

    def __init__(self, model: str = None, enabled: bool = True):
        self.model = model or DEFAULT_MODEL
        self.enabled = enabled
        self._cross_encoder = None
        self._initialized = False

    def _init_model(self) -> bool:
        """Initialize CrossEncoder (lazy loading)."""
        if self._initialized:
            return self._cross_encoder is not None

        if not self.enabled:
            self._initialized = True
            return False

        try:
            from sentence_transformers import CrossEncoder

            # Auto-detect device
            device = None
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

            logger.info(f"Loading reranker {self.model} on {device}...")
            self._cross_encoder = CrossEncoder(
                self.model,
                device=device,
                trust_remote_code=True
            )
            self._initialized = True
            logger.info(f"Reranker loaded: {self.model}")
            return True

        except ImportError:
            logger.warning("sentence-transformers not installed, reranker unavailable")
            self._initialized = True
            return False
        except Exception as e:
            logger.warning(f"Failed to load reranker {self.model}: {e}")
            self._initialized = True
            return False

    def is_available(self) -> bool:
        """Check if reranker model is loaded."""
        return self._init_model()

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10
    ) -> RerankResult:
        """Rerank candidates using CrossEncoder."""
        if not candidates:
            return RerankResult(
                candidates=[],
                model=self.model,
                status=RerankerStatus.SUCCESS,
                provider="local",
                runtime="sentence_transformers"
            )

        if not self._init_model() or self._cross_encoder is None:
            return self._fallback_rerank(query, candidates, top_k)

        try:
            # Prepare pairs for cross-encoder
            pairs = [(query, c.get('text', '')) for c in candidates]

            # Get reranker scores
            scores = self._cross_encoder.predict(pairs)

            # Add scores to candidates
            scored_candidates = []
            for i, candidate in enumerate(candidates):
                candidate_copy = dict(candidate)
                candidate_copy['reranker_score'] = float(scores[i])
                scored_candidates.append(candidate_copy)

            # Sort by reranker score (descending)
            scored_candidates.sort(key=lambda x: x.get('reranker_score', 0), reverse=True)

            return RerankResult(
                candidates=scored_candidates[:top_k],
                model=self.model,
                status=RerankerStatus.SUCCESS,
                provider="local",
                runtime="sentence_transformers"
            )

        except Exception as e:
            logger.error(f"Reranking error: {e}")
            return self._fallback_rerank(query, candidates, top_k, reason=str(e))

    def _fallback_rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10,
        reason: str = None
    ) -> RerankResult:
        """Fallback reranking using similarity scores."""
        # Use existing similarity score if available
        scored_candidates = []
        for candidate in candidates:
            candidate_copy = dict(candidate)
            # Use existing similarity as fallback reranker score
            candidate_copy['reranker_score'] = candidate.get('similarity', 0.5)
            candidate_copy['fallback_rerank'] = True
            scored_candidates.append(candidate_copy)

        # Sort by similarity (descending)
        scored_candidates.sort(key=lambda x: x.get('reranker_score', 0), reverse=True)

        return RerankResult(
            candidates=scored_candidates[:top_k],
            model="fallback-similarity",
            status=RerankerStatus.FALLBACK,
            reason=reason or "Reranker model not available, using similarity fallback",
            provider="local",
            runtime="fallback"
        )

    def get_info(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "enabled": self.enabled,
            "available": self._cross_encoder is not None,
            "initialized": self._initialized,
            "provider": "local",
            "runtime": "sentence_transformers",
        }


class DeterministicFallbackReranker:
    """
    Deterministic fallback reranker for testing.

    Uses similarity score or deterministic ranking when reranker unavailable.
    This is NOT semantically meaningful - only for testing/fallback.
    """

    def __init__(self):
        self.model = "fallback-deterministic"
        self.enabled = True

    def is_available(self) -> bool:
        """Always available (no external dependency)."""
        return True

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10
    ) -> RerankResult:
        """Rerank using deterministic similarity-based ranking."""
        if not candidates:
            return RerankResult(
                candidates=[],
                model=self.model,
                status=RerankerStatus.SUCCESS,
                provider="local",
                runtime="fallback"
            )

        # Use existing similarity as fallback
        scored_candidates = []
        for candidate in candidates:
            candidate_copy = dict(candidate)
            candidate_copy['reranker_score'] = candidate.get('similarity', 0.5)
            candidate_copy['fallback_rerank'] = True
            scored_candidates.append(candidate_copy)

        # Sort by similarity (descending)
        scored_candidates.sort(key=lambda x: x.get('reranker_score', 0), reverse=True)

        return RerankResult(
            candidates=scored_candidates[:top_k],
            model=self.model,
            status=RerankerStatus.FALLBACK,
            reason="Using deterministic fallback (not semantically meaningful)",
            provider="local",
            runtime="fallback"
        )

    def get_info(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "enabled": True,
            "available": True,
            "semantic": False,
            "provider": "local",
            "runtime": "fallback",
        }


def create_reranker(
    model: str = None,
    enabled: bool = True,
    use_fallback: bool = False
) -> RerankerAdapter:
    """
    Create reranker instance.

    Args:
        model: Reranker model name
        enabled: Whether reranker is enabled
        use_fallback: Force fallback mode

    Returns:
        RerankerAdapter instance
    """
    if use_fallback:
        return DeterministicFallbackReranker()

    return SentenceTransformersReranker(model=model, enabled=enabled)


def create_reranker_from_config(config: Dict[str, Any]) -> RerankerAdapter:
    """
    Create reranker from configuration.

    Args:
        config: Configuration dict with reranker settings

    Returns:
        RerankerAdapter instance
    """
    reranker_config = config.get('state_space_gate', {}).get('reranker', {})

    enabled = reranker_config.get('enabled', True)
    model = reranker_config.get('model') or os.environ.get('RERANKER_MODEL', DEFAULT_MODEL)

    return create_reranker(model=model, enabled=enabled)


__all__ = [
    'RerankerStatus',
    'RerankResult',
    'RerankerAdapter',
    'SentenceTransformersReranker',
    'DeterministicFallbackReranker',
    'create_reranker',
    'create_reranker_from_config',
    'DEFAULT_MODEL',
    'DEFAULT_TOP_K_INPUT',
    'DEFAULT_TOP_K_OUTPUT',
]