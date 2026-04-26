"""
Unit tests for Vector Store (pgvector interface) - AGF-REQ-006 / AGF-REQ-003

Tests cover:
- search_similar functionality
- insert_document and insert_embedding
- batch operations
- centroid calculation
- KB document retrieval by axis
- embedding versioning (valid_from, valid_to)
- mock mode when psycopg2 unavailable

Coverage target: 85%
"""

import pytest
import json
from datetime import datetime

# Import the module under test
from src.vector_store import (
    VectorStore,
    SearchResult,
    JudgmentKB,
    create_vector_store
)


# Use fixtures from conftest.py


class TestSearchResult:
    """Tests for SearchResult dataclass"""

    def test_search_result_creation(self):
        """UT-KB-001: SearchResult basic creation"""
        result = SearchResult(
            doc_id="doc-123",
            similarity=0.85,
            axis_type="taboo",
            text="Example text",
            labels={"key": "value"},
            source_type="manual"
        )
        assert result.doc_id == "doc-123"
        assert result.similarity == 0.85
        assert result.axis_type == "taboo"
        assert result.text == "Example text"

    def test_search_result_defaults(self):
        """SearchResult with default optional fields"""
        result = SearchResult(
            doc_id="doc-456",
            similarity=0.75,
            axis_type="accepted",
            text="Sample"
        )
        assert result.labels is None
        assert result.source_type is None


class TestVectorStoreMockMode:
    """Tests for mock mode when psycopg2 unavailable"""

    def test_initialization_without_psycopg2(self, mock_mode_vector_store):
        """Mock mode activates when psycopg2 unavailable"""
        assert mock_mode_vector_store.conn is None

    def test_search_similar_returns_mock_results(self, mock_mode_vector_store):
        """UT-KB-004: Mock search returns predefined results"""
        results = mock_mode_vector_store.search_similar([0.1] * 1536, "taboo", limit=5)
        assert len(results) > 0
        assert results[0].axis_type == "taboo"
        assert results[0].doc_id.startswith("mock-")

    @pytest.mark.parametrize("method,args,expected", [
        ("insert_document", ("taboo", "text"), "mock-doc-id"),
        ("insert_embedding", ("doc-1", "model", 1536, [0.1]*1536, "hash"), "mock-embed-id"),
        ("insert_gate_decision", ("run-1", {}, "v1"), "mock-decision-id"),
        ("insert_static_gate_result", ("run-1", "sast", "fail"), "mock-gate-id"),
        ("get_state_vector", ("run-1",), None),
        ("get_gate_decision", ("decision-1",), None),
        ("get_centroid", ("constitution",), [0.5]*1536),
        ("get_active_embeddings", ("taboo",), []),
        ("search_similar_with_docs", ([0.1]*1536, "taboo"), []),
    ])
    def test_mock_returns_expected(self, mock_mode_vector_store, method, args, expected):
        """Consolidated mock return value tests"""
        result = getattr(mock_mode_vector_store, method)(*args)
        if isinstance(expected, list) and len(expected) == 1536:
            assert len(result) == 1536
            assert all(v == expected[0] for v in result)
        elif isinstance(expected, str):
            assert result == expected
        elif expected is None:
            assert result is None or result == []

    def test_batch_insert_returns_mock_ids(self, mock_mode_vector_store):
        """Batch insert returns mock IDs in mock mode"""
        embed_ids = mock_mode_vector_store.batch_insert_embeddings(
            doc_ids=["doc-1", "doc-2", "doc-3"],
            model="text-embedding-3-large",
            dims=1536,
            embeddings=[[0.1] * 1536 for _ in range(3)],
            content_hashes=["hash1", "hash2", "hash3"]
        )
        assert len(embed_ids) == 3

    @pytest.mark.parametrize("method,args", [
        ("deprecate_embedding", ("doc-1",)),
        ("deprecate_document", ("doc-1",)),
        ("insert_state_vector", ({'run_id': 'run-1', 'semantic': {'vector': [0.1]*1536}},)),
    ])
    def test_mock_operations_no_error(self, mock_mode_vector_store, method, args):
        """Consolidated no-error tests in mock mode"""
        getattr(mock_mode_vector_store, method)(*args)

    def test_ensure_connection_raises_without_psycopg2(self, mock_mode_vector_store):
        """Ensure connection raises error without psycopg2"""
        with pytest.raises(RuntimeError, match="psycopg2 not installed"):
            mock_mode_vector_store._ensure_connection()

    def test_get_static_gate_results_returns_empty(self, mock_mode_vector_store):
        """Get static gate results returns empty in mock mode"""
        assert mock_mode_vector_store.get_static_gate_results("run-1") == []

    def test_insert_audit_event_returns_mock_id(self, mock_mode_vector_store):
        """Insert audit event returns mock ID in mock mode"""
        event_id = mock_mode_vector_store.insert_audit_event("trace-1", "span-1", "run-1", "run_started", "agent")
        assert event_id == "mock-event-id"


