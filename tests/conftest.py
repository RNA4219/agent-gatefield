"""
Shared test fixtures and configuration for agent-gatefield tests.
"""

import pytest
from unittest.mock import MagicMock, patch, Mock


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (deselect with '-m \"not integration\"')"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )


# ============================================================================
# Database Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_db_cursor():
    """
    Shared mock cursor with context manager support.

    Usage:
        mock_cursor = mock_db_cursor
        mock_cursor.fetchall.return_value = [...]
    """
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.return_value = None
    mock_cursor.execute.return_value = None
    return mock_cursor


@pytest.fixture
def mock_db_connection(mock_db_cursor):
    """
    Shared mock database connection.

    Usage:
        mock_conn, mock_cursor = mock_db_connection
        mock_cursor.fetchall.return_value = [...]
    """
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_db_cursor
    mock_conn.commit.return_value = None
    mock_conn.close.return_value = None
    return mock_conn, mock_db_cursor


@pytest.fixture
def mock_psycopg2_with_db(mock_db_connection):
    """
    Shared psycopg2 mock with database connection.

    Patches PSYCOPG2_AVAILABLE, RealDictCursor, psycopg2.

    Usage:
        mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
    """
    mock_conn, mock_cursor = mock_db_connection
    with patch('src.vector_store._psycopg2.PSYCOPG2_AVAILABLE', True), \
         patch('src.vector_store._psycopg2.RealDictCursor'), \
         patch('src.vector_store._psycopg2.psycopg2') as mock_psycopg2:
        mock_psycopg2.connect.return_value = mock_conn
        yield mock_psycopg2, mock_conn, mock_cursor


# Removed class-scoped autouse fixture - caused scope mismatch


@pytest.fixture
def mock_psycopg2_unavailable():
    """
    Mock psycopg2 as unavailable (ImportError scenario).
    """
    with patch('src.vector_store._psycopg2.PSYCOPG2_AVAILABLE', False):
        yield


@pytest.fixture
def mock_mode_vector_store(mock_psycopg2_unavailable):
    """
    VectorStore in mock mode (psycopg2 unavailable).
    Returns a VectorStore instance that operates without database.
    """
    from src.vector_store import VectorStore
    return VectorStore("postgresql://localhost/test")


@pytest.fixture
def vector_store_with_db(mock_psycopg2_with_db):
    """
    VectorStore with mock database connection.

    Usage:
        vs, mock_conn, mock_cursor = vector_store_with_db
        mock_cursor.fetchall.return_value = [...]
        vs.search_similar(...)
    """
    mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
    from src.vector_store import VectorStore
    vs = VectorStore("postgresql://localhost/gatefield")
    return vs, mock_conn, mock_cursor


@pytest.fixture
def mock_execute_values(mock_psycopg2_with_db):
    """
    Fixture for batch operations with execute_values patched.
    """
    from unittest.mock import patch
    mock_psycopg2, mock_conn, mock_cursor = mock_psycopg2_with_db
    with patch('src.vector_store._psycopg2.execute_values') as mock_ev:
        yield mock_ev, mock_conn, mock_cursor


# ============================================================================
# Engine Mock Fixtures
# ============================================================================

@pytest.fixture
def engine_config():
    """
    Default DecisionEngine configuration for tests.
    """
    return {
        'thresholds': {
            'composite_warn': 0.70,
            'composite_block': 0.85,
            'taboo_warn': 0.80,
            'taboo_block': 0.88,
            'judge_std_warn': 0.15,
            'judge_std_block': 0.25,
            'tool_failure_warn': 0.10,
            'tool_failure_block': 0.25
        },
        'hard_overrides': {
            'block_if_secret_found': True,
            'block_if_prod_write_and_taboo_warn': True,
            'hold_if_high_privilege_and_uncertain': True
        },
        'threshold_version': 'v1'
    }


@pytest.fixture
def sample_state_vector():
    """
    Sample state vector for testing.
    """
    return {
        'run_id': 'run-sample-001',
        'artifact_id': 'art-sample-001',
        'rule_violation': {'secret': 0, 'sast_high': 0, 'tool_policy_deny': 0},
        'risk': {'prod_write': 0, 'pii_level': 0, 'high_privilege': 0},
        'uncertainty': {'judge_std': 0.05, 'tool_error_rate': 0.02, 'self_confidence': 0.95},
        'trajectory': {'delta_semantic': 0.03, 'tool_calls': 5, 'ewma_drift': 0.02},
        'historical_decision': {'taboo_similarity': 0.10, 'accept_similarity': 0.85, 'reject_similarity': 0.05},
        'semantic': {'embedding_ref': 'vec://sample-embedding'},
        'test_evidence': {'pass_rate': 1.0, 'coverage_delta': 0.05}
    }


@pytest.fixture
def sample_kb_embeddings():
    """
    Sample KB embeddings for scorer tests.
    """
    return {
        'taboo': [{'embedding': [0.1] * 1536, 'similarity': 0.15, 'doc_id': 'taboo-001'}],
        'accepted': [{'embedding': [0.2] * 1536, 'similarity': 0.85, 'doc_id': 'accept-001'}],
        'rejected': [{'embedding': [0.3] * 1536, 'similarity': 0.10, 'doc_id': 'reject-001'}],
        'constitution_centroid': [0.25] * 1536
    }


# ============================================================================
# Review Queue Fixtures
# ============================================================================

@pytest.fixture
def sample_review_item():
    """
    Sample ReviewItem for testing.
    """
    from datetime import datetime, timezone
    from src.review.dataclasses import ReviewItem

    return ReviewItem(
        decision_id='decision-sample-001',
        run_id='run-sample-001',
        state='hold',
        composite_score=0.85,
        severity='high',
        top_factors=['taboo_proximity', 'uncertainty'],
        artifact_ref='artifact://art-sample-001',
        trace_ref='trace://trace-sample-001',
        created_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_review_action():
    """
    Sample ReviewAction for testing.
    """
    from datetime import datetime, timezone
    from src.review.dataclasses import ReviewAction

    return ReviewAction(
        decision_id='decision-sample-001',
        reviewer='reviewer-sample-001',
        created_at=datetime.now(timezone.utc)
    )


# ============================================================================
# Vector Store Fixtures
# ============================================================================

@pytest.fixture
def sample_embedding_vector():
    """
    Sample 1536-dimension embedding vector for testing.
    """
    return [0.1] * 1536


@pytest.fixture
def sample_document():
    """
    Sample judgment document for KB tests.
    """
    return {
        'axis_type': 'taboo',
        'text': 'Sample taboo pattern text',
        'source_type': 'manual',
        'labels': {'category': 'injection', 'severity': 'high'},
        'scope': 'repo-sample'
    }


@pytest.fixture
def mock_embedding_worker():
    """
    Mock embedding worker for JudgmentKB tests.
    """
    worker = Mock()
    worker.process_text.return_value = [0.1] * 1536
    worker.compute_hash.return_value = "sha256:hash"
    worker.model = "text-embedding-3-large"
    worker.dims = 1536
    return worker


@pytest.fixture
def mock_vector_store_for_kb():
    """
    Mock VectorStore for JudgmentKB promote_from_run test.
    """
    vs = Mock()
    vs.insert_document.return_value = "promoted-doc-123"
    vs.get_state_vector.return_value = {'context_json': {'repo': 'service-a'}}
    vs.insert_embedding.return_value = "embed-123"
    return vs