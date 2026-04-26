"""
Similarity Scorers.

Scorers for measuring similarity to accepted and rejected examples.
"""

from typing import List, Dict, Optional, Tuple

from src.core.distance import cosine_similarity
from .base import BaseScorer, ScorerResult


class BaseSimilarityScorer(BaseScorer):
    """
    Base class for similarity-based scorers.

    Provides common methods for computing similarities to example corpus.
    """

    def __init__(self, weight: float, name: str):
        super().__init__(weight=weight, name=name)

    def _compute_top_similarities(
        self,
        semantic_vector: List[float],
        embeddings: List[List[float]],
        docs: Optional[List[Dict]],
        top_k: int = 5
    ) -> Tuple[List[Tuple[int, float, Optional[Dict]]], float]:
        """
        Compute similarities and return top-k matches.

        Args:
            semantic_vector: Vector to compare against
            embeddings: List of embedding vectors
            docs: Optional list of documents
            top_k: Number of top matches to return

        Returns:
            Tuple of (top_matches list, max_similarity)
        """
        similarities = []
        for i, vec in enumerate(embeddings):
            sim = cosine_similarity(semantic_vector, vec)
            doc = docs[i] if docs and i < len(docs) else None
            similarities.append((i, sim, doc))

        similarities.sort(key=lambda x: x[1], reverse=True)
        top_matches = similarities[:top_k]
        max_sim = top_matches[0][1] if top_matches else 0.0

        return top_matches, max_sim


class AcceptSimilarityScorer(BaseSimilarityScorer):
    """
    Accepted examples similarity scorer.

    Measures how similar the semantic vector is to previously accepted examples.
    Higher score = similar to accepted = better (safer).
    """

    def __init__(self, weight: float = 0.10):
        """
        Initialize AcceptSimilarityScorer.

        Args:
            weight: Weight for this scorer in composite calculation (default: 0.10)
        """
        super().__init__(weight=weight, name="accept_similarity")

    def score(
        self,
        semantic_vector: List[float],
        accepted_embeddings: List[List[float]],
        accepted_docs: Optional[List[Dict]] = None,
        top_k: int = 5
    ) -> ScorerResult:
        """
        Calculate similarity score to accepted examples.

        Args:
            semantic_vector: Current semantic vector to evaluate
            accepted_embeddings: List of accepted example embedding vectors
            accepted_docs: Optional list of accepted documents for reference extraction
            top_k: Number of top matches to consider

        Returns:
            ScorerResult with max cosine similarity to accepted corpus
        """
        if not self._validate_inputs(semantic_vector, accepted_embeddings):
            return self._create_empty_result("No accepted embeddings available")

        top_matches, max_sim = self._compute_top_similarities(
            semantic_vector, accepted_embeddings, accepted_docs, top_k
        )
        weighted = max_sim * self.weight

        refs = self._extract_refs(top_matches)

        return ScorerResult(
            name=self.name,
            score=max_sim,
            weight=self.weight,
            weighted_score=weighted,
            top_exemplar_refs=refs,
            explanation=f"Accept similarity: {max_sim:.4f} (max similarity to accepted corpus)"
        )

    def _extract_refs(
        self,
        matches: List[Tuple[int, float, Optional[Dict]]]
    ) -> List[str]:
        """
        Extract document IDs from matches.

        Args:
            matches: List of (index, similarity, doc) tuples

        Returns:
            List of document IDs
        """
        refs = []
        for idx, sim, doc in matches:
            if doc:
                doc_id = doc.get('doc_id', '')
                if doc_id:
                    refs.append(doc_id)
        return refs


class RejectSimilarityScorer(BaseSimilarityScorer):
    """
    Rejected examples similarity scorer.

    Measures how similar the semantic vector is to previously rejected examples.
    Higher score = similar to rejected = more risky.
    """

    def __init__(self, weight: float = 0.15):
        """
        Initialize RejectSimilarityScorer.

        Args:
            weight: Weight for this scorer in composite calculation (default: 0.15)
        """
        super().__init__(weight=weight, name="reject_similarity")

    def score(
        self,
        semantic_vector: List[float],
        rejected_embeddings: List[List[float]],
        rejected_docs: Optional[List[Dict]] = None,
        top_k: int = 5
    ) -> ScorerResult:
        """
        Calculate similarity score to rejected examples.

        Args:
            semantic_vector: Current semantic vector to evaluate
            rejected_embeddings: List of rejected example embedding vectors
            rejected_docs: Optional list of rejected documents for reference extraction
            top_k: Number of top matches to consider

        Returns:
            ScorerResult with max cosine similarity to rejected corpus
        """
        if not self._validate_inputs(semantic_vector, rejected_embeddings):
            return self._create_empty_result("No rejected embeddings available")

        top_matches, max_sim = self._compute_top_similarities(
            semantic_vector, rejected_embeddings, rejected_docs, top_k
        )
        weighted = max_sim * self.weight

        refs, reasons = self._extract_match_details(top_matches)

        return ScorerResult(
            name=self.name,
            score=max_sim,
            weight=self.weight,
            weighted_score=weighted,
            top_exemplar_refs=refs,
            explanation=f"Reject similarity: {max_sim:.4f}. Top reject reasons: {', '.join(reasons[:3])}"
        )

    def _extract_match_details(
        self,
        matches: List[Tuple[int, float, Optional[Dict]]]
    ) -> Tuple[List[str], List[str]]:
        """
        Extract refs and reject reasons from matches.

        Args:
            matches: List of (index, similarity, doc) tuples

        Returns:
            Tuple of (refs list, reasons list)
        """
        refs = []
        reasons = []
        for idx, sim, doc in matches:
            if doc:
                doc_id = doc.get('doc_id', '')
                if doc_id:
                    refs.append(doc_id)
                reason = doc.get('labels', {}).get('reject_reason', 'unknown')
                reasons.append(f"{reason}: {sim:.4f}")
        return refs, reasons