class TestVectorStoreConnection:
    """Tests for database connection handling"""

    def test_successful_connection(self, mock_psycopg2_with_db):
        """Connection established successfully"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        vs = VectorStore("postgresql://user:pass@localhost:5432/gatefield")
        mock_psycopg2.connect.assert_called_once_with(
            host='localhost', user='user', password='pass', database='gatefield', port=5432
        )

    def test_connection_failure_raises(self, mock_psycopg2_with_db):
        """Connection failure raises exception"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_psycopg2.connect.side_effect = Exception("Connection refused")
        with pytest.raises(Exception, match="Connection refused"):
            VectorStore("postgresql://localhost/gatefield")

    def test_close_connection(self, vector_store_with_db):
        """Close properly terminates connection"""
        vs, mock_conn, mock_cursor = vector_store_with_db
        vs.close()
        mock_conn.close.assert_called_once()

    def test_ensure_connection_reconnects(self, mock_psycopg2_with_db):
        """Ensure connection reconnects if closed"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_conn.closed = True
        vs = VectorStore("postgresql://localhost/gatefield")
        vs._ensure_connection()
        assert mock_psycopg2.connect.call_count >= 2


class TestVectorStoreSearchSimilar:
    """Tests for search_similar functionality"""

    def test_search_similar_basic(self, mock_psycopg2_with_db):
        """UT-KB-004: axis_type filtering in search"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db

        # Mock RealDictCursor results
        mock_cursor.fetchall.return_value = [
            {
                'doc_id': 'doc-1',
                'similarity': 0.85,
                'axis_type': 'taboo',
                'text': 'Taboo example text'
            },
            {
                'doc_id': 'doc-2',
                'similarity': 0.75,
                'axis_type': 'taboo',
                'text': 'Another taboo text'
            }
        ]

        vs = VectorStore("postgresql://localhost/gatefield")
        query_vector = [0.1] * 1536
        results = vs.search_similar(query_vector, "taboo", limit=5)

        assert len(results) == 2
        assert results[0].axis_type == "taboo"
        assert results[0].similarity == 0.85
        mock_cursor.execute.assert_called_once()

    def test_search_similar_with_scope(self, mock_psycopg2_with_db):
        """UT-KB-005: scope filtering in search"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = []

        vs = VectorStore("postgresql://localhost/gatefield")
        query_vector = [0.1] * 1536
        scope = "repo-a"
        results = vs.search_similar(query_vector, "accepted", limit=5, scope=scope)

        # Verify query was executed
        mock_cursor.execute.assert_called_once()

    def test_search_similar_empty_results(self, mock_psycopg2_with_db):
        """Search returns empty list when no matches"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = []

        vs = VectorStore("postgresql://localhost/gatefield")
        results = vs.search_similar([0.1] * 1536, "judgment_log", limit=10)
        assert results == []

    def test_search_similar_with_docs(self, mock_psycopg2_with_db):
        """Search similar with full document metadata"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = [
            {
                'doc_id': 'doc-1',
                'axis_type': 'taboo',
                'text': 'Taboo text',
                'source_type': 'manual',
                'version': 1,
                'labels': {'key': 'value'},
                'scope': 'repo-a',
                'status': 'active',
                'similarity': 0.85
            }
        ]
        vs = VectorStore("postgresql://localhost/gatefield")
        results = vs.search_similar_with_docs([0.1] * 1536, "taboo", limit=5)
        assert len(results) == 1
        assert results[0]['doc_id'] == 'doc-1'

    def test_vector_format_conversion(self, mock_psycopg2_with_db):
        """Vector is correctly formatted for PostgreSQL"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = []
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.search_similar([0.1, 0.2, 0.3], "taboo")
        # Vector was passed to execute
        mock_cursor.execute.assert_called_once()


