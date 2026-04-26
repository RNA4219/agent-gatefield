"""
Qdrant Judgment KB - Local-first judgment knowledge base.

Combines QdrantVectorStore + LocalEmbedder + Reranker for complete local retrieval stack.
Implements RUNBOOK Local Retrieval Stack requirements.
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from .qdrant_store import QdrantVectorStore, SearchResult, DEFAULT_DIMS
from ..encoder.local_embedder import LocalEmbedder, Reranker, DEFAULT_MODEL

logger = logging.getLogger(__name__)


class QdrantJudgmentKB:
    """
    Judgment Knowledge Base with Qdrant backend and BGE-M3 embeddings.

    Implements RUNBOOK Local Retrieval Stack:
    - No external API required (OPENAI_API_KEY not needed)
    - BGE-M3 dense vectors (1024d)
    - bge-reranker-v2-m3 for reranking
    - Qdrant as vector DB
    """

    def __init__(
        self,
        vector_store: QdrantVectorStore = None,
        embedder: LocalEmbedder = None,
        reranker: Reranker = None,
        config: Dict[str, Any] = None
    ):
        """
        Initialize Qdrant Judgment KB.

        Args:
            vector_store: QdrantVectorStore instance (auto-created if None)
            embedder: LocalEmbedder instance (auto-created if None)
            reranker: Reranker instance (auto-created if None)
            config: Configuration dict
        """
        self.config = config or {}

        # Initialize components
        self.vector_store = vector_store or QdrantVectorStore(
            embedding_dims=self.config.get('dimensions', DEFAULT_DIMS),
            in_memory=self.config.get('in_memory', False),
            host=self.config.get('host'),
            port=self.config.get('port'),
        )

        self.embedder = embedder or LocalEmbedder(
            dimensions=self.config.get('dimensions', DEFAULT_DIMS),
            device=self.config.get('device'),
        )

        self.reranker = reranker or Reranker(
            enabled=self.config.get('reranker_enabled', True),
            device=self.config.get('device'),
        )

        # Top-k configuration per RUNBOOK
        self.top_k_input = self.config.get('top_k_input', 50)
        self.top_k_output = self.config.get('top_k_output', 10)

        logger.info(f"QdrantJudgmentKB initialized: dims={self.embedder.dimensions}, reranker={self.reranker.enabled}")

    def import_from_file(
        self,
        axis_type: str,
        file_path: str,
        format: str = 'jsonl',
        scope: str = None,
        auto_embed: bool = True
    ) -> List[str]:
        """
        Import judgment documents from file.

        Args:
            axis_type: Axis type (taboo, accepted, rejected, constitution)
            file_path: Path to JSONL file
            format: File format (jsonl)
            scope: Optional scope filter
            auto_embed: Generate embeddings automatically

        Returns:
            List of document IDs
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        docs = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    docs.append({
                        'doc_id': record.get('id'),
                        'axis_type': axis_type,
                        'text': record.get('text', ''),
                        'labels': {
                            'category': record.get('category'),
                            'severity': record.get('severity'),
                            'reviewers': record.get('reviewers', []),
                        },
                        'scope': scope,
                        'source_type': 'import',
                    })

        if not docs:
            return []

        # Generate embeddings
        if auto_embed:
            texts = [d['text'] for d in docs]
            embeddings = self.embedder.embed(texts)
        else:
            embeddings = [[0.5] * self.embedder.dimensions for _ in docs]

        # Batch insert
        doc_ids = self.vector_store.batch_insert(docs, embeddings)

        logger.info(f"Imported {len(doc_ids)} documents to {axis_type}")
        return doc_ids

    def search(
        self,
        query_text: str,
        axis_type: str,
        limit: int = None,
        scope: str = None,
        use_reranker: bool = True
    ) -> List[SearchResult]:
        """
        Search judgment KB with query text.

        Args:
            query_text: Query text
            axis_type: Axis type to search
            limit: Max results (default: top_k_output)
            scope: Optional scope filter
            use_reranker: Use reranker for final ranking

        Returns:
            List of SearchResult with reranker scores if enabled
        """
        limit = limit or self.top_k_output
        input_limit = self.top_k_input if use_reranker else limit

        # Embed query
        query_vector = self.embedder.embed_single(query_text)

        # Vector search
        results = self.vector_store.search_similar(
            query_vector=query_vector,
            axis_type=axis_type,
            limit=input_limit,
            scope=scope
        )

        # Rerank if enabled
        if use_reranker and self.reranker.enabled and results:
            candidates = [
                {'doc_id': r.doc_id, 'text': r.text, 'similarity': r.similarity,
                 'axis_type': r.axis_type, 'labels': r.labels, 'scope': r.scope}
                for r in results
            ]
            reranked = self.reranker.rerank(query_text, candidates, top_k=limit)

            # Convert back to SearchResult with reranker score
            results = []
            for c in reranked:
                results.append(SearchResult(
                    doc_id=c['doc_id'],
                    similarity=c.get('similarity', 0),
                    axis_type=c.get('axis_type', axis_type),
                    text=c.get('text', ''),
                    labels=c.get('labels'),
                    reranker_score=c.get('reranker_score'),
                ))

        return results[:limit]

    def get_taboo_topk(
        self,
        query_text: str,
        limit: int = 5
    ) -> List[SearchResult]:
        """Search taboo axis."""
        return self.search(query_text, 'taboo', limit)

    def get_accepted_topk(
        self,
        query_text: str,
        limit: int = 5
    ) -> List[SearchResult]:
        """Search accepted axis."""
        return self.search(query_text, 'accepted', limit)

    def get_rejected_topk(
        self,
        query_text: str,
        limit: int = 5
    ) -> List[SearchResult]:
        """Search rejected axis."""
        return self.search(query_text, 'rejected', limit)

    def get_constitution_centroid(self) -> Optional[List[float]]:
        """Get constitution axis centroid."""
        return self.vector_store.get_centroid('constitution')

    def get_model_info(self) -> Dict[str, Any]:
        """Get model configuration info."""
        return {
            'embedding': self.embedder.get_model_info(),
            'reranker': self.reranker.get_info(),
            'vector_store': self.vector_store.get_collection_info(),
            'top_k': {'input': self.top_k_input, 'output': self.top_k_output},
        }

    def close(self):
        """Close all connections."""
        self.vector_store.close()


def create_qdrant_kb(config: Dict[str, Any] = None) -> QdrantJudgmentKB:
    """
    Create QdrantJudgmentKB from config.

    Args:
        config: Configuration dict with keys:
            - dimensions: Vector dimensions (default: 1024)
            - device: Device for inference (cuda, cpu, mps)
            - reranker_enabled: Enable reranker (default: True)
            - top_k_input: Vector search limit (default: 50)
            - top_k_output: Final output limit (default: 10)
            - in_memory: Use in-memory Qdrant (default: False)
            - host: Qdrant host
            - port: Qdrant port
    """
    return QdrantJudgmentKB(config=config)


__all__ = [
    'QdrantJudgmentKB',
    'create_qdrant_kb',
]