"""
Uncertainty Scorer.

Measures uncertainty from multiple factors.
"""

from typing import List

from .base import BaseScorer, ScorerResult


class UncertaintyScorer(BaseScorer):
    """
    Uncertainty scorer.

    Combines multiple uncertainty factors into a single score.
    Higher score = more uncertainty = more risky.
    """

    # Weights for each uncertainty factor
    FACTOR_WEIGHTS = {
        'judge_std': 0.25,
        'confidence_gap': 0.25,
        'tool_error': 0.25,
        'evidence_gap': 0.25
    }

    def __init__(self, weight: float = 0.05):
        """
        Initialize UncertaintyScorer.

        Args:
            weight: Weight for this scorer in composite calculation (default: 0.05)
        """
        super().__init__(weight=weight, name="uncertainty")

    def score(
        self,
        judge_std: float = 0.0,
        self_confidence: float = 0.0,
        tool_error_rate: float = 0.0,
        evidence_gap: float = 0.0
    ) -> ScorerResult:
        """
        Calculate composite uncertainty score.

        Args:
            judge_std: Standard deviation of judge scores (disagreement indicator)
            self_confidence: Model's self-confidence score (0-1, higher = more confident)
            tool_error_rate: Rate of tool errors (0-1)
            evidence_gap: Evidence gap measure (0-1)

        Returns:
            ScorerResult with uncertainty score
        """
        # Normalize inputs to [0, 1] range
        norm_judge_std = min(judge_std, 1.0)
        norm_confidence_gap = 1.0 - min(max(self_confidence, 0.0), 1.0)
        norm_tool_error = min(tool_error_rate, 1.0)
        norm_evidence_gap = min(evidence_gap, 1.0)

        # Weighted average of uncertainty factors
        uncertainty_score = (
            norm_judge_std * self.FACTOR_WEIGHTS['judge_std'] +
            norm_confidence_gap * self.FACTOR_WEIGHTS['confidence_gap'] +
            norm_tool_error * self.FACTOR_WEIGHTS['tool_error'] +
            norm_evidence_gap * self.FACTOR_WEIGHTS['evidence_gap']
        )

        weighted = uncertainty_score * self.weight

        factors = self._collect_significant_factors(
            norm_judge_std, norm_confidence_gap, norm_tool_error, norm_evidence_gap,
            judge_std, tool_error_rate, evidence_gap
        )

        explanation = f"Uncertainty score: {uncertainty_score:.4f}"
        if factors:
            explanation += f" (factors: {', '.join(factors)})"

        return ScorerResult(
            name=self.name,
            score=uncertainty_score,
            weight=self.weight,
            weighted_score=weighted,
            top_exemplar_refs=[],
            explanation=explanation
        )

    def _collect_significant_factors(
        self,
        norm_judge_std: float,
        norm_confidence_gap: float,
        norm_tool_error: float,
        norm_evidence_gap: float,
        raw_judge_std: float,
        raw_tool_error: float,
        raw_evidence_gap: float
    ) -> List[str]:
        """
        Collect factors that exceed significance threshold.

        Args:
            norm_*: Normalized factor values
            raw_*: Raw factor values for display

        Returns:
            List of factor description strings
        """
        factors = []
        if norm_judge_std > 0.1:
            factors.append(f"judge_std={raw_judge_std:.4f}")
        if norm_confidence_gap > 0.1:
            factors.append(f"confidence_gap={norm_confidence_gap:.4f}")
        if norm_tool_error > 0.1:
            factors.append(f"tool_error_rate={raw_tool_error:.4f}")
        if norm_evidence_gap > 0.1:
            factors.append(f"evidence_gap={raw_evidence_gap:.4f}")
        return factors