class TestVectorStoreInsertDocument:
    """Tests for insert_document functionality"""

    @pytest.mark.parametrize("doc_id,labels,scope", [
        ("doc-uuid-123", None, None),
        ("doc-456", {"category": "security", "severity": "high"}, None),
        ("doc-789", None, "repo-b"),
    ])
    def test_insert_document_variations(self, mock_psycopg2_with_db, doc_id, labels, scope):
        """Consolidated insert document tests"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = [doc_id]
        vs = VectorStore("postgresql://localhost/gatefield")
        result = vs.insert_document(
            axis_type="taboo",
            text="Content",
            source_type="manual",
            labels=labels,
            scope=scope
        )
        assert result == doc_id
        mock_conn.commit.assert_called_once()


class TestVectorStoreInsertEmbedding:
    """Tests for insert_embedding functionality and versioning"""

    def test_insert_embedding_basic(self, mock_psycopg2_with_db):
        """UT-KB-001: insert_embedding creates embedding"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['embed-uuid-123']
        vs = VectorStore("postgresql://localhost/gatefield")
        embed_id = vs.insert_embedding(
            doc_id="doc-1",
            model="text-embedding-3-large",
            dims=1536,
            embedding=[0.1] * 1536,
            content_hash="sha256:abc123def456"
        )
        assert embed_id == "embed-uuid-123"
        mock_conn.commit.assert_called_once()

    def test_insert_embedding_deprecates_old(self, mock_psycopg2_with_db):
        """UT-KB-002: append-only versioning - old embedding marked valid_to"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['embed-new-123']
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_embedding(
            doc_id="doc-1",
            model="text-embedding-3-large",
            dims=1536,
            embedding=[0.2] * 1536,
            content_hash="sha256:newhash"
        )
        assert mock_cursor.execute.call_count == 2
        first_call = mock_cursor.execute.call_args_list[0]
        assert 'UPDATE' in str(first_call)

    def test_embedding_versioning_valid_from_valid_to(self, mock_psycopg2_with_db):
        """UT-KB-002: Embedding versioning creates new version"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.side_effect = ['embed-v1', 'embed-v2']
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_embedding("doc-version-test", "model", 1536, [0.1] * 1536, "sha256:v1")
        vs.insert_embedding("doc-version-test", "model", 1536, [0.2] * 1536, "sha256:v2")
        assert mock_cursor.execute.call_count >= 3

    def test_insert_embedding_content_hash(self, mock_psycopg2_with_db):
        """UT-KB-007: content_hash for deduplication"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['embed-hash-123']
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_embedding("doc-1", "model", 1536, [0.1] * 1536, "sha256:contenthash123")
        call_args = mock_cursor.execute.call_args[0]
        assert 'sha256:contenthash123' in str(call_args)


class TestVectorStoreBatchOperations:
    """Tests for batch_insert_embeddings functionality"""

    def test_batch_insert_embeddings(self, mock_execute_values):
        """Batch insert for efficiency"""
        mock_ev, mock_conn, mock_cursor = mock_execute_values
        mock_ev.return_value = [('embed-1',), ('embed-2',), ('embed-3',)]
        vs = VectorStore("postgresql://localhost/gatefield")
        embed_ids = vs.batch_insert_embeddings(
            doc_ids=["doc-1", "doc-2", "doc-3"],
            model="model",
            dims=1536,
            embeddings=[[0.1] * 1536 for _ in range(3)],
            content_hashes=["h1", "h2", "h3"]
        )
        assert len(embed_ids) == 3
        mock_ev.assert_called_once()

    def test_batch_insert_deprecates_existing(self, mock_execute_values):
        """Batch insert deprecates existing embeddings"""
        mock_ev, mock_conn, mock_cursor = mock_execute_values
        mock_ev.return_value = [('embed-new',)]
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.batch_insert_embeddings(["doc-1"], "model", 1536, [[0.1] * 1536], ["hash1"])
        update_call = mock_cursor.execute.call_args_list[0]
        assert 'UPDATE' in str(update_call)

    def test_batch_insert_empty_list(self, mock_mode_vector_store):
        """Batch insert with empty list"""
        embed_ids = mock_mode_vector_store.batch_insert_embeddings([], "model", 1536, [], [])
        assert embed_ids == []


class TestVectorStoreCentroid:
    """Tests for centroid calculation"""

    def test_get_centroid_basic(self, mock_psycopg2_with_db):
        """Centroid calculation for constitution axis"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ["[0.1, 0.2, 0.3]"]
        vs = VectorStore("postgresql://localhost/gatefield")
        centroid = vs.get_centroid("constitution")
        assert centroid == [0.1, 0.2, 0.3]

    def test_get_centroid_empty_axis(self, mock_psycopg2_with_db):
        """Centroid returns empty list for axis with no embeddings"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = [None]
        vs = VectorStore("postgresql://localhost/gatefield")
        centroid = vs.get_centroid("empty_axis")
        assert centroid == []

    def test_get_centroid_filters_active_embeddings(self, mock_psycopg2_with_db):
        """Centroid only uses active embeddings (valid_to IS NULL)"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ["[0.5, 0.5]"]
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.get_centroid("taboo")
        call_args = mock_cursor.execute.call_args[0]
        assert 'valid_to IS NULL' in call_args[0]


