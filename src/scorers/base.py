"""
Base class for all scorers.

Provides common functionality for input validation, result creation,
and reference extraction.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class ScorerResult:
    """Individual scorer output."""
    name: str
    score: float
    weight: float
    weighted_score: float
    top_exemplar_refs: List[str]
    explanation: str


class BaseScorer(ABC):
    """
    Abstract base class for all scorers.

    Provides common methods for input validation, result creation,
    and reference extraction to reduce code duplication.
    """

    def __init__(self, weight: float, name: str):
        """
        Initialize base scorer.

        Args:
            weight: Weight applied to this scorer's score in composite calculation
            name: Unique identifier for this scorer
        """
        self.weight = weight
        self.name = name

    def _validate_inputs(self, *values: Optional[Any]) -> bool:
        """
        Check if all required inputs are present and valid.

        Args:
            *values: Variable number of values to validate

        Returns:
            True if all values are truthy (non-empty, non-None), False otherwise
        """
        for value in values:
            if value is None:
                return False
            if isinstance(value, (list, dict, str)) and len(value) == 0:
                return False
        return True

    def _create_empty_result(self, reason: str) -> ScorerResult:
        """
        Create a result for missing or invalid inputs.

        Args:
            reason: Explanation for why the result is empty

        Returns:
            ScorerResult with zero scores and empty refs
        """
        return ScorerResult(
            name=self.name,
            score=0.0,
            weight=self.weight,
            weighted_score=0.0,
            top_exemplar_refs=[],
            explanation=reason
        )

    def _get_top_refs(
        self,
        docs: Optional[List[Dict]],
        indices: List[int],
        max_refs: int = 5
    ) -> List[str]:
        """
        Extract document IDs from top matching documents.

        Args:
            docs: List of document dictionaries with 'doc_id' field
            indices: Indices of documents to extract
            max_refs: Maximum number of refs to return

        Returns:
            List of document IDs, limited to max_refs
        """
        if not docs:
            return []

        refs = []
        for idx in indices[:max_refs]:
            if idx < len(docs):
                doc_id = docs[idx].get('doc_id', '')
                if doc_id:
                    refs.append(doc_id)
        return refs

    def _format_explanation(
        self,
        base_msg: str,
        score: float,
        details: Optional[List[str]] = None
    ) -> str:
        """
        Format explanation string with optional details.

        Args:
            base_msg: Base explanation message
            score: Score value to include
            details: Optional list of additional details to append

        Returns:
            Formatted explanation string
        """
        explanation = f"{base_msg}: {score:.4f}"
        if details:
            explanation += f". {', '.join(details)}"
        return explanation

    @abstractmethod
    def score(self, *args, **kwargs) -> ScorerResult:
        """
        Calculate score based on input parameters.

        Must be implemented by each scorer.

        Returns:
            ScorerResult with score, weight, and explanation
        """
        pass