"""
JudgmentKB - Judgment Knowledge Base manager.
"""

import json
import logging
import pathlib
from datetime import datetime, timezone
from typing import List, Dict, Optional

from .store import VectorStore
from .types import SearchResult

logger = logging.getLogger(__name__)


class JudgmentKB:
    """Judgment Knowledge Base manager"""

    def __init__(self, vector_store: VectorStore, embedding_worker: 'EmbeddingWorker' = None):
        self.vs = vector_store
        self.embedding_worker = embedding_worker

    def import_document(
        self,
        axis_type: str,
        text: str,
        source_type: str = 'manual',
        scope: str = None,
        labels: dict = None,
        auto_embed: bool = True
    ) -> str:
        """
        Import new judgment document

        Args:
            axis_type: constitution, taboo, accepted, rejected, judgment_log
            text: Document text content
            source_type: manual, run_promoted, import
            scope: Optional scope filter
            labels: Optional labels dict
            auto_embed: Whether to automatically generate embedding

        Returns:
            doc_id of imported document
        """
        # Insert document
        doc_id = self.vs.insert_document(axis_type, text, source_type, scope, labels)

        # Generate embedding if worker is available
        if auto_embed and self.embedding_worker:
            embedding = self.embedding_worker.process_text(text)
            content_hash = self.embedding_worker.compute_hash(text)

            self.vs.insert_embedding(
                doc_id=doc_id,
                model=self.embedding_worker.model,
                dims=self.embedding_worker.dims,
                embedding=embedding,
                content_hash=content_hash
            )

        return doc_id

    def import_from_file(
        self,
        axis_type: str,
        file_path: str,
        format: str = 'jsonl',
        scope: str = None
    ) -> List[str]:
        """
        Import documents from file

        Args:
            axis_type: Target axis
            file_path: Path to file (jsonl, yaml, csv)
            format: File format
            scope: Scope for all imported docs

        Returns:
            List of imported doc_ids
        """
        path = pathlib.Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        doc_ids = []

        if format == 'jsonl':
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        doc_id = self.import_document(
                            axis_type=axis_type,
                            text=data.get('text', ''),
                            source_type='import',
                            scope=scope or data.get('scope'),
                            labels=data.get('labels'),
                            auto_embed=True
                        )
                        doc_ids.append(doc_id)

        return doc_ids

    def promote_from_run(
        self,
        run_id: str,
        axis_type: str = 'judgment_log',
        decision: str = None,
        comment: str = None,
        reviewer: str = None
    ) -> str:
        """
        Promote a run outcome to judgment log

        Args:
            run_id: Run ID to promote
            axis_type: Target axis (usually judgment_log)
            decision: Human review decision (approve/reject/recalibrate)
            comment: Reviewer comment
            reviewer: Reviewer name

        Returns:
            doc_id of promoted document
        """
        # Get state vector and decision
        state_vector = self.vs.get_state_vector(run_id)

        # Build judgment log entry
        text_parts = []
        if decision:
            text_parts.append(f"Decision: {decision}")
        if comment:
            text_parts.append(f"Comment: {comment}")
        if reviewer:
            text_parts.append(f"Reviewer: {reviewer}")
        if state_vector:
            context = state_vector.get('context_json', {})
            if context:
                text_parts.append(f"Context: {json.dumps(context)}")

        text = "\n".join(text_parts) if text_parts else f"Promoted from run {run_id}"

        labels = {
            'run_id': run_id,
            'decision': decision,
            'reviewer': reviewer,
            'promoted_at': datetime.now(timezone.utc).isoformat()
        }

        return self.import_document(
            axis_type=axis_type,
            text=text,
            source_type='run_promoted',
            labels=labels,
            auto_embed=True
        )

    def get_taboo_topk(
        self,
        query_vector: List[float],
        k: int = 5,
        scope: str = None
    ) -> List[SearchResult]:
        """Get top-k taboo examples"""
        return self.vs.search_similar(query_vector, 'taboo', k, scope)

    def get_accepted_topk(
        self,
        query_vector: List[float],
        k: int = 5,
        scope: str = None
    ) -> List[SearchResult]:
        """Get top-k accepted examples"""
        return self.vs.search_similar(query_vector, 'accepted', k, scope)

    def get_rejected_topk(
        self,
        query_vector: List[float],
        k: int = 5,
        scope: str = None
    ) -> List[SearchResult]:
        """Get top-k rejected examples"""
        return self.vs.search_similar(query_vector, 'rejected', k, scope)

    def get_constitution_centroid(self) -> List[float]:
        """Get constitution centroid for alignment scoring"""
        return self.vs.get_centroid('constitution')

    def get_embeddings_for_axis(
        self,
        axis_type: str,
        scope: str = None
    ) -> List[Dict]:
        """Get all embeddings and docs for an axis"""
        return self.vs.get_active_embeddings(axis_type, scope)

    def reindex_axis(self, axis_type: str) -> int:
        """
        Rebuild HNSW index for an axis

        Returns count of embeddings indexed
        """
        embeddings = self.vs.get_active_embeddings(axis_type)
        count = len(embeddings)

        logger.info(f"Reindexed {count} embeddings for axis {axis_type}")
        return count


__all__ = ['JudgmentKB']