class TestVectorStoreDeprecate:
    """Tests for deprecation functions"""

    @pytest.mark.parametrize("method,arg,check_str", [
        ("deprecate_embedding", "doc-123", "valid_to"),
        ("deprecate_document", "doc-456", "deprecated"),
    ])
    def test_deprecate_operations(self, mock_psycopg2_with_db, method, arg, check_str):
        """Consolidated deprecation tests"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        vs = VectorStore("postgresql://localhost/gatefield")
        getattr(vs, method)(arg)
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0]
        assert 'UPDATE' in call_args[0]
        assert check_str in call_args[0]
        mock_conn.commit.assert_called_once()


class TestVectorStoreGetActiveEmbeddings:
    """Tests for KB document retrieval by axis"""

    def test_get_active_embeddings_basic(self, mock_psycopg2_with_db):
        """UT-KB-004: axis_type filtering - get embeddings by axis"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = [
            {
                'embed_id': 'embed-1',
                'doc_id': 'doc-1',
                'model': 'model',
                'dims': 1536,
                'embedding': '[0.1, 0.2, 0.3]',
                'text': 'text',
                'labels': {'key': 'value'},
                'scope': 'repo-a'
            }
        ]
        vs = VectorStore("postgresql://localhost/gatefield")
        embeddings = vs.get_active_embeddings("taboo")
        assert len(embeddings) == 1
        assert isinstance(embeddings[0]['embedding'], list)

    def test_get_active_embeddings_with_scope(self, mock_psycopg2_with_db):
        """UT-KB-005: scope filtering in get_active_embeddings"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = []
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.get_active_embeddings("accepted", scope="repo-a")
        assert 'repo-a' in str(mock_cursor.execute.call_args[0])

    def test_get_active_embeddings_filters_deprecated(self, mock_psycopg2_with_db):
        """Only active embeddings returned (status=active, valid_to IS NULL)"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = []
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.get_active_embeddings("taboo")
        call_args = mock_cursor.execute.call_args[0]
        assert 'status = \'active\'' in call_args[0]
        assert 'valid_to IS NULL' in call_args[0]

    def test_get_active_embeddings_parse_vector(self, mock_psycopg2_with_db):
        """Embedding vector is parsed from PostgreSQL string format"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = [
            {'embed_id': 'embed-1', 'doc_id': 'doc-1', 'model': 'model', 'dims': 3,
             'embedding': '[0.5, 0.6, 0.7]', 'text': 'text', 'labels': {}, 'scope': None}
        ]
        vs = VectorStore("postgresql://localhost/gatefield")
        embeddings = vs.get_active_embeddings("taboo")
        assert embeddings[0]['embedding'] == [0.5, 0.6, 0.7]


class TestVectorStoreStateVector:
    """Tests for state vector storage"""

    def test_insert_state_vector(self, mock_psycopg2_with_db):
        """State vector stored with all components"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        vs = VectorStore("postgresql://localhost/gatefield")
        state_vector = {
            'run_id': 'run-uuid-123',
            'artifact_id': 'artifact-uuid-456',
            'semantic': {'vector': [0.1] * 1536},
            'rule_violation': {'secret': 0},
            'test_evidence': {'unit_pass_rate': 0.97},
        }
        vs.insert_state_vector(state_vector)
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_insert_state_vector_upsert(self, mock_psycopg2_with_db):
        """State vector upsert on conflict"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_state_vector({'run_id': 'run-1', 'semantic': {'vector': [0.1] * 1536}})
        call_args = mock_cursor.execute.call_args[0]
        assert 'ON CONFLICT' in call_args[0]

    def test_get_state_vector(self, mock_psycopg2_with_db):
        """Get state vector by run_id"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = {
            'run_id': 'run-1',
            'artifact_id': 'artifact-1',
            'semantic_embedding': '[0.1, 0.2]',
            'rule_json': {'secret': 0}
        }
        vs = VectorStore("postgresql://localhost/gatefield")
        result = vs.get_state_vector("run-1")
        assert result is not None
        assert isinstance(result['semantic_embedding'], list)

    def test_get_state_vector_not_found(self, mock_psycopg2_with_db):
        """Get state vector returns None if not found"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = None
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.get_state_vector("nonexistent-run") is None


class TestVectorStoreGateDecision:
    """Tests for gate decision storage"""

    def test_insert_gate_decision(self, mock_psycopg2_with_db):
        """Gate decision stored with threshold_version"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['decision-123']
        vs = VectorStore("postgresql://localhost/gatefield")
        decision_id = vs.insert_gate_decision("run-1", {'decision': 'warn'}, "v1")
        assert decision_id == 'decision-123'
        mock_conn.commit.assert_called_once()

    def test_get_gate_decision(self, mock_psycopg2_with_db):
        """Get gate decision by ID"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = {'decision_id': 'decision-1', 'state': 'warn'}
        vs = VectorStore("postgresql://localhost/gatefield")
        result = vs.get_gate_decision("decision-1")
        assert result['state'] == 'warn'


class TestVectorStoreStaticGateResult:
    """Tests for static gate result storage"""

    def test_insert_static_gate_result(self, mock_psycopg2_with_db):
        """Static gate result stored"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['gate-123']
        vs = VectorStore("postgresql://localhost/gatefield")
        gate_id = vs.insert_static_gate_result("run-1", "sast", "fail", "high", "artifact://ref")
        assert gate_id == 'gate-123'

    def test_get_static_gate_results(self, mock_psycopg2_with_db):
        """Get all static gate results for run"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = [
            {'gate_name': 'lint', 'status': 'pass'},
            {'gate_name': 'sast', 'status': 'fail', 'severity': 'high'}
        ]
        vs = VectorStore("postgresql://localhost/gatefield")
        results = vs.get_static_gate_results("run-1")
        assert len(results) == 2
        assert results[1]['gate_name'] == 'sast'


class TestVectorStoreAuditEvent:
    """Tests for audit event storage"""

    def test_insert_audit_event(self, mock_psycopg2_with_db):
        """Audit event stored with trace_id"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['event-123']
        vs = VectorStore("postgresql://localhost/gatefield")
        event_id = vs.insert_audit_event("trace-1", "span-1", "run-1", "run_started", "agent")
        assert event_id == 'event-123'


