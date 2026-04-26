"""
VectorStore - pgvector client for judgment KB.
"""

import json
import logging
from typing import Optional, List, Dict, Any

from .types import SearchResult

logger = logging.getLogger(__name__)


class VectorStore:
    """pgvector client for judgment KB"""

    def __init__(self, connection_string: str):
        self.conn_str = connection_string
        self.conn = None
        self._connect()

    def _connect(self) -> None:
        """Establish database connection"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            logger.warning("psycopg2 not available, VectorStore will operate in mock mode")
            return

        try:
            # Parse connection string and use keyword args to avoid encoding issues
            # on Windows with Japanese locale
            parts = self._parse_connection_string(self.conn_str)
            self.conn = pg.psycopg2.connect(**parts)
            # Set client encoding to UTF-8 to avoid Windows locale issues
            self.conn.set_client_encoding('UTF8')
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def _parse_connection_string(self, conn_str: str) -> dict:
        """Parse PostgreSQL connection string into keyword arguments."""
        # Handle postgresql://user:pass@host:port/db format
        if conn_str.startswith('postgresql://'):
            conn_str = conn_str[13:]  # Remove prefix

        # Split into host and auth parts
        if '@' in conn_str:
            auth_part, host_part = conn_str.split('@', 1)
            if ':' in auth_part:
                user, password = auth_part.split(':', 1)
            else:
                user = auth_part
                password = ''
        else:
            user = None
            password = None
            host_part = conn_str

        # Parse host:port/db
        if '/' in host_part:
            host_db = host_part.split('/', 1)
            host_port = host_db[0]
            database = host_db[1] if len(host_db) > 1 else ''
        else:
            host_port = host_part
            database = ''

        if ':' in host_port:
            host, port = host_port.split(':', 1)
            port = int(port)
        else:
            host = host_port
            port = 5432

        result = {'host': host}
        if user:
            result['user'] = user
        if password:
            result['password'] = password
        if database:
            result['database'] = database
        if port:
            result['port'] = port

        return result

    def _ensure_connection(self) -> None:
        """Ensure connection is alive, reconnect if needed"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 not installed")

        if self.conn is None or self.conn.closed:
            self._connect()

    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def search_similar(
        self,
        query_vector: List[float],
        axis_type: str,
        limit: int = 10,
        scope: str = None
    ) -> List[SearchResult]:
        """Similarity search using cosine distance via pgvector"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return self._mock_search(axis_type, limit)

        self._ensure_connection()
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        with self.conn.cursor(cursor_factory=pg.RealDictCursor) as cur:
            cur.execute("SELECT * FROM search_similar(%s, %s, %s)", (vector_str, axis_type, limit))
            rows = cur.fetchall()
            return [
                SearchResult(
                    doc_id=str(row['doc_id']),
                    similarity=row['similarity'],
                    axis_type=row['axis_type'],
                    text=row['text'],
                    labels=None,
                    source_type=None
                ) for row in rows
            ]

    def search_similar_with_docs(
        self,
        query_vector: List[float],
        axis_type: str,
        limit: int = 10
    ) -> List[Dict]:
        """Similarity search with full document metadata"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return []

        self._ensure_connection()
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        with self.conn.cursor(cursor_factory=pg.RealDictCursor) as cur:
            cur.execute("""
                SELECT jd.doc_id, jd.axis_type, jd.text, jd.source_type,
                       jd.version, jd.labels, jd.scope, jd.status,
                       1 - (je.embedding <=> %s::vector) as similarity
                FROM judgment_embeddings je
                JOIN judgment_documents jd ON je.doc_id = jd.doc_id
                WHERE jd.axis_type = %s AND jd.status = 'active' AND je.valid_to IS NULL
                ORDER BY je.embedding <=> %s::vector LIMIT %s
            """, (vector_str, axis_type, vector_str, limit))
            return [dict(row) for row in cur.fetchall()]

    def insert_document(
        self,
        axis_type: str,
        text: str,
        source_type: str = 'manual',
        scope: str = None,
        labels: Dict = None
    ) -> str:
        """Insert new judgment document, returns doc_id"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return "mock-doc-id"

        self._ensure_connection()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO judgment_documents (axis_type, text, source_type, scope, labels)
                VALUES (%s, %s, %s, %s, %s) RETURNING doc_id
            """, (axis_type, text, source_type, scope, json.dumps(labels) if labels else '{}'))
            doc_id = cur.fetchone()[0]
            self.conn.commit()
            return str(doc_id)

    def insert_embedding(
        self,
        doc_id: str,
        model: str,
        dims: int,
        embedding: List[float],
        content_hash: str
    ) -> str:
        """Insert new embedding (append-only versioning), returns embed_id"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return "mock-embed-id"

        self._ensure_connection()
        vector_str = "[" + ",".join(str(v) for v in embedding) + "]"

        with self.conn.cursor() as cur:
            cur.execute("UPDATE judgment_embeddings SET valid_to = NOW() WHERE doc_id = %s AND valid_to IS NULL", (doc_id,))
            cur.execute("""
                INSERT INTO judgment_embeddings (doc_id, model, dims, embedding, content_hash)
                VALUES (%s, %s, %s, %s::vector, %s) RETURNING embed_id
            """, (doc_id, model, dims, vector_str, content_hash))
            embed_id = cur.fetchone()[0]
            self.conn.commit()
            return str(embed_id)

    def batch_insert_embeddings(
        self,
        doc_ids: List[str],
        model: str,
        dims: int,
        embeddings: List[List[float]],
        content_hashes: List[str]
    ) -> List[str]:
        """Batch insert embeddings for efficiency"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return ["mock-embed-id"] * len(doc_ids)

        self._ensure_connection()
        data = [
            (doc_id, model, dims, "[" + ",".join(str(v) for v in emb) + "]", hash_val)
            for doc_id, emb, hash_val in zip(doc_ids, embeddings, content_hashes)
        ]

        with self.conn.cursor() as cur:
            cur.execute("UPDATE judgment_embeddings SET valid_to = NOW() WHERE doc_id = ANY(%s) AND valid_to IS NULL", (doc_ids,))
            result = pg.execute_values(
                cur,
                "INSERT INTO judgment_embeddings (doc_id, model, dims, embedding, content_hash) VALUES %s RETURNING embed_id",
                data,
                template="(%s, %s, %s, %s::vector, %s)",
                fetch=True
            )
            embed_ids = [row[0] for row in result]
            self.conn.commit()
            return [str(eid) for eid in embed_ids]

    def deprecate_embedding(self, doc_id: str) -> None:
        """Mark old embedding as deprecated"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return
        self._ensure_connection()
        with self.conn.cursor() as cur:
            cur.execute("UPDATE judgment_embeddings SET valid_to = NOW() WHERE doc_id = %s AND valid_to IS NULL", (doc_id,))
            self.conn.commit()

    def deprecate_document(self, doc_id: str) -> None:
        """Mark document as deprecated"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return
        self._ensure_connection()
        with self.conn.cursor() as cur:
            cur.execute("UPDATE judgment_documents SET status = 'deprecated', updated_at = NOW() WHERE doc_id = %s", (doc_id,))
            self.conn.commit()

    def get_active_embeddings(self, axis_type: str, scope: str = None) -> List[Dict]:
        """Get all active embeddings for an axis"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return []
        self._ensure_connection()
        with self.conn.cursor(cursor_factory=pg.RealDictCursor) as cur:
            if scope:
                cur.execute("""
                    SELECT je.embed_id, je.doc_id, je.model, je.dims, je.embedding,
                           jd.text, jd.labels, jd.scope
                    FROM judgment_embeddings je
                    JOIN judgment_documents jd ON je.doc_id = jd.doc_id
                    WHERE jd.axis_type = %s AND jd.status = 'active' AND jd.scope = %s AND je.valid_to IS NULL
                """, (axis_type, scope))
            else:
                cur.execute("""
                    SELECT je.embed_id, je.doc_id, je.model, je.dims, je.embedding,
                           jd.text, jd.labels, jd.scope
                    FROM judgment_embeddings je
                    JOIN judgment_documents jd ON je.doc_id = jd.doc_id
                    WHERE jd.axis_type = %s AND jd.status = 'active' AND je.valid_to IS NULL
                """, (axis_type,))
            results = []
            for row in cur.fetchall():
                emb_data = dict(row)
                if emb_data['embedding']:
                    emb_str = str(emb_data['embedding'])
                    emb_data['embedding'] = [float(x) for x in emb_str.strip('[]').split(',')]
                results.append(emb_data)
            return results

    def insert_state_vector(self, state_vector: Dict) -> None:
        """Store state vector for a run"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return
        self._ensure_connection()
        run_id = state_vector.get('run_id')
        semantic = state_vector.get('semantic', {})
        semantic_embedding = semantic.get('vector', [])
        vector_str = "[" + ",".join(str(v) for v in semantic_embedding) + "]" if semantic_embedding else None
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO state_vectors
                (run_id, artifact_id, semantic_embedding, rule_json, test_json, risk_json,
                 history_json, uncertainty_json, context_json, trajectory_json)
                VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    semantic_embedding = EXCLUDED.semantic_embedding,
                    rule_json = EXCLUDED.rule_json, test_json = EXCLUDED.test_json,
                    risk_json = EXCLUDED.risk_json, history_json = EXCLUDED.history_json,
                    uncertainty_json = EXCLUDED.uncertainty_json, context_json = EXCLUDED.context_json,
                    trajectory_json = EXCLUDED.trajectory_json, created_at = NOW()
            """, (
                run_id, state_vector.get('artifact_id'), vector_str,
                json.dumps(state_vector.get('rule_violation', {})),
                json.dumps(state_vector.get('test_evidence', {})),
                json.dumps(state_vector.get('risk', {})),
                json.dumps(state_vector.get('historical_decision', {})),
                json.dumps(state_vector.get('uncertainty', {})),
                json.dumps(state_vector.get('context', {})),
                json.dumps(state_vector.get('trajectory', {}))
            ))
            self.conn.commit()

    def get_state_vector(self, run_id: str) -> Optional[Dict]:
        """Get state vector for a run"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return None
        self._ensure_connection()
        with self.conn.cursor(cursor_factory=pg.RealDictCursor) as cur:
            cur.execute("SELECT * FROM state_vectors WHERE run_id = %s", (run_id,))
            row = cur.fetchone()
            if row:
                result = dict(row)
                if result['semantic_embedding']:
                    emb_str = str(result['semantic_embedding'])
                    result['semantic_embedding'] = [float(x) for x in emb_str.strip('[]').split(',')]
                return result
            return None

    def get_centroid(self, axis_type: str) -> List[float]:
        """Calculate centroid for an axis"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return [0.5] * 1536
        self._ensure_connection()
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(embedding) as centroid
                FROM judgment_embeddings je
                JOIN judgment_documents jd ON je.doc_id = jd.doc_id
                WHERE jd.axis_type = %s AND jd.status = 'active' AND je.valid_to IS NULL
            """, (axis_type,))
            row = cur.fetchone()
            if row and row[0]:
                return [float(x) for x in str(row[0]).strip('[]').split(',')]
            return []

    def insert_gate_decision(self, run_id: str, decision: Dict, threshold_version: str) -> str:
        """Insert gate decision, returns decision_id"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return "mock-decision-id"
        self._ensure_connection()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO gate_decisions (run_id, composite_score, state, reasons_json, action_type, threshold_version)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING decision_id
            """, (run_id, decision.get('composite_score'), decision.get('decision'),
                  json.dumps(decision.get('factors', [])), decision.get('action_type'), threshold_version))
            decision_id = cur.fetchone()[0]
            self.conn.commit()
            return str(decision_id)

    def get_gate_decision(self, decision_id: str) -> Optional[Dict]:
        """Get gate decision by ID"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return None
        self._ensure_connection()
        with self.conn.cursor(cursor_factory=pg.RealDictCursor) as cur:
            cur.execute("SELECT * FROM gate_decisions WHERE decision_id = %s", (decision_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def insert_static_gate_result(self, run_id: str, gate_name: str, status: str,
                                   severity: str = None, evidence_ref: str = None) -> str:
        """Insert static gate result"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return "mock-gate-id"
        self._ensure_connection()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO static_gate_results (run_id, gate_name, severity, status, evidence_ref)
                VALUES (%s, %s, %s, %s, %s) RETURNING gate_result_id
            """, (run_id, gate_name, severity, status, evidence_ref))
            gate_id = cur.fetchone()[0]
            self.conn.commit()
            return str(gate_id)

    def get_static_gate_results(self, run_id: str) -> List[Dict]:
        """Get all static gate results for a run"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return []
        self._ensure_connection()
        with self.conn.cursor(cursor_factory=pg.RealDictCursor) as cur:
            cur.execute("SELECT * FROM static_gate_results WHERE run_id = %s", (run_id,))
            return [dict(row) for row in cur.fetchall()]

    def insert_audit_event(self, trace_id: str, span_id: str, run_id: str,
                           event_type: str, actor: str, payload_hash: str = None,
                           retention_class: str = 'audit') -> str:
        """Insert audit event"""
        import src.vector_store._psycopg2 as pg
        if not pg.PSYCOPG2_AVAILABLE:
            return "mock-event-id"
        self._ensure_connection()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_events (trace_id, span_id, run_id, event_type, actor, payload_hash, retention_class)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING event_id
            """, (trace_id, span_id, run_id, event_type, actor, payload_hash, retention_class))
            event_id = cur.fetchone()[0]
            self.conn.commit()
            return str(event_id)

    def _mock_search(self, axis_type: str, limit: int) -> List[SearchResult]:
        """Mock search for testing without database"""
        return [
            SearchResult(
                doc_id=f"mock-{axis_type}-1",
                similarity=0.85,
                axis_type=axis_type,
                text=f"Mock {axis_type} example",
                labels={},
                source_type="mock"
            )
        ]


__all__ = ['VectorStore']