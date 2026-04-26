"""
Constitution Alignment Scorer.

Measures alignment with design constitution (design principles/guidelines).
"""

from typing import List, Dict, Optional

from src.core.distance import cosine_similarity
from .base import BaseScorer, ScorerResult


class ConstitutionAlignmentScorer(BaseScorer):
    """
    Design constitution alignment scorer.

    Measures how well the semantic vector aligns with the design constitution centroid.
    Higher score = more aligned = better (safer).
    """

    def __init__(self, weight: float = 0.20):
        """
        Initialize ConstitutionAlignmentScorer.

        Args:
            weight: Weight for this scorer in composite calculation (default: 0.20)
        """
        super().__init__(weight=weight, name="constitution_alignment")

    def score(
        self,
        semantic_vector: List[float],
        constitution_centroid: List[float],
        constitution_docs: Optional[List[Dict]] = None
    ) -> ScorerResult:
        """
        Calculate alignment score with design constitution centroid.

        Args:
            semantic_vector: Current semantic vector to evaluate
            constitution_centroid: Centroid vector of design constitution documents
            constitution_docs: Optional list of constitution documents for reference extraction

        Returns:
            ScorerResult with cosine similarity score to constitution centroid
        """
        if not self._validate_inputs(semantic_vector, constitution_centroid):
            return self._create_empty_result(
                "Missing semantic vector or constitution centroid"
            )

        sim = cosine_similarity(semantic_vector, constitution_centroid)
        weighted = sim * self.weight

        refs = self._get_top_refs_from_docs(constitution_docs, 5)

        return ScorerResult(
            name=self.name,
            score=sim,
            weight=self.weight,
            weighted_score=weighted,
            top_exemplar_refs=refs,
            explanation=f"Constitution alignment: {sim:.4f} (centroid similarity)"
        )

    def _get_top_refs_from_docs(
        self,
        docs: Optional[List[Dict]],
        max_refs: int
    ) -> List[str]:
        """
        Extract document IDs from constitution docs.

        Args:
            docs: Optional list of constitution documents
            max_refs: Maximum number of refs to return

        Returns:
            List of document IDs
        """
        if not docs:
            return []
        return [d.get('doc_id', '') for d in docs[:max_refs] if d.get('doc_id')]