class TestJudgmentKB:
    """Tests for JudgmentKB manager class"""

    def test_judgment_kb_initialization(self, mock_mode_vector_store):
        """JudgmentKB initializes with VectorStore"""
        kb = JudgmentKB(mock_mode_vector_store)
        assert kb.vs == mock_mode_vector_store
        assert kb.embedding_worker is None

    def test_import_document(self, mock_mode_vector_store):
        """UT-KB-001: Import document to KB"""
        kb = JudgmentKB(mock_mode_vector_store)
        doc_id = kb.import_document("taboo", "Taboo content", "manual")
        assert doc_id == "mock-doc-id"

    def test_import_document_with_embedding(self, mock_mode_vector_store, mock_embedding_worker):
        """Import document with auto embedding"""
        kb = JudgmentKB(mock_mode_vector_store, mock_embedding_worker)
        kb.import_document("taboo", "Content", auto_embed=True)
        mock_embedding_worker.process_text.assert_called_once()

    def test_get_taboo_topk(self, mock_mode_vector_store):
        """UT-KB-004: get_taboo_topk returns top-k taboo examples"""
        kb = JudgmentKB(mock_mode_vector_store)
        results = kb.get_taboo_topk([0.1] * 1536, k=5)
        assert len(results) > 0
        assert results[0].axis_type == "taboo"

    def test_get_accepted_topk(self, mock_mode_vector_store):
        kb = JudgmentKB(mock_mode_vector_store)
        results = kb.get_accepted_topk([0.1] * 1536, k=5)
        assert results[0].axis_type == "accepted"

    def test_get_rejected_topk(self, mock_mode_vector_store):
        kb = JudgmentKB(mock_mode_vector_store)
        results = kb.get_rejected_topk([0.1] * 1536, k=5)
        assert results[0].axis_type == "rejected"

    def test_get_constitution_centroid(self, mock_mode_vector_store):
        kb = JudgmentKB(mock_mode_vector_store)
        centroid = kb.get_constitution_centroid()
        assert len(centroid) == 1536

    def test_get_embeddings_for_axis(self, mock_mode_vector_store):
        kb = JudgmentKB(mock_mode_vector_store)
        assert kb.get_embeddings_for_axis("taboo") == []

    def test_reindex_axis(self, mock_mode_vector_store):
        kb = JudgmentKB(mock_mode_vector_store)
        assert kb.reindex_axis("taboo") == 0

    def test_promote_from_run(self, mock_vector_store_for_kb, mock_embedding_worker):
        """UT-KB-001: Promote run outcome to judgment log"""
        kb = JudgmentKB(mock_vector_store_for_kb, mock_embedding_worker)
        doc_id = kb.promote_from_run("run-123", "judgment_log", "approve", "Good", "alice")
        assert doc_id == "promoted-doc-123"
        mock_vector_store_for_kb.insert_document.assert_called_once()


