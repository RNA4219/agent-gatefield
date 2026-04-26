"""
State Vector Encoder - Generate composite state vectors from artifacts and traces
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .utils import generate_mock_embedding

try:
    from src.encoder.embedding_worker import (
        DEFAULT_DIMENSIONS,
        DEFAULT_MODEL,
        DEFAULT_RUNTIME,
        EmbeddingWorker,
        create_embedding_worker_from_config,
    )
except ImportError:
    DEFAULT_MODEL = "BAAI/bge-m3"
    DEFAULT_DIMENSIONS = 1024
    DEFAULT_RUNTIME = "llama.cpp"
    EmbeddingWorker = None
    create_embedding_worker_from_config = None

logger = logging.getLogger(__name__)

ENCODER_VERSION = "encoder-v1.0.0"
SCHEMA_VERSION = "1.0.0"


class StateEncoder:
    """
    成果物・工程・履歴から複合状態ベクトルを生成

    State vector components:
    - semantic: Dense embedding from artifact content
    - rule_violation: Sparse severity vector from static gates
    - test_evidence: Numeric evidence from test results
    - risk: Risk context vector
    - historical_decision: Similarity to past decisions
    - uncertainty: Uncertainty metrics
    - context: Metadata (repo, artifact_type, env)
    - trajectory: Sequence features for drift detection
    """

    def __init__(
        self,
        embedding_config: dict,
        embedding_worker: EmbeddingWorker = None
    ):
        self.provider = embedding_config.get('provider') or os.environ.get('EMBEDDING_PROVIDER', 'local')
        self.runtime = embedding_config.get('runtime') or os.environ.get('EMBEDDING_RUNTIME', DEFAULT_RUNTIME)
        self.model = embedding_config.get('model') or os.environ.get('EMBEDDING_MODEL', DEFAULT_MODEL)
        self.dimensions = int(embedding_config.get('dimensions') or os.environ.get('EMBEDDING_DIMENSIONS', DEFAULT_DIMENSIONS))

        # Initialize embedding worker
        if embedding_worker:
            self.embedding_worker = embedding_worker
        elif EmbeddingWorker:
            self.embedding_worker = EmbeddingWorker(
                provider=self.provider,
                runtime=self.runtime,
                model=self.model,
                dims=self.dimensions
            )
        else:
            self.embedding_worker = None
            logger.warning("EmbeddingWorker not available, semantic encoding will be mock")

    def encode(
        self,
        artifact: dict,
        trace: dict,
        rule_results: dict,
        historical_context: dict = None
    ) -> dict:
        """
        Generate composite state vector

        Args:
            artifact: Artifact info (run_id, artifact_id, hash, diff, type, repo, env)
            trace: Execution trace (tool calls, steps, test results, errors)
            rule_results: Static gate results (lint, sast, secret, license counts)
            historical_context: Optional historical decision context

        Returns:
            state_vector: Structured dict with all components
        """
        state_vector = {
            'schema_version': SCHEMA_VERSION,
            'run_id': artifact.get('run_id'),
            'artifact_id': artifact.get('artifact_id'),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'encoder_version': ENCODER_VERSION,
            'intermediate': artifact.get('intermediate', False),
            'semantic': self._encode_semantic(artifact),
            'rule_violation': self._encode_rule_violation(rule_results),
            'test_evidence': self._encode_test_evidence(trace),
            'risk': self._encode_risk(artifact, trace),
            'historical_decision': historical_context or {},
            'uncertainty': self._encode_uncertainty(trace, historical_context),
            'context': self._encode_context(artifact),
            'trajectory': self._encode_trajectory(trace)
        }
        return state_vector

    def _encode_semantic(self, artifact: dict) -> dict:
        """
        Generate semantic embedding from artifact content

        Args:
            artifact: Dict with 'diff', 'content', or 'text' fields

        Returns:
            Dict with model, dims, vector, and vector_ref
        """
        # Get text content for embedding
        text_content = self._extract_text_content(artifact)

        if not text_content:
            return {
                'model': self.model,
                'dims': self.dimensions,
                'vector': [],
                'vector_ref': None,
                'content_hash': None,
                'status': 'no_content'
            }

        # Compute content hash
        content_hash = self._compute_hash(text_content)

        # Generate embedding
        embedding = []
        if self.embedding_worker:
            try:
                embedding = self.embedding_worker.process_text(text_content)
            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")
                embedding = self._mock_embedding()
        else:
            embedding = self._mock_embedding()

        return {
            'provider': self.provider,
            'model': self.model,
            'dims': self.dimensions,
            'vector': embedding,
            'vector_ref': f"vec://{content_hash[:16]}",
            'content_hash': content_hash,
            'status': 'success'
        }

    def _extract_text_content(self, artifact: dict) -> str:
        """Extract text content from artifact for embedding"""
        # Direct content field
        if artifact.get('content'):
            return str(artifact['content'])

        # Diff content
        if artifact.get('diff'):
            diff = str(artifact['diff'])
            cleaned = diff.replace('+++', '').replace('---', '').replace('@@', '')
            return cleaned

        # Text field
        if artifact.get('text'):
            return str(artifact['text'])

        # Description
        if artifact.get('description'):
            return str(artifact['description'])

        # Combine metadata as fallback
        parts = []
        if artifact.get('type'):
            parts.append(f"Type: {artifact['type']}")
        if artifact.get('repo'):
            parts.append(f"Repo: {artifact['repo']}")

        return ' '.join(parts) if parts else ''

    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of content"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _mock_embedding(self) -> List[float]:
        """Generate mock embedding for testing"""
        return generate_mock_embedding(self.dimensions)

    def _encode_rule_violation(self, rule_results: dict) -> dict:
        """Encode static gate violations as sparse severity vector"""
        return {
            'secret': rule_results.get('secret_scan', {}).get('count', 0),
            'secret_critical': rule_results.get('secret_scan', {}).get('critical_count', 0),
            'sast_high': rule_results.get('sast', {}).get('high_count', 0),
            'sast_medium': rule_results.get('sast', {}).get('medium_count', 0),
            'sast_low': rule_results.get('sast', {}).get('low_count', 0),
            'lint_error': rule_results.get('lint', {}).get('error_count', 0),
            'lint_warning': rule_results.get('lint', {}).get('warning_count', 0),
            'typecheck_error': rule_results.get('typecheck', {}).get('error_count', 0),
            'test_failed': rule_results.get('tests', {}).get('failed_count', 0),
            'test_error': rule_results.get('tests', {}).get('error_count', 0),
            'license_forbidden': rule_results.get('license', {}).get('forbidden_count', 0),
            'license_unknown': rule_results.get('license', {}).get('unknown_count', 0),
            'tool_policy_deny': rule_results.get('tool_policy', {}).get('deny_count', 0),
        }

    def _encode_test_evidence(self, trace: dict) -> dict:
        """Encode test execution evidence as numeric vector"""
        test_results = trace.get('test_results', {})
        return {
            'unit_pass_rate': test_results.get('pass_rate', 0.0),
            'unit_total': test_results.get('total', 0),
            'unit_passed': test_results.get('passed', 0),
            'unit_failed': test_results.get('failed', 0),
            'changed_modules_tested': test_results.get('modules_tested', 0),
            'coverage_delta': test_results.get('coverage_delta', 0.0),
            'new_tests_added': test_results.get('new_tests', 0),
            'test_duration_seconds': test_results.get('duration', 0),
        }

    def _encode_risk(self, artifact: dict, trace: dict) -> dict:
        """Encode risk context as numeric/categorical vector"""
        tool_calls = trace.get('tool_calls', [])
        # Handle case where tool_calls might be an int (count) instead of list
        if isinstance(tool_calls, int):
            tool_calls = []
        risk_metadata = artifact.get('risk_metadata', {})

        # Detect production write
        prod_write = 0
        for tc in tool_calls:
            cmd = str(tc.get('command', tc.get('tool', '')))
            if any(p in cmd.lower() for p in ['production', 'prod', 'deploy', 'kubectl apply']):
                prod_write = 1

        # Detect network egress
        network_egress = 0
        for tc in tool_calls:
            if tc.get('external_call') or 'http' in str(tc).lower():
                network_egress = 1

        # PII level
        pii_level = risk_metadata.get('pii_level', 0)
        if artifact.get('contains_pii'):
            pii_level = max(pii_level, 2)

        # Privilege level
        privilege_level = 0
        for tc in tool_calls:
            if tc.get('high_privilege') or tc.get('admin'):
                privilege_level = 3
            elif tc.get('elevated'):
                privilege_level = max(privilege_level, 2)

        return {
            'prod_write': prod_write,
            'pii_level': pii_level,
            'network_egress': network_egress,
            'privilege_level': privilege_level,
            'high_privilege': privilege_level >= 2,
            'data_classification': risk_metadata.get('data_classification', 'internal'),
        }

    def _encode_uncertainty(self, trace: dict, historical_context: dict = None) -> dict:
        """Encode uncertainty metrics"""
        tool_calls = trace.get('tool_calls', [])
        # Handle case where tool_calls might be an int (count) instead of list
        if isinstance(tool_calls, int):
            tool_call_count = tool_calls
            tool_calls = []
        else:
            tool_call_count = len(tool_calls)

        error_calls = sum(1 for tc in tool_calls if tc.get('error') or tc.get('failed'))
        # Also check tool_errors field for count-based input
        if isinstance(trace.get('tool_errors'), int):
            error_calls = max(error_calls, trace.get('tool_errors', 0))

        tool_error_rate = error_calls / max(tool_call_count, 1)
        judge_std = historical_context.get('grader_variance', 0) if historical_context else 0
        self_confidence = trace.get('model_confidence', 0.0)

        # Evidence gap
        evidence_gap = 0.0
        if not trace.get('test_results'):
            evidence_gap += 0.3
        if tool_call_count == 0:
            evidence_gap += 0.2

        return {
            'judge_std': judge_std,
            'self_confidence': self_confidence,
            'tool_error_rate': tool_error_rate,
            'evidence_gap': evidence_gap,
            'total_uncertainty': (judge_std + (1 - self_confidence) + tool_error_rate + evidence_gap) / 4,
        }

    def _encode_context(self, artifact: dict) -> dict:
        """Encode context metadata"""
        return {
            'repo': artifact.get('repo', ''),
            'service': artifact.get('service', ''),
            'branch': artifact.get('branch', ''),
            'commit': artifact.get('commit', ''),
            'artifact_type': artifact.get('type', 'code_patch'),
            'env': artifact.get('env', 'local'),
            'author': artifact.get('author', ''),
            'timestamp': artifact.get('timestamp', datetime.now(timezone.utc).isoformat()),
            'scope': artifact.get('scope', ''),
        }

    def _encode_trajectory(self, trace: dict) -> dict:
        """Encode trajectory/sequence features for drift detection"""
        tool_calls = trace.get('tool_calls', [])
        # Handle case where tool_calls might be an int (count) instead of list
        if isinstance(tool_calls, int):
            tool_call_count = tool_calls
            tool_calls = []
        else:
            tool_call_count = len(tool_calls)

        steps = trace.get('steps', [])
        # Handle case where steps might be an int (count) instead of list
        if isinstance(steps, int):
            step_count = steps
            steps = []
        else:
            step_count = len(steps)

        # Calculate branch_count from steps or use branches field if available
        if isinstance(trace.get('branches'), int):
            branch_count = trace.get('branches', 0)
        else:
            branch_count = sum(1 for s in steps if s.get('branch') or s.get('decision'))

        # Calculate backtrack_count from steps or use backtracks field if available
        if isinstance(trace.get('backtracks'), int):
            backtrack_count = trace.get('backtracks', 0)
        else:
            backtrack_count = sum(1 for s in steps if s.get('backtrack') or s.get('retry'))

        return {
            'delta_semantic': trace.get('delta_semantic', 0.0),
            'delta_semantic_vector': trace.get('previous_semantic_vector', []),
            'tool_calls': tool_call_count,
            'tool_sequence': [tc.get('tool', 'unknown') for tc in tool_calls],
            'step_count': step_count,
            'branch_count': branch_count,
            'backtrack_count': backtrack_count,
            'duration_seconds': trace.get('duration', 0),
        }

    def encode_for_kb(
        self,
        state_vector: dict,
        kb_store: 'VectorStore'
    ) -> dict:
        """
        Encode state vector and retrieve KB context
        """
        semantic_vector = state_vector.get('semantic', {}).get('vector', [])
        if not semantic_vector:
            return state_vector

        # Search each axis
        for axis in ['constitution', 'taboo', 'accepted', 'rejected', 'judgment_log']:
            try:
                results = kb_store.search_similar(semantic_vector, axis, limit=5)
                max_sim = max((r.similarity for r in results), default=0.0)
                state_vector['historical_decision'][f'{axis}_sim'] = max_sim
            except Exception as e:
                logger.warning(f"KB search failed for axis {axis}: {e}")

        return state_vector


def create_state_encoder_from_config(config: dict) -> StateEncoder:
    """Create StateEncoder from configuration"""
    embedding_config = config.get('state_space_gate', {}).get('semantic_embedding', {})

    embedding_worker = None
    if create_embedding_worker_from_config:
        embedding_worker = create_embedding_worker_from_config(config)

    return StateEncoder(
        embedding_config=embedding_config,
        embedding_worker=embedding_worker
    )
