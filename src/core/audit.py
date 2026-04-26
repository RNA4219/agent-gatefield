"""
Audit Logging - State Transition and Hard Override Audit Trail

STATE_TRANSITION_SPEC 11.1 compliant audit logging.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Configure audit logger
audit_logger = logging.getLogger('gate_audit')
audit_logger.setLevel(logging.INFO)


def log_state_transition(
    result: 'DecisionResult',
    previous_state: 'GateState' = None,
    audit_logger: logging.Logger = audit_logger
) -> None:
    """
    Log state transition for audit trail.

    Args:
        result: DecisionResult containing decision details
        previous_state: Previous gate state (if any)
        audit_logger: Logger instance to use (defaults to module-level logger)
    """
    audit_event = {
        'event_type': 'state_transition',
        'trace_id': result.trace_id,
        'run_id': result.run_id,
        'decision_id': result.decision_id,
        'previous_state': previous_state.value if previous_state else None,
        'new_state': result.decision if isinstance(result.decision, str) else result.decision.value,
        'composite_score': result.composite_score,
        'top_factors': [f.__dict__ if hasattr(f, '__dict__') else f for f in result.factors],
        'action_type': result.action.get('action_type', '') if result.action else '',
        'threshold_version': result.threshold_version,
        'hard_override_reason': result.hard_override,
        'self_correction_count': result.self_correction_count,
        'persistent_factors': result.persistent_factors,
        'checkpoint_ref': result.checkpoint_ref,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'retention_class': 'audit'
    }

    audit_logger.info(json.dumps(audit_event))


def log_hard_override(
    override_reason: str,
    trigger_value: Any,
    state_vector: Dict,
    policy_version: str,
    threshold_version: str,
    audit_logger: logging.Logger = audit_logger
) -> None:
    """
    Log hard override trigger for audit trail.

    Args:
        override_reason: The hard override rule that triggered
        trigger_value: The value(s) that caused the trigger
        state_vector: The state vector being evaluated
        policy_version: Current policy version
        threshold_version: Current threshold version
        audit_logger: Logger instance to use
    """
    audit_event = {
        'event_type': 'hard_override',
        'override_reason': override_reason,
        'trigger_value': trigger_value,
        'policy_version': policy_version,
        'threshold_version': threshold_version,
        'state_vector_summary': {
            'rule_violation': state_vector.get('rule_violation', {}),
            'risk': state_vector.get('risk', {}),
            'uncertainty': state_vector.get('uncertainty', {})
        },
        'created_at': datetime.now(timezone.utc).isoformat(),
        'retention_class': 'audit'
    }

    audit_logger.info(json.dumps(audit_event))


def log_sla_timeout(
    decision_id: str,
    timeout_type: str,
    sla_deadline: datetime,
    escalation_target: str,
    audit_logger: logging.Logger = audit_logger
) -> None:
    """
    Log SLA timeout event for audit trail.

    Args:
        decision_id: ID of the decision that timed out
        timeout_type: 'ack_timeout' or 'decision_timeout'
        sla_deadline: The deadline that was exceeded
        escalation_target: Who was escalated to
        audit_logger: Logger instance to use
    """
    audit_event = {
        'event_type': 'sla_timeout',
        'decision_id': decision_id,
        'timeout_type': timeout_type,
        'sla_deadline': sla_deadline.isoformat(),
        'escalation_target': escalation_target,
        'auto_block_reason': 'sla_timeout_fail_closed',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'retention_class': 'audit'
    }
    audit_logger.info(json.dumps(audit_event))


def log_late_hard_fail(
    original_decision_id: str,
    late_fail_type: str,
    affected_artifacts: List[str],
    detection_time: datetime,
    audit_logger: logging.Logger = audit_logger
) -> None:
    """
    Log late hard fail event for audit trail.

    Args:
        original_decision_id: ID of the original PASS decision
        late_fail_type: Type of late failure detected
        affected_artifacts: List of affected artifact IDs
        detection_time: When the failure was detected
        audit_logger: Logger instance to use
    """
    audit_event = {
        'event_type': 'late_hard_fail',
        'original_decision_id': original_decision_id,
        'late_fail_type': late_fail_type,
        'affected_artifacts': affected_artifacts,
        'detection_time': detection_time.isoformat(),
        'remediation_action': 'artifact_invalidation',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'retention_class': 'audit'
    }
    audit_logger.info(json.dumps(audit_event))


def log_checkpoint_rollback(
    rollback_reason: str,
    source_checkpoint_ref: str,
    target_checkpoint_ref: str,
    upstream_failure_ref: Optional[str],
    audit_logger: logging.Logger = audit_logger
) -> None:
    """
    Log checkpoint rollback event for audit trail.

    Args:
        rollback_reason: Why the rollback was triggered
        source_checkpoint_ref: Checkpoint rolling back from
        target_checkpoint_ref: Checkpoint rolling back to
        upstream_failure_ref: Reference to upstream failure (if any)
        audit_logger: Logger instance to use
    """
    audit_event = {
        'event_type': 'checkpoint_rollback',
        'rollback_reason': rollback_reason,
        'source_checkpoint_ref': source_checkpoint_ref,
        'target_checkpoint_ref': target_checkpoint_ref,
        'upstream_failure_ref': upstream_failure_ref,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'retention_class': 'audit'
    }
    audit_logger.info(json.dumps(audit_event))