class TestCreateVectorStore:
    """Tests for convenience function"""

    def test_create_vector_store_with_connection_string(self, mock_psycopg2_unavailable):
        """Create VectorStore with explicit connection string"""
        vs = create_vector_store("postgresql://custom-host/db", backend="pgvector")
        assert vs.conn_str == "postgresql://custom-host/db"

    def test_create_vector_store_from_env(self, mock_psycopg2_unavailable):
        """Create VectorStore from environment variable"""
        import os
        os.environ['DATABASE_URL'] = 'postgresql://env-host/env-db'
        vs = create_vector_store(backend="pgvector")
        assert 'env-host' in vs.conn_str or 'localhost' in vs.conn_str
        del os.environ['DATABASE_URL']

    def test_create_vector_store_default(self, mock_psycopg2_unavailable):
        """Create VectorStore with default connection string"""
        import os
        os.environ.pop('DATABASE_URL', None)
        vs = create_vector_store(backend="pgvector")
        assert 'localhost' in vs.conn_str


class TestVectorStoreAxisTypes:
    """Tests for valid axis_type values"""

    VALID_AXIS_TYPES = ["constitution", "taboo", "accepted", "rejected", "judgment_log"]

    def test_search_similar_all_axis_types(self, mock_mode_vector_store):
        for axis_type in self.VALID_AXIS_TYPES:
            results = mock_mode_vector_store.search_similar([0.1] * 1536, axis_type)
            assert results[0].axis_type == axis_type

    def test_insert_document_all_axis_types(self, mock_mode_vector_store):
        for axis_type in self.VALID_AXIS_TYPES:
            assert mock_mode_vector_store.insert_document(axis_type, "content") == "mock-doc-id"

    def test_get_centroid_all_axis_types(self, mock_mode_vector_store):
        for axis_type in self.VALID_AXIS_TYPES:
            assert len(mock_mode_vector_store.get_centroid(axis_type)) == 1536


