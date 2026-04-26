"""
Taboo Proximity Scorer.

Measures proximity to taboo (forbidden) examples.
"""

from typing import List, Dict, Optional, Tuple

from src.core.distance import cosine_similarity
from .base import BaseScorer, ScorerResult


class TabooProximityScorer(BaseScorer):
    """
    Taboo proximity scorer.

    Measures how close the semantic vector is to taboo (forbidden) examples.
    Higher score = closer to taboo = more risky.
    """

    def __init__(self, weight: float = 0.30):
        """
        Initialize TabooProximityScorer.

        Args:
            weight: Weight for this scorer in composite calculation (default: 0.30)
        """
        super().__init__(weight=weight, name="taboo_proximity")

    def score(
        self,
        semantic_vector: List[float],
        taboo_embeddings: List[List[float]],
        taboo_docs: Optional[List[Dict]] = None,
        top_k: int = 5
    ) -> ScorerResult:
        """
        Calculate proximity score to taboo examples.

        Args:
            semantic_vector: Current semantic vector to evaluate
            taboo_embeddings: List of taboo example embedding vectors
            taboo_docs: Optional list of taboo documents for reference extraction
            top_k: Number of top matches to consider

        Returns:
            ScorerResult with max cosine similarity to taboo corpus
        """
        if not self._validate_inputs(semantic_vector, taboo_embeddings):
            return self._create_empty_result("No taboo embeddings available")

        # Calculate similarity to each taboo embedding
        similarities = self._compute_similarities(semantic_vector, taboo_embeddings, taboo_docs)

        # Sort by similarity (descending) and take top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_matches = similarities[:top_k]

        max_sim = top_matches[0][1] if top_matches else 0.0
        weighted = max_sim * self.weight

        refs, explanations = self._extract_match_details(top_matches)

        return ScorerResult(
            name=self.name,
            score=max_sim,
            weight=self.weight,
            weighted_score=weighted,
            top_exemplar_refs=refs,
            explanation=(
                f"Taboo proximity: {max_sim:.4f} (max similarity to taboo corpus). "
                f"Top matches: {', '.join(explanations[:3])}"
            )
        )

    def _compute_similarities(
        self,
        semantic_vector: List[float],
        embeddings: List[List[float]],
        docs: Optional[List[Dict]]
    ) -> List[Tuple[int, float, Optional[Dict]]]:
        """
        Compute similarities to all embeddings.

        Args:
            semantic_vector: Vector to compare against
            embeddings: List of embedding vectors
            docs: Optional list of documents

        Returns:
            List of (index, similarity, doc) tuples
        """
        similarities = []
        for i, vec in enumerate(embeddings):
            sim = cosine_similarity(semantic_vector, vec)
            doc = docs[i] if docs and i < len(docs) else None
            similarities.append((i, sim, doc))
        return similarities

    def _extract_match_details(
        self,
        matches: List[Tuple[int, float, Optional[Dict]]]
    ) -> Tuple[List[str], List[str]]:
        """
        Extract refs and explanation strings from matches.

        Args:
            matches: List of (index, similarity, doc) tuples

        Returns:
            Tuple of (refs list, explanations list)
        """
        refs = []
        explanations = []
        for idx, sim, doc in matches:
            if doc:
                doc_id = doc.get('doc_id', '')
                if doc_id:
                    refs.append(doc_id)
                taboo_type = doc.get('labels', {}).get('taboo_type', 'unknown')
                explanations.append(f"{taboo_type}: {sim:.4f}")
        return refs, explanations