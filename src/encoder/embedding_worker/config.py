"""
Embedding Worker Configuration Factory

Factory function for creating EmbeddingWorker from configuration.
"""

import os
from typing import Dict

from .constants import DEFAULT_MODEL, DEFAULT_DIMENSIONS, DEFAULT_RUNTIME
from .worker import EmbeddingWorker


def create_embedding_worker_from_config(config: Dict) -> EmbeddingWorker:
    """
    Create EmbeddingWorker from configuration

    Args:
        config: Configuration dict with embedding settings

    Returns:
        EmbeddingWorker instance
    """
    embedding_config = config.get('state_space_gate', {}).get('semantic_embedding', {})

    # Use defaults from RUNBOOK Local Retrieval Stack
    provider = embedding_config.get('provider') or os.environ.get('EMBEDDING_PROVIDER', 'local')
    runtime = embedding_config.get('runtime') or os.environ.get('EMBEDDING_RUNTIME', DEFAULT_RUNTIME)
    model = embedding_config.get('model') or os.environ.get('EMBEDDING_MODEL', DEFAULT_MODEL)
    dimensions = embedding_config.get('dimensions') or os.environ.get('EMBEDDING_DIMENSIONS', str(DEFAULT_DIMENSIONS))

    return EmbeddingWorker(
        provider=provider,
        runtime=runtime,
        model=model,
        dims=int(dimensions),
        api_key=embedding_config.get('api_key') or os.environ.get('OPENAI_API_KEY'),
        api_base=embedding_config.get('api_base')
    )


__all__ = ["create_embedding_worker_from_config"]