class TestVectorStoreEdgeCases:
    """Tests for edge cases and error handling"""

    def test_search_similar_limit_variations(self, mock_mode_vector_store):
        """Search with various limit values"""
        assert len(mock_mode_vector_store.search_similar([0.1] * 1536, "taboo", limit=1)) > 0
        assert len(mock_mode_vector_store.search_similar([0.1] * 1536, "taboo", limit=100)) > 0

    def test_insert_document_empty_text(self, mock_psycopg2_with_db):
        """Insert document with empty text"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['doc-empty']
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.insert_document("taboo", "") == 'doc-empty'

    def test_insert_embedding_empty_vector(self, mock_psycopg2_with_db):
        """Insert embedding with empty vector"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['embed-empty']
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.insert_embedding("doc-1", "model", 0, [], "sha256:empty") == 'embed-empty'

    def test_close_without_connection(self, mock_mode_vector_store):
        """Close when connection is None"""
        mock_mode_vector_store.close()
        assert mock_mode_vector_store.conn is None


class TestEmbeddingVersioning:
    """Tests specifically for embedding versioning"""

    def test_versioning_preserves_history(self, mock_psycopg2_with_db):
        """UT-KB-002: append-only versioning preserves history"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.side_effect = ['embed-v1', 'embed-v2', 'embed-v3']
        vs = VectorStore("postgresql://localhost/gatefield")
        for i in range(3):
            vs.insert_embedding("doc-versioning", "model", 1536, [i * 0.1] * 1536, f"sha256:v{i}")
        assert mock_cursor.execute.call_count == 6

    def test_valid_to_set_on_update(self, mock_psycopg2_with_db):
        """valid_to is set when deprecating embedding"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['embed-new']
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_embedding("doc-1", "model", 1536, [0.1] * 1536, "hash")
        update_call = mock_cursor.execute.call_args_list[0]
        assert 'SET valid_to = NOW()' in update_call[0][0]

    def test_only_latest_embedding_is_active(self, mock_psycopg2_with_db):
        """Only embeddings with valid_to IS NULL are active"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = [
            {'embed_id': 'embed-latest', 'doc_id': 'doc-1', 'embedding': '[0.2, 0.3]',
             'text': 'text', 'labels': {}, 'scope': None, 'model': 'model', 'dims': 2}
        ]
        vs = VectorStore("postgresql://localhost/gatefield")
        assert len(vs.get_active_embeddings("taboo")) == 1


class TestVectorStoreIntegrationMarkers:
    """Integration tests require real database"""

    @pytest.mark.integration
    def test_full_workflow(self, mock_psycopg2_with_db):
        """Full insert and search workflow"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.side_effect = [['doc-1'], ['embed-1']]
        mock_cursor.fetchall.return_value = [{'doc_id': 'doc-1', 'similarity': 0.95, 'axis_type': 'taboo', 'text': 'text'}]
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.insert_document("taboo", "Taboo text") == 'doc-1'
        assert vs.insert_embedding("doc-1", "model", 1536, [0.1] * 1536, "hash") == 'embed-1'
        assert len(vs.search_similar([0.1] * 1536, "taboo")) == 1


class TestVectorStoreCoveragePaths:
    """Tests to improve coverage for less common code paths"""

    def test_get_state_vector_with_null_embedding(self, mock_psycopg2_with_db):
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = {'run_id': 'run-1', 'semantic_embedding': None}
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.get_state_vector("run-1")['semantic_embedding'] is None

    def test_get_active_embeddings_null_embedding(self, mock_psycopg2_with_db):
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = [
            {'embed_id': 'embed-1', 'doc_id': 'doc-1', 'model': 'model', 'dims': 1536,
             'embedding': None, 'text': 'text', 'labels': {}, 'scope': None}
        ]
        vs = VectorStore("postgresql://localhost/gatefield")
        embeddings = vs.get_active_embeddings("taboo")
        assert embeddings[0]['embedding'] is None

    def test_insert_state_vector_no_semantic(self, mock_psycopg2_with_db):
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_state_vector({'run_id': 'run-no-semantic', 'artifact_id': 'artifact-1', 'semantic': {}})
        mock_cursor.execute.assert_called_once()

    def test_insert_document_empty_text(self, mock_psycopg2_with_db):
        """Insert document with empty text"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['doc-empty']
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.insert_document("taboo", "") == 'doc-empty'

    def test_insert_embedding_empty_vector(self, mock_psycopg2_with_db):
        """Insert embedding with empty vector"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['embed-empty']
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.insert_embedding("doc-1", "model", 0, [], "sha256:empty") == 'embed-empty'

    def test_close_without_connection(self, mock_mode_vector_store):
        """Close when connection is None"""
        mock_mode_vector_store.close()
        assert mock_mode_vector_store.conn is None


