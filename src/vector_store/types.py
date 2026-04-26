"""
Type definitions for vector_store module.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class SearchResult:
    """Search result from similarity search"""
    doc_id: str
    similarity: float
    axis_type: str
    text: str
    labels: Optional[Dict] = None
    source_type: Optional[str] = None


__all__ = ['SearchResult']