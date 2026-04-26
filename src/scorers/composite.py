"""
Composite and Direction Scorers.

CompositeScorer combines all individual scorers.
DirectionScorer measures movement toward desired direction.
"""

from typing import List, Dict

from .base import BaseScorer, ScorerResult
from src.core.distance import cosine_similarity


class DirectionScorer(BaseScorer):
    """
    Direction scorer.

    Measures whether the trajectory is moving toward the accepted region
    (away from rejected region).
    Positive score = good direction, Negative score = bad direction.
    """

    def __init__(self, weight: float = 0.05):
        """
        Initialize DirectionScorer.

        Args:
            weight: Weight for this scorer in composite calculation (default: 0.05)
        """
        super().__init__(weight=weight, name="direction")

    def score(
        self,
        delta_semantic: List[float],
        accepted_centroid: List[float],
        rejected_centroid: List[float]
    ) -> ScorerResult:
        """
        Calculate direction score.

        Measures cosine similarity between the semantic delta and the
        accepted-rejected direction vector.

        Args:
            delta_semantic: Difference between current and previous semantic vectors
            accepted_centroid: Centroid of accepted examples
            rejected_centroid: Centroid of rejected examples

        Returns:
            ScorerResult with direction score
            Positive = moving toward accepted (good)
            Negative = moving toward rejected (bad)
        """
        if not self._validate_inputs(delta_semantic):
            return self._create_empty_result(
                "Missing delta_semantic (no previous step to compare)"
            )

        if not self._validate_inputs(accepted_centroid, rejected_centroid):
            return self._create_empty_result(
                "Missing accepted or rejected centroid for direction calculation"
            )

        # Check dimension compatibility
        dims = len(accepted_centroid)
        if dims != len(rejected_centroid) or dims != len(delta_semantic):
            return ScorerResult(
                name=self.name,
                score=0.0,
                weight=self.weight,
                weighted_score=0.0,
                top_exemplar_refs=[],
                explanation=(
                    f"Dimension mismatch: delta={len(delta_semantic)}, "
                    f"accepted={dims}, rejected={len(rejected_centroid)}"
                )
            )

        # Compute direction vector pointing toward accepted (away from rejected)
        direction_vector = self._compute_direction_vector(
            accepted_centroid, rejected_centroid
        )

        # Compute cosine similarity between delta and direction
        dir_score = cosine_similarity(delta_semantic, direction_vector)
        weighted = dir_score * self.weight

        direction_desc = self._describe_direction(dir_score)

        return ScorerResult(
            name=self.name,
            score=dir_score,
            weight=self.weight,
            weighted_score=weighted,
            top_exemplar_refs=[],
            explanation=(
                f"Direction score: {dir_score:.4f} (moving {direction_desc}, "
                f"delta_semantic aligned with accepted-rejected axis)"
            )
        )

    def _compute_direction_vector(
        self,
        accepted_centroid: List[float],
        rejected_centroid: List[float]
    ) -> List[float]:
        """
        Compute direction vector from rejected to accepted.

        Args:
            accepted_centroid: Centroid of accepted examples
            rejected_centroid: Centroid of rejected examples

        Returns:
            Direction vector
        """
        dims = len(accepted_centroid)
        return [accepted_centroid[i] - rejected_centroid[i] for i in range(dims)]

    def _describe_direction(self, score: float) -> str:
        """
        Describe direction based on score.

        Args:
            score: Direction score

        Returns:
            Human-readable direction description
        """
        if score > 0.3:
            return "toward accepted"
        elif score < -0.3:
            return "toward rejected"
        else:
            return "neutral"


