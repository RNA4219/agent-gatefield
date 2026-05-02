"""
Re-Embed Job

Scheduled job for embedding model migration with dual-write process.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .constants import DEFAULT_MODEL, DEFAULT_DIMENSIONS
from .worker import EmbeddingWorker

logger = logging.getLogger(__name__)


class ReEmbedJob:
    """
    Scheduled job for embedding model migration

    Handles dual-write migration process:
    1. Generate new embeddings, keep old ones active
    2. Validate new embeddings
    3. Deprecate old embeddings (set valid_to)
    4. Trigger recalibration
    """

    def __init__(
        self,
        axis_type: str,
        old_model: str,
        new_model: str,
        old_dims: int = 1536,
        new_dims: int = 1536
    ):
        self.axis_type = axis_type
        self.old_model = old_model
        self.new_model = new_model
        self.old_dims = old_dims
        self.new_dims = new_dims
        self.status = "pending"
        self.progress = 0.0
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None

    def execute(
        self,
        vector_store: 'VectorStore',
        calibration_pipeline: 'CalibrationPipeline' = None
    ) -> Dict:
        """
        Execute re-embedding with dual-write

        Args:
            vector_store: VectorStore for persistence
            calibration_pipeline: Optional calibration pipeline for threshold update

        Returns:
            Dict with execution status
        """
        self.status = "processing"
        self.started_at = datetime.now(timezone.utc)

        try:
            # Phase 1: Generate new embeddings
            worker = EmbeddingWorker(model=self.new_model, dims=self.new_dims)
            result = worker.re_embed_all(
                axis_type=self.axis_type,
                new_model=self.new_model,
                new_dims=self.new_dims,
                vector_store=vector_store
            )

            if result.get('status') != 'completed':
                self.status = "failed"
                self.error = result.get('reason', 'Unknown error')
                return result

            self.progress = 0.5

            # Phase 2: Validate new embeddings
            new_embeddings = vector_store.get_active_embeddings(self.axis_type)
            validation_passed = self._validate_embeddings(new_embeddings)

            if not validation_passed:
                self.status = "failed"
                self.error = "Validation failed"
                return {"status": "failed", "reason": "validation_failed"}

            self.progress = 0.75

            # Phase 3: Deprecate old embeddings
            deprecated_count = self._deprecate_old_embeddings(vector_store)

            self.progress = 0.90

            # Phase 4: Trigger recalibration (optional)
            if calibration_pipeline:
                calibration_pipeline.run_offline_eval(
                    dataset_path="",  # Would use axis dataset
                    threshold_version=f"v-{self.new_model}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
                )

            self.status = "completed"
            self.completed_at = datetime.now(timezone.utc)
            self.progress = 1.0

            return {
                "status": "completed",
                "axis_type": self.axis_type,
                "old_model": self.old_model,
                "new_model": self.new_model,
                "new_embeddings_count": len(new_embeddings),
                "deprecated_count": deprecated_count,
                "duration_seconds": (
                    self.completed_at - self.started_at
                ).total_seconds() if self.started_at else 0
            }

        except Exception as e:
            self.status = "failed"
            self.error = str(e)
            logger.error(f"Re-embed job failed: {e}")
            return {"status": "failed", "error": str(e)}

    def _validate_embeddings(self, embeddings: List[Dict]) -> bool:
        """Validate new embeddings"""
        if not embeddings:
            return False

        for emb in embeddings:
            if emb.get('model') != self.new_model:
                return False
            if emb.get('dims') != self.new_dims:
                return False
            actual_emb = emb.get('embedding', [])
            if not actual_emb or len(actual_emb) != self.new_dims:
                return False

        return True

    def _deprecate_old_embeddings(self, vector_store: 'VectorStore') -> int:
        """Deprecate old embeddings by setting valid_to"""
        # This would use a custom query to update embeddings where model = old_model
        # For now, return count as placeholder
        count = 0
        # Would execute: UPDATE judgment_embeddings SET valid_to = NOW()
        # WHERE model = old_model AND valid_to IS NULL
        return count


__all__ = ["ReEmbedJob"]