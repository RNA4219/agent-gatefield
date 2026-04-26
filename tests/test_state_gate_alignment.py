"""Contract alignment with agent-state-gate GatefieldAdapter."""

from src.api.http_app import GatefieldService, create_app


def test_decision_packet_contains_state_gate_required_fields():
    service = GatefieldService()

    packet = service.evaluate(
        {
            "artifact_id": "01HART0001",
            "artifact_ref": "artifact://local/01HART0001",
            "diff_hash": "sha256:abc123def456",
            "trace": {
                "run_id": "01HRUN0001",
                "trace_id": "a1b2c3d4e5f6789012345678901234ab",
                "context": {"repo": "agent-gatefield", "artifact_type": "code_patch"},
            },
            "rule_results": {
                "lint": {"status": "pass", "count": 0},
                "sast": {"status": "pass", "count": 0},
                "secret_scan": {"status": "pass", "count": 0},
            },
        }
    )

    required = {
        "schema_version",
        "decision_id",
        "run_id",
        "artifact_id",
        "decision",
        "composite_score",
        "factors",
        "exemplar_refs",
        "action",
        "threshold_version",
        "policy_version",
        "static_gate_summary",
        "created_at",
    }
    assert required.issubset(packet.keys())
    assert packet["schema_version"] == "1.0.0"
    assert packet["decision"] in {"pass", "warn", "hold", "block"}
    assert packet["run_id"] == "01HRUN0001"
    assert packet["trace_id"] == "a1b2c3d4e5f6789012345678901234ab"
    assert packet["state_vector_ref"] == "state://01HRUN0001"
    assert packet["diff_hash"] == "sha256:abc123def456"
    assert packet["artifact_ref"] == {
        "uri": "artifact://local/01HART0001",
        "diff_hash": "sha256:abc123def456",
    }
    assert set(packet["static_gate_summary"]["gates_executed"]) == {"lint", "sast", "secret_scan"}


def test_service_stores_decision_and_state_vector_for_adapter_reads():
    service = GatefieldService()
    packet = service.evaluate(
        {
            "artifact_id": "ART-001",
            "trace": {"run_id": "RUN-001"},
            "rule_results": {},
        }
    )

    assert service.decisions[packet["decision_id"]] == packet
    assert service.state_vectors_by_run["RUN-001"]["artifact_id"] == "ART-001"


def test_service_fallback_semantic_uses_configured_bge_m3_dimensions():
    service = GatefieldService()
    packet = service.evaluate(
        {
            "artifact_id": "ART-002",
            "trace": {"run_id": "RUN-002"},
            "rule_results": {},
        }
    )

    semantic = service.state_vectors_by_run[packet["run_id"]]["semantic"]
    assert semantic["model"] == "BAAI/bge-m3"
    assert semantic["dims"] == 1024
    assert len(semantic["vector"]) == 1024


def test_http_app_registers_state_gate_adapter_routes():
    app = create_app()
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}

    assert ("GET", "/v1/health") in routes
    assert ("POST", "/v1/evaluate") in routes
    assert ("POST", "/v1/review/items") in routes
    assert ("GET", "/v1/decisions/{decision_id}") in routes
    assert ("GET", "/v1/state-vectors/{run_id}") in routes
    assert ("GET", "/v1/audit/{run_id}") in routes