class CompositeScorer:
    """
    Composite score calculator.

    Integrates results from all individual scorers into a composite score.
    """

    # Scorers where higher score = more risky
    RISK_SCORERS = ['taboo_proximity', 'reject_similarity', 'drift', 'anomaly', 'uncertainty']

    # Scorers where lower score = more risky (missing alignment = risk)
    SAFE_SCORERS = ['constitution_alignment', 'accept_similarity', 'direction']

    def __init__(self, config: Dict):
        """
        Initialize CompositeScorer with all individual scorers.

        Args:
            config: Configuration dict with scorer weights
        """
        from .constitution import ConstitutionAlignmentScorer
        from .taboo import TabooProximityScorer
        from .similarity import AcceptSimilarityScorer, RejectSimilarityScorer
        from .drift import DriftScorer
        from .anomaly import AnomalyScorer
        from .uncertainty import UncertaintyScorer

        self.scorers = {
            "constitution_alignment": ConstitutionAlignmentScorer(
                config.get('constitution_alignment', {}).get('weight', 0.20)
            ),
            "taboo_proximity": TabooProximityScorer(
                config.get('taboo_proximity', {}).get('weight', 0.30)
            ),
            "accept_similarity": AcceptSimilarityScorer(
                config.get('accept_similarity', {}).get('weight', 0.10)
            ),
            "reject_similarity": RejectSimilarityScorer(
                config.get('reject_similarity', {}).get('weight', 0.15)
            ),
            "direction": DirectionScorer(
                config.get('direction', {}).get('weight', 0.05)
            ),
            "drift": DriftScorer(
                config.get('drift', {}).get('weight', 0.10)
            ),
            "anomaly": AnomalyScorer(
                config.get('anomaly', {}).get('weight', 0.10)
            ),
            "uncertainty": UncertaintyScorer(
                config.get('uncertainty', {}).get('weight', 0.05)
            ),
        }

    def compute_composite(self, scorer_results: List[ScorerResult]) -> float:
        """
        Compute weighted composite score.

        Note: Each scorer's weighted_score already has weight applied.
        Note: Direction score can be negative and needs special handling.

        Args:
            scorer_results: List of ScorerResult from individual scorers

        Returns:
            Composite risk score (higher = more risky)
        """
        total_weighted = 0.0
        for r in scorer_results:
            if r.name == 'direction':
                # Direction score: positive=good, negative=bad
                # For risk composite: negative direction adds to risk
                direction_risk = max(0, -r.weighted_score)
                total_weighted += direction_risk
            else:
                total_weighted += r.weighted_score
        return total_weighted

    def get_top_factors(
        self,
        scorer_results: List[ScorerResult],
        n: int = 3
    ) -> List[str]:
        """
        Extract top contributing factors.

        Args:
            scorer_results: List of ScorerResult
            n: Number of top factors to return

        Returns:
            List of explanation strings for top factors
        """
        factors = []
        for r in scorer_results:
            if r.name in self.RISK_SCORERS:
                # Higher score = more significant risk factor
                factors.append((r.name, r.score, r.explanation, 'risk'))
            elif r.name in self.SAFE_SCORERS:
                # For direction: negative score is risky
                if r.name == 'direction':
                    factors.append((r.name, max(0, -r.score), r.explanation, 'safe'))
                else:
                    # Lower alignment score = risk factor
                    factors.append((r.name, 1 - r.score, r.explanation, 'safe'))

        # Sort by impact (descending)
        factors.sort(key=lambda x: x[1], reverse=True)

        return [f[2] for f in factors[:n]]

    def collect_exemplar_refs(
        self,
        scorer_results: List[ScorerResult],
        max_refs: int = 5
    ) -> List[str]:
        """
        Collect exemplar references from all scorers.

        Args:
            scorer_results: List of ScorerResult
            max_refs: Maximum number of refs to return

        Returns:
            Deduplicated list of document IDs
        """
        all_refs = []
        for r in scorer_results:
            all_refs.extend(r.top_exemplar_refs)

        # Deduplicate and limit
        seen = set()
        unique_refs = []
        for ref in all_refs:
            if ref and ref not in seen:
                seen.add(ref)
                unique_refs.append(ref)

        return unique_refs[:max_refs]