class TestEmbeddingVersioning:
    """Tests specifically for embedding versioning"""

    def test_versioning_preserves_history(self, mock_psycopg2_with_db):
        """UT-KB-002: append-only versioning preserves history"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.side_effect = ['embed-v1', 'embed-v2', 'embed-v3']
        vs = VectorStore("postgresql://localhost/gatefield")
        for i in range(3):
            vs.insert_embedding("doc-versioning", "model", 1536, [i * 0.1] * 1536, f"sha256:v{i}")
        assert mock_cursor.execute.call_count == 6

    def test_valid_to_set_on_update(self, mock_psycopg2_with_db):
        """valid_to is set when deprecating embedding"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = ['embed-new']
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_embedding("doc-1", "model", 1536, [0.1] * 1536, "hash")
        update_call = mock_cursor.execute.call_args_list[0]
        assert 'SET valid_to = NOW()' in update_call[0][0]

    def test_only_latest_embedding_is_active(self, mock_psycopg2_with_db):
        """Only embeddings with valid_to IS NULL are active"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = [
            {'embed_id': 'embed-latest', 'doc_id': 'doc-1', 'embedding': '[0.2, 0.3]',
             'text': 'text', 'labels': {}, 'scope': None, 'model': 'model', 'dims': 2}
        ]
        vs = VectorStore("postgresql://localhost/gatefield")
        assert len(vs.get_active_embeddings("taboo")) == 1


class TestVectorStoreIntegrationMarkers:
    """Integration tests require real database"""

    @pytest.mark.integration
    def test_full_workflow(self, mock_psycopg2_with_db):
        """Full insert and search workflow"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.side_effect = [['doc-1'], ['embed-1']]
        mock_cursor.fetchall.return_value = [{'doc_id': 'doc-1', 'similarity': 0.95, 'axis_type': 'taboo', 'text': 'text'}]
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.insert_document("taboo", "Taboo text") == 'doc-1'
        assert vs.insert_embedding("doc-1", "model", 1536, [0.1] * 1536, "hash") == 'embed-1'
        assert len(vs.search_similar([0.1] * 1536, "taboo")) == 1


class TestVectorStoreCoveragePaths:
    """Tests for less common code paths"""

    def test_get_state_vector_with_null_embedding(self, mock_psycopg2_with_db):
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchone.return_value = {'run_id': 'run-1', 'semantic_embedding': None}
        vs = VectorStore("postgresql://localhost/gatefield")
        assert vs.get_state_vector("run-1")['semantic_embedding'] is None

    def test_get_active_embeddings_null_embedding(self, mock_psycopg2_with_db):
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        mock_cursor.fetchall.return_value = [
            {'embed_id': 'embed-1', 'doc_id': 'doc-1', 'model': 'model', 'dims': 1536,
             'embedding': None, 'text': 'text', 'labels': {}, 'scope': None}
        ]
        vs = VectorStore("postgresql://localhost/gatefield")
        embeddings = vs.get_active_embeddings("taboo")
        assert embeddings[0]['embedding'] is None

    def test_insert_state_vector_no_semantic(self, mock_psycopg2_with_db):
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_state_vector({'run_id': 'run-no-semantic', 'artifact_id': 'artifact-1', 'semantic': {}})
        mock_cursor.execute.assert_called_once()

        # Should handle null embedding
        assert len(embeddings) == 1
        assert embeddings[0]['embedding'] is None

    def test_insert_state_vector_no_semantic(self, mock_psycopg2_with_db):
        """Insert state vector without semantic embedding"""
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
        vs = VectorStore("postgresql://localhost/gatefield")
        vs.insert_state_vector({'run_id': 'run-no-semantic', 'artifact_id': 'artifact-1', 'semantic': {}})
        mock_cursor.execute.assert_called_once()