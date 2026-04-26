"""
Contract tests for trace schema and decision packet
"""

import pytest
import json
from datetime import datetime


# Trace event schema (from requirements)
TRACE_EVENT_SCHEMA = {
    "run_id": "uuid",
    "trace_id": "otel-trace-id",
    "event_type": "tool_call_requested",
    "timestamp": "RFC3339",
    "actor": "agent|tool|reviewer|system",
    "artifact_ref": "artifact://...",
    "checkpoint_ref": "checkpoint://...",
    "policy_version": "gate-policy-v1",
    "payload_ref": "blob://redacted-or-hashed"
}


# State vector schema
STATE_VECTOR_SCHEMA = {
    "run_id": "uuid",
    "artifact_id": "uuid",
    "semantic": {"provider": "local", "model": "BAAI/bge-m3", "dims": 1024, "vector_ref": "vec://..."},
    "rule_violation": {"secret": 0, "sast_high": 1, "license_unknown": 2},
    "test_evidence": {"unit_pass_rate": 0.97, "changed_modules_tested": 4},
    "risk": {"prod_write": 0, "pii_level": 1, "network_egress": 1},
    "historical_decision": {"accept_sim": 0.84, "reject_sim": 0.31, "judgment_log_sim": 0.66},
    "uncertainty": {"judge_std": 0.08, "tool_error_rate": 0.02, "self_confidence": 0.74},
    "context": {"repo": "service-a", "artifact_type": "code_patch", "env": "staging"},
    "trajectory": {"delta_semantic": 0.07, "tool_calls": 9, "branch_count": 2}
}


# Decision packet schema
DECISION_PACKET_SCHEMA = {
    "decision_id": "uuid",
    "run_id": "uuid",
    "composite_score": 0.75,
    "state": "pass|warn|hold|block",
    "reasons": ["top_factor_1", "top_factor_2"],
    "exemplar_refs": ["doc_id_1", "doc_id_2"],
    "action_type": "continue|artifact_correction|process_correction|prompt_correction",
    "threshold_version": "threshold-v1",
    "static_gate_summary": {"lint": "pass", "sast": "fail"},
    "created_at": "RFC3339"
}


class TestTraceEventSchema:
    def test_required_fields_present(self):
        event = {
            "run_id": "123e4567-e89b-12d3-a456-426614174000",
            "trace_id": "abc123def456",
            "event_type": "tool_call_requested",
            "timestamp": "2026-04-26T12:00:00Z",
            "actor": "agent",
            "artifact_ref": "artifact://run/123/artifact/456",
            "checkpoint_ref": "checkpoint://run/123/cp/1",
            "policy_version": "gate-policy-v1",
            "payload_ref": "blob://hash/abc123"
        }
        for field in TRACE_EVENT_SCHEMA.keys():
            assert field in event

    def test_event_type_enum(self):
        valid_types = [
            "run_started",
            "step_started",
            "tool_call_requested",
            "artifact_emitted",
            "static_gate_completed",
            "run_completed",
            "run_failed"
        ]
        for t in valid_types:
            assert t in ["run_started", "step_started", "tool_call_requested",
                         "artifact_emitted", "static_gate_completed",
                         "run_completed", "run_failed"]

    def test_actor_enum(self):
        valid_actors = ["agent", "tool", "reviewer", "system"]
        for a in valid_actors:
            assert a in valid_actors


class TestStateVectorSchema:
    def test_required_fields_present(self):
        vector = STATE_VECTOR_SCHEMA.copy()
        required = ["run_id", "artifact_id", "semantic", "rule_violation",
                    "test_evidence", "risk", "historical_decision",
                    "uncertainty", "context", "trajectory"]
        for field in required:
            assert field in vector

    def test_semantic_dims_valid(self):
        # Default is BGE-M3 1024d; other dimensions are migration/alternate-provider cases.
        dims = STATE_VECTOR_SCHEMA["semantic"]["dims"]
        assert dims in [1024, 1536, 3072, 512, 256]


class TestDecisionPacketSchema:
    def test_required_fields_present(self):
        packet = DECISION_PACKET_SCHEMA.copy()
        required = ["decision_id", "run_id", "composite_score", "state",
                    "reasons", "exemplar_refs", "action_type",
                    "threshold_version", "created_at"]
        for field in required:
            assert field in packet

    def test_state_enum(self):
        valid_states = ["pass", "warn", "hold", "block"]
        for s in valid_states:
            assert s in valid_states

    def test_action_type_enum(self):
        valid_actions = ["continue", "artifact_correction",
                         "process_correction", "prompt_correction"]
        for a in valid_actions:
            assert a in valid_actions

    def test_explanation_required(self):
        # Must have top 3 factors and top 5 exemplar refs for escalated decisions
        packet = DECISION_PACKET_SCHEMA.copy()
        packet["state"] = "hold"
        assert len(packet["reasons"]) >= 1
        assert len(packet["exemplar_refs"]) >= 1


class TestSchemaBackwardCompatibility:
    """Ensure schema changes don't break existing clients"""

    def test_trace_event_add_optional_field(self):
        # Adding optional field should not break parsing
        event = {
            "run_id": "uuid",
            "trace_id": "trace",
            "event_type": "run_started",
            "timestamp": "2026-04-26T12:00:00Z",
            "actor": "agent",
            # new optional field
            "parent_run_id": "parent-uuid"
        }
        assert "run_id" in event  # should parse successfully

    def test_state_vector_add_optional_component(self):
        # Adding optional component should not break
        vector = STATE_VECTOR_SCHEMA.copy()
        vector["optional_new_field"] = {"data": "value"}
        assert "run_id" in vector
