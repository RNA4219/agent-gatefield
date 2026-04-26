"""
Hard Override Rules - Immediate Block/Hold Conditions

STATE_TRANSITION_SPEC 3.1 and 3.2 compliant hard override rules.
These rules are evaluated before scorers and can immediately block or hold.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

from src.core.audit import log_hard_override
from src.core.types import ScoreFactor


# Hard override rule identifiers
HO01_SECRET_FOUND = 'secret_found'
HO02_PROD_WRITE_TABOO_WARN = 'prod_write_taboo'
HO03_HIGH_PRIVILEGE_UNCERTAIN = 'high_privilege_uncertain'
HO04_SAST_HIGH = 'sast_high'
HO05_TOOL_POLICY_DENY = 'tool_policy_deny'


def apply_hard_overrides(
    state_vector: Dict,
    thresholds: Dict,
    hard_overrides_config: Dict,
    threshold_version: str,
    policy_version: str,
    gate_state_cls,
    decision_result_cls,
    taboo_score: Optional[float] = None
) -> Optional['DecisionResult']:
    """
    Apply hard override rules to state vector.

    Evaluation order per STATE_TRANSITION_SPEC 3.2:
    1. block_if_secret_found (immediate, no dependencies)
    2. hold_if_high_privilege_and_uncertain (no scorer dependency)
    3. static_gate_sast_high (immediate)
    4. tool_policy_deny (immediate)
    5. block_if_prod_write_and_taboo_warn (requires taboo scorer - pass taboo_score)

    Args:
        state_vector: The state vector being evaluated
        thresholds: Threshold configuration dict
        hard_overrides_config: Hard overrides enabled/disabled config
        threshold_version: Current locked threshold version
        policy_version: Current policy version
        gate_state_cls: GateState enum class (for state values)
        decision_result_cls: DecisionResult dataclass (for creating results)
        taboo_score: Optional taboo proximity score (required for HO02)

    Returns:
        DecisionResult if hard override triggered, None otherwise
    """
    rule_violation = state_vector.get('rule_violation', {})
    risk = state_vector.get('risk', {})
    uncertainty = state_vector.get('uncertainty', {})

    # Helper to build static_gate_summary for hard overrides
    def build_override_gate_summary(rule_type: str, count: int = 1) -> Dict:
        return {
            'gates_executed': [rule_type],
            'all_passed': False,
            'hard_failures': [{
                'gate_name': rule_type,
                'severity': 'critical',
                'evidence_ref': f'{rule_type}://override',
                'rule_id': rule_type
            }],
            'warnings': []
        }

    # Helper to build action dict
    def build_action(action_type: str, checkpoint_ref: str = None) -> Dict:
        action = {'action_type': action_type}
        if checkpoint_ref:
            action['checkpoint_ref'] = checkpoint_ref
        return action

    # HO01: block_if_secret_found (STATE_TRANSITION_SPEC 3.1)
    if hard_overrides_config.get('block_if_secret_found', True):
        secret_count = rule_violation.get('secret', 0)
        if secret_count > 0:
            log_hard_override(
                override_reason=HO01_SECRET_FOUND,
                trigger_value=secret_count,
                state_vector=state_vector,
                policy_version=policy_version,
                threshold_version=threshold_version
            )
            return decision_result_cls(
                decision='block',
                composite_score=1.0,
                artifact_id=state_vector.get('artifact_id', ''),
                policy_version=policy_version,
                factors=[ScoreFactor(
                    name='secret_detection',
                    value=1.0,
                    weight=1.0,
                    contribution=1.0
                )],
                exemplar_refs=[],
                action=build_action('artifact_correction'),
                threshold_version=threshold_version,
                static_gate_summary=build_override_gate_summary('secret_scan', secret_count),
                hard_override=HO01_SECRET_FOUND,
                state_vector_ref=f"state://{state_vector.get('run_id', '')}",
                scorer_results=[],
                created_at=datetime.now(timezone.utc)
            )

    # HO03: hold_if_high_privilege_and_uncertain (STATE_TRANSITION_SPEC 3.1)
    if hard_overrides_config.get('hold_if_high_privilege_and_uncertain', True):
        if risk.get('high_privilege', 0) == 1:
            judge_std = uncertainty.get('judge_std', 0)
            tool_error = uncertainty.get('tool_error_rate', 0)
            judge_std_warn = thresholds.get('judge_std_warn', 0.15)
            tool_error_warn = thresholds.get('tool_failure_warn', 0.10)
            if judge_std > judge_std_warn or tool_error > tool_error_warn:
                trigger_value = {'judge_std': judge_std, 'tool_error_rate': tool_error}
                log_hard_override(
                    override_reason=HO03_HIGH_PRIVILEGE_UNCERTAIN,
                    trigger_value=trigger_value,
                    state_vector=state_vector,
                    policy_version=policy_version,
                    threshold_version=threshold_version
                )
                return decision_result_cls(
                    decision='hold',
                    composite_score=0.85,
                    artifact_id=state_vector.get('artifact_id', ''),
                    policy_version=policy_version,
                    factors=[ScoreFactor(
                        name='high_privilege_uncertainty',
                        value=max(judge_std, tool_error),
                        weight=1.0,
                        contribution=0.85
                    )],
                    exemplar_refs=[],
                    action=build_action('hold_for_review'),
                    threshold_version=threshold_version,
                    static_gate_summary={'gates_executed': [], 'all_passed': True, 'hard_failures': [], 'warnings': []},
                    hard_override=HO03_HIGH_PRIVILEGE_UNCERTAIN,
                    state_vector_ref=f"state://{state_vector.get('run_id', '')}",
                    scorer_results=[],
                    created_at=datetime.now(timezone.utc)
                )

    # HO04: static_gate_sast_high (STATE_TRANSITION_SPEC 3.1)
    sast_high_count = rule_violation.get('sast_high', 0)
    if sast_high_count > 0:
        log_hard_override(
            override_reason=HO04_SAST_HIGH,
            trigger_value=sast_high_count,
            state_vector=state_vector,
            policy_version=policy_version,
            threshold_version=threshold_version
        )
        return decision_result_cls(
            decision='block',
            composite_score=0.95,
            artifact_id=state_vector.get('artifact_id', ''),
            policy_version=policy_version,
            factors=[ScoreFactor(
                name='sast_high',
                value=float(sast_high_count),
                weight=1.0,
                contribution=0.95
            )],
            exemplar_refs=[],
            action=build_action('artifact_correction'),
            threshold_version=threshold_version,
            static_gate_summary=build_override_gate_summary('sast', sast_high_count),
            hard_override=HO04_SAST_HIGH,
            state_vector_ref=f"state://{state_vector.get('run_id', '')}",
            scorer_results=[],
            created_at=datetime.now(timezone.utc)
        )

    # HO05: tool_policy_deny (STATE_TRANSITION_SPEC 3.1)
    tool_deny_count = rule_violation.get('tool_policy_deny', 0)
    if tool_deny_count > 0:
        log_hard_override(
            override_reason=HO05_TOOL_POLICY_DENY,
            trigger_value=tool_deny_count,
            state_vector=state_vector,
            policy_version=policy_version,
            threshold_version=threshold_version
        )
        return decision_result_cls(
            decision='block',
            composite_score=1.0,
            artifact_id=state_vector.get('artifact_id', ''),
            policy_version=policy_version,
            factors=[ScoreFactor(
                name='tool_policy_deny',
                value=float(tool_deny_count),
                weight=1.0,
                contribution=1.0
            )],
            exemplar_refs=[],
            action=build_action('process_correction'),
            threshold_version=threshold_version,
            static_gate_summary=build_override_gate_summary('tool_policy', tool_deny_count),
            hard_override=HO05_TOOL_POLICY_DENY,
            state_vector_ref=f"state://{state_vector.get('run_id', '')}",
            scorer_results=[],
            created_at=datetime.now(timezone.utc)
        )

    # HO02: block_if_prod_write_and_taboo_warn
    # This requires taboo scorer result, so it's evaluated after scorers
    # Only applies if taboo_score is provided
    if hard_overrides_config.get('block_if_prod_write_and_taboo_warn', True) and taboo_score is not None:
        taboo_warn = thresholds.get('taboo_warn', 0.80)
        if risk.get('prod_write', 0) == 1 and taboo_score >= taboo_warn:
            trigger_value = {'prod_write': 1, 'taboo_score': taboo_score}
            log_hard_override(
                override_reason=HO02_PROD_WRITE_TABOO_WARN,
                trigger_value=trigger_value,
                state_vector=state_vector,
                policy_version=policy_version,
                threshold_version=threshold_version
            )
            return decision_result_cls(
                decision='block',
                composite_score=0.90,
                artifact_id=state_vector.get('artifact_id', ''),
                policy_version=policy_version,
                factors=[ScoreFactor(
                    name='prod_write_taboo',
                    value=taboo_score,
                    weight=1.0,
                    contribution=0.90,
                    threshold=taboo_warn,
                    threshold_type='warn'
                )],
                exemplar_refs=[],
                action=build_action('process_correction'),
                threshold_version=threshold_version,
                static_gate_summary={'gates_executed': [], 'all_passed': True, 'hard_failures': [], 'warnings': []},
                hard_override=HO02_PROD_WRITE_TABOO_WARN,
                state_vector_ref=f"state://{state_vector.get('run_id', '')}",
                scorer_results=[],
                created_at=datetime.now(timezone.utc)
            )

    return None


def check_hard_override_ho02(
    state_vector: Dict,
    thresholds: Dict,
    hard_overrides_config: Dict,
    threshold_version: str,
    policy_version: str,
    gate_state_cls,
    decision_result_cls,
    taboo_score: float
) -> Optional['DecisionResult']:
    """
    Check HO02 (block_if_prod_write_and_taboo_warn) after scorers have run.

    This is a convenience function for checking HO02 specifically after
    the taboo scorer has produced a result.

    Args:
        state_vector: The state vector being evaluated
        thresholds: Threshold configuration dict
        hard_overrides_config: Hard overrides enabled/disabled config
        threshold_version: Current locked threshold version
        policy_version: Current policy version
        gate_state_cls: GateState enum class
        decision_result_cls: DecisionResult dataclass
        taboo_score: Taboo proximity score from scorer

    Returns:
        DecisionResult if HO02 triggered, None otherwise
    """
    risk = state_vector.get('risk', {})

    def build_action(action_type: str) -> Dict:
        return {'action_type': action_type}

    if hard_overrides_config.get('block_if_prod_write_and_taboo_warn', True):
        taboo_warn = thresholds.get('taboo_warn', 0.80)
        if risk.get('prod_write', 0) == 1 and taboo_score >= taboo_warn:
            trigger_value = {'prod_write': 1, 'taboo_score': taboo_score}
            log_hard_override(
                override_reason=HO02_PROD_WRITE_TABOO_WARN,
                trigger_value=trigger_value,
                state_vector=state_vector,
                policy_version=policy_version,
                threshold_version=threshold_version
            )
            return decision_result_cls(
                decision='block',
                composite_score=0.90,
                artifact_id=state_vector.get('artifact_id', ''),
                policy_version=policy_version,
                factors=[ScoreFactor(
                    name='prod_write_taboo',
                    value=taboo_score,
                    weight=1.0,
                    contribution=0.90,
                    threshold=taboo_warn,
                    threshold_type='warn'
                )],
                exemplar_refs=[],
                action=build_action('process_correction'),
                threshold_version=threshold_version,
                static_gate_summary={'gates_executed': [], 'all_passed': True, 'hard_failures': [], 'warnings': []},
                hard_override=HO02_PROD_WRITE_TABOO_WARN,
                state_vector_ref=f"state://{state_vector.get('run_id', '')}",
                scorer_results=[],
                created_at=datetime.now(timezone.utc)
            )

    return None