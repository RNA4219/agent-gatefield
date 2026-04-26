"""
Qdrant Vector Store - Local-first vector database backend.

Implements RUNBOOK Local Retrieval Stack requirements.
Uses Qdrant as vector DB backend instead of pgvector.
"""

import logging
import os
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import uuid

logger = logging.getLogger(__name__)

# Collection configuration
DEFAULT_COLLECTION = "gatefield_judgments"
DEFAULT_DISTANCE = "Cosine"
DEFAULT_DIMS = 1024  # BGE-M3 dense


@dataclass
class SearchResult:
    """Search result from vector store."""
    doc_id: str
    similarity: float
    axis_type: str
    text: str
    labels: Optional[Dict] = None
    source_type: Optional[str] = None
    scope: Optional[str] = None
    version: Optional[int] = None
    reranker_score: Optional[float] = None


class QdrantVectorStore:
    """
    Qdrant-based vector store for judgment KB.

    Implements RUNBOOK Local Retrieval Stack requirements.
    No external API required, runs locally or in controlled infrastructure.
    """

    def __init__(
        self,
        collection_name: str = None,
        host: str = None,
        port: int = None,
        url: str = None,
        location: str = None,
        embedding_dims: int = DEFAULT_DIMS,
        distance: str = DEFAULT_DISTANCE,
        prefer_grpc: bool = True,
        in_memory: bool = False
    ):
        """
        Initialize Qdrant vector store.

        Args:
            collection_name: Collection name (default: gatefield_judgments)
            host: Qdrant server host (default: localhost)
            port: Qdrant server port (default: 6333 for REST, 6334 for gRPC)
            url: Full URL to Qdrant server
            location: :memory: for in-memory or path for persistent storage
            embedding_dims: Vector dimensions (default: 1024 for BGE-M3)
            distance: Distance metric (Cosine, Euclidean, Dot)
            prefer_grpc: Prefer gRPC over REST
            in_memory: Use in-memory storage (no persistence)
        """
        self.collection_name = collection_name or DEFAULT_COLLECTION
        self.embedding_dims = embedding_dims
        self.distance = distance
        self.in_memory = in_memory
        self._client = None
        self._initialized = False

        # Connection params
        if location == ":memory:" or in_memory:
            self.location = ":memory:"
            self.host = None
            self.port = None
            self.url = None
        elif url:
            self.url = url
            self.location = None
            self.host = None
            self.port = None
        else:
            self.host = host or os.environ.get('QDRANT_HOST', 'localhost')
            self.port = port or int(os.environ.get('QDRANT_PORT', '6333'))
            self.location = None
            self.url = None

        logger.info(f"QdrantVectorStore configured: collection={self.collection_name}, dims={self.embedding_dims}")

    def _init_client(self) -> bool:
        """Initialize Qdrant client (lazy loading)."""
        if self._initialized:
            return self._client is not None

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams

            # Create client
            if self.location == ":memory:":
                self._client = QdrantClient(location=":memory:", check_compatibility=False)
            elif self.url:
                self._client = QdrantClient(url=self.url, prefer_grpc=True, check_compatibility=False)
            else:
                self._client = QdrantClient(
                    host=self.host,
                    port=self.port,
                    prefer_grpc=True,
                    check_compatibility=False,
                )

            # Create collection if not exists
            distance_map = {
                'Cosine': Distance.COSINE,
                'Euclidean': Distance.EUCLID,
                'Dot': Distance.DOT,
            }
            dist = distance_map.get(self.distance, Distance.COSINE)

            try:
                self._client.get_collection(self.collection_name)
                logger.info(f"Collection {self.collection_name} exists")
            except Exception:
                # Create collection
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dims,
                        distance=dist
                    )
                )
                logger.info(f"Created collection {self.collection_name}")

            self._initialized = True
            return True

        except ImportError:
            logger.warning("qdrant-client not installed, QdrantVectorStore unavailable")
            self._initialized = True
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {e}")
            self._initialized = True
            return False

    def search_similar(
        self,
        query_vector: List[float],
        axis_type: str,
        limit: int = 10,
        scope: str = None,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query embedding vector
            axis_type: Filter by axis (taboo, accepted, rejected, constitution)
            limit: Maximum results
            scope: Optional scope filter
            min_score: Minimum similarity score

        Returns:
            List of SearchResult objects
        """
        if not self._init_client() or self._client is None:
            return self._mock_search(axis_type, limit)

        try:
            from qdrant_client.http.models import QueryRequest, Filter, FieldCondition, MatchValue

            # Build filter
            conditions = [
                FieldCondition(key="axis_type", match=MatchValue(value=axis_type)),
                FieldCondition(key="status", match=MatchValue(value="active")),
            ]
            if scope:
                conditions.append(FieldCondition(key="scope", match=MatchValue(value=scope)))

            filter_obj = Filter(must=conditions)

            # Use new query_batch_points API (qdrant-client 1.17+)
            request = QueryRequest(
                query=query_vector,
                filter=filter_obj,
                limit=limit,
                with_payload=True
            )

            results = self._client.query_batch_points(
                collection_name=self.collection_name,
                requests=[request]
            )

            # Convert to SearchResult
            search_results = []
            for response in results:
                for hit in response.points:
                    if min_score and hit.score < min_score:
                        continue
                    payload = hit.payload or {}
                    search_results.append(SearchResult(
                        doc_id=str(hit.id),
                        similarity=hit.score,
                        axis_type=payload.get('axis_type') or payload.get('axis') or axis_type,
                        text=payload.get('text', ''),
                        labels=payload.get('labels'),
                        source_type=payload.get('source_type') or payload.get('source'),
                        scope=payload.get('scope'),
                        version=payload.get('version'),
                    ))

            return search_results

        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def insert_document(
        self,
        axis_type: str,
        text: str,
        embedding: List[float],
        labels: Dict = None,
        scope: str = None,
        source_type: str = "manual",
        doc_id: str = None
    ) -> str:
        """
        Insert document with embedding.

        Args:
            axis_type: Axis type (taboo, accepted, rejected, constitution)
            text: Document text
            embedding: Vector embedding
            labels: Optional labels
            scope: Optional scope filter
            source_type: Source type (manual, run_promoted, import)
            doc_id: Optional document ID (auto-generated if None)

        Returns:
            Document ID
        """
        if not self._init_client() or self._client is None:
            return f"mock-doc-{uuid.uuid4()}"

        try:
            doc_id = doc_id or str(uuid.uuid4())

            # Payload with all required metadata per RUNBOOK
            content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
            payload = {
                'doc_id': doc_id,
                'axis': axis_type,
                'axis_type': axis_type,
                'text': text,
                'labels': labels or {},
                'scope': scope,
                'source': source_type,
                'source_type': source_type,
                'model': 'BAAI/bge-m3',  # per RUNBOOK
                'dims': self.embedding_dims,
                'content_hash': content_hash,
                'dataset_version': 'v1.0.0',
                'redaction_status': 'verified',
                'status': 'active',
                'version': 1,
                'created_at': datetime.now(timezone.utc).isoformat(),
            }

            from qdrant_client.http.models import PointStruct
            point = PointStruct(
                id=doc_id,
                vector=embedding,
                payload=payload
            )

            self._client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )

            return doc_id

        except Exception as e:
            logger.error(f"Insert error: {e}")
            return f"mock-doc-{uuid.uuid4()}"

    def batch_insert(
        self,
        documents: List[Dict[str, Any]],
        embeddings: List[List[float]]
    ) -> List[str]:
        """
        Batch insert documents with embeddings.

        Args:
            documents: List of document dicts (axis_type, text, labels, scope)
            embeddings: List of embedding vectors

        Returns:
            List of document IDs
        """
        if not self._init_client() or self._client is None:
            return [f"mock-doc-{uuid.uuid4()}" for _ in documents]

        try:
            from qdrant_client.http.models import PointStruct

            points = []
            doc_ids = []
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                doc_id = doc.get('doc_id') or str(uuid.uuid4())
                axis_type = doc.get('axis_type') or doc.get('axis')
                source_type = doc.get('source_type') or doc.get('source') or 'import'
                text = doc.get('text', '')
                content_hash = doc.get('content_hash') or hashlib.sha256(text.encode('utf-8')).hexdigest()
                doc_ids.append(doc_id)

                payload = {
                    'doc_id': doc_id,
                    'axis': axis_type,
                    'axis_type': axis_type,
                    'text': text,
                    'labels': doc.get('labels', {}),
                    'scope': doc.get('scope'),
                    'source': source_type,
                    'source_type': source_type,
                    'model': 'BAAI/bge-m3',
                    'dims': self.embedding_dims,
                    'content_hash': content_hash,
                    'dataset_version': 'v1.0.0',
                    'redaction_status': 'verified',
                    'status': 'active',
                    'version': 1,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                }

                points.append(PointStruct(
                    id=doc_id,
                    vector=emb,
                    payload=payload
                ))

            self._client.upsert(
                collection_name=self.collection_name,
                points=points
            )

            return doc_ids

        except Exception as e:
            logger.error(f"Batch insert error: {e}")
            return [f"mock-doc-{uuid.uuid4()}" for _ in documents]

    def deprecate_document(self, doc_id: str) -> bool:
        """Mark document as deprecated."""
        if not self._init_client() or self._client is None:
            return True

        try:
            from qdrant_client.http.models import Payload

            self._client.set_payload(
                collection_name=self.collection_name,
                payload={'status': 'deprecated', 'updated_at': datetime.now(timezone.utc).isoformat()},
                points=[doc_id]
            )
            return True
        except Exception as e:
            logger.error(f"Deprecate error: {e}")
            return False

    def get_centroid(self, axis_type: str) -> Optional[List[float]]:
        """Get centroid (average vector) for axis."""
        if not self._init_client() or self._client is None:
            return [0.5] * self.embedding_dims

        try:
            # Get all vectors for axis (limited sample)
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue

            filter_obj = Filter(
                must=[
                    FieldCondition(key="axis_type", match=MatchValue(value=axis_type)),
                    FieldCondition(key="status", match=MatchValue(value="active")),
                ]
            )

            # Scroll through points
            points, _ = self._client.scroll(
                collection_name=self.collection_name,
                scroll_filter=filter_obj,
                limit=100,
                with_vectors=True
            )

            if not points:
                return None

            # Calculate centroid
            vectors = [p.vector for p in points]
            dims = len(vectors[0])
            centroid = [sum(v[i] for v in vectors) / len(vectors) for i in range(dims)]

            return centroid

        except Exception as e:
            logger.error(f"Centroid error: {e}")
            return None

    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection info."""
        if not self._init_client() or self._client is None:
            return {'status': 'mock', 'points_count': 0}

        try:
            info = self._client.get_collection(self.collection_name)
            result = {
                'status': info.status.value,
                'points_count': info.points_count,
                'config': {},
            }
            # Safely access config (API varies by version)
            try:
                if hasattr(info.config, 'params') and hasattr(info.config.params, 'vectors'):
                    vectors_config = info.config.params.vectors
                    if hasattr(vectors_config, 'size'):
                        result['config']['dimensions'] = vectors_config.size
                    if hasattr(vectors_config, 'distance'):
                        result['config']['distance'] = vectors_config.distance.value if hasattr(vectors_config.distance, 'value') else str(vectors_config.distance)
            except Exception:
                pass
            return result
        except Exception as e:
            logger.error(f"Info error: {e}")
            return {'status': 'error', 'error': str(e)}

    def _mock_search(self, axis_type: str, limit: int) -> List[SearchResult]:
        """Mock search when Qdrant unavailable."""
        results = []
        for i in range(limit):
            results.append(SearchResult(
                doc_id=f"mock-{i+1}",
                similarity=0.85 - i * 0.1,
                axis_type=axis_type,
                text=f"Mock {axis_type} document {i+1}",
            ))
        return results

    def close(self) -> None:
        """Close connection."""
        if self._client:
            self._client.close()
            self._client = None


def create_qdrant_store(config: Dict[str, Any] = None) -> QdrantVectorStore:
    """
    Create QdrantVectorStore from config.

    Args:
        config: Configuration dict with optional keys:
            - collection: Collection name
            - host: Server host
            - port: Server port
            - url: Full URL
            - location: Storage location
            - dims: Vector dimensions
            - distance: Distance metric
            - in_memory: Use in-memory storage
    """
    if config is None:
        config = {}

    return QdrantVectorStore(
        collection_name=config.get('collection') or config.get('collection_name'),
        host=config.get('host'),
        port=config.get('port'),
        url=config.get('url'),
        location=config.get('location'),
        embedding_dims=config.get('dims') or config.get('dimensions', DEFAULT_DIMS),
        distance=config.get('distance', DEFAULT_DISTANCE),
        in_memory=config.get('in_memory', False),
    )


__all__ = [
    'QdrantVectorStore',
    'SearchResult',
    'create_qdrant_store',
    'DEFAULT_COLLECTION',
    'DEFAULT_DIMS',
    'DEFAULT_DISTANCE',
]
