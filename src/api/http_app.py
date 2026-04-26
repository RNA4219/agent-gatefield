"""Aiohttp HTTP API aligned with agent-state-gate GatefieldAdapter.

The API is intentionally thin: it exposes the existing DecisionEngine,
ReviewQueue, state-vector lookup, and audit export without redefining their
schemas. Persistence is in-memory by default so contract tests and local
integration can run without PostgreSQL.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from aiohttp import web

from src.core.engine import DecisionEngine
from src.review.dataclasses import ReviewItem
from src.review.queue import ReviewQueue


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _load_config(config_path: str | None = None) -> dict[str, Any]:
    path = Path(config_path or "config/gate-config.yaml")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _engine_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "thresholds": config.get("thresholds") or config.get("state_space_gate", {}).get("thresholds", {}),
        "hard_overrides": config.get("state_space_gate", {}).get("hard_overrides", {}),
        "state_space_gate": config.get("state_space_gate", {}),
        "threshold_version": config.get("threshold_version", "sha256:threshold-v1-hash"),
        "policy_version": config.get("policy_version", "gate-policy-v1"),
        "actions": config.get("actions", {}),
    }


def _trace_id(value: str | None) -> str:
    if value:
        return value
    return hashlib.sha256(str(uuid.uuid4()).encode("utf-8")).hexdigest()[:32]


def _rule_results_to_violations(rule_results: dict[str, Any]) -> dict[str, int]:
    mapping = {
        "secret_scan": "secret",
        "secret": "secret",
        "sast": "sast_high",
        "lint": "lint_error",
        "typecheck": "type_error",
        "license_scan": "license_forbidden",
        "tool_policy": "tool_policy_deny",
    }
    violations: dict[str, int] = {}
    for gate_name, result in (rule_results or {}).items():
        if not isinstance(result, dict):
            continue
        status = str(result.get("status", "")).lower()
        severity = str(result.get("severity", "")).lower()
        count = int(result.get("count", 0) or 0)
        if status in {"fail", "failed", "error", "deny", "block"} or severity in {"critical", "high"}:
            violations[mapping.get(gate_name, gate_name)] = count or 1
        elif status in {"warn", "warning"} and count:
            violations[f"{mapping.get(gate_name, gate_name)}_warning"] = count
    return violations


class GatefieldService:
    """Service layer backing the HTTP handlers."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or _load_config()
        self.engine = DecisionEngine(_engine_config(self.config))
        self.review_queue = ReviewQueue()
        self.decisions: dict[str, dict[str, Any]] = {}
        self.state_vectors_by_run: dict[str, dict[str, Any]] = {}
        self.audit_events_by_run: dict[str, list[dict[str, Any]]] = {}

    def build_state_vector(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("state_vector"):
            state_vector = dict(payload["state_vector"])
        else:
            trace = payload.get("trace") or {}
            run_id = payload.get("run_id") or trace.get("run_id") or str(uuid.uuid4())
            artifact_id = payload.get("artifact_id") or str(uuid.uuid4())
            rule_results = payload.get("rule_results") or {}
            state_vector = {
                "schema_version": "1.0.0",
                "run_id": run_id,
                "artifact_id": artifact_id,
                "trace_id": _trace_id(trace.get("trace_id")),
                "semantic": payload.get("semantic") or {"vector": [0.5] * 1536},
                "rule_violation": _rule_results_to_violations(rule_results),
                "test_evidence": payload.get("test_evidence") or {"unit_pass_rate": 1.0},
                "risk": payload.get("risk") or {},
                "historical_decision": payload.get("historical_decision") or {},
                "uncertainty": payload.get("uncertainty") or {"judge_std": 0.05},
                "context": payload.get("context") or trace.get("context") or {"repo": "", "artifact_type": ""},
                "trajectory": payload.get("trajectory") or {},
                "static_gate_results": rule_results,
                "artifact_ref": payload.get("artifact_ref"),
                "diff_hash": payload.get("diff_hash"),
            }

        state_vector.setdefault("schema_version", "1.0.0")
        state_vector.setdefault("run_id", payload.get("run_id") or str(uuid.uuid4()))
        state_vector.setdefault("artifact_id", payload.get("artifact_id") or str(uuid.uuid4()))
        trace = payload.get("trace") or {}
        state_vector.setdefault("trace_id", _trace_id(trace.get("trace_id")))
        return state_vector

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        state_vector = self.build_state_vector(payload)
        result = self.engine.evaluate(state_vector).to_dict()
        self.state_vectors_by_run[result["run_id"]] = state_vector
        self.decisions[result["decision_id"]] = result
        self.audit_events_by_run.setdefault(result["run_id"], []).append(
            {
                "schema_version": "1.0.0",
                "event_id": str(uuid.uuid4()),
                "trace_id": result.get("trace_id") or _trace_id(None),
                "span_id": (result.get("trace_id") or _trace_id(None))[:16],
                "run_id": result["run_id"],
                "event_type": "gate_decision",
                "actor": "gate_engine",
                "payload_hash": hashlib.sha256(str(result).encode("utf-8")).hexdigest(),
                "retention_class": "audit",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return result

    def enqueue_review(self, payload: dict[str, Any]) -> str:
        decision_id = payload.get("decision_id") or str(uuid.uuid4())
        item = ReviewItem(
            decision_id=decision_id,
            run_id=payload.get("run_id") or "",
            state=payload.get("state") or payload.get("decision") or "hold",
            composite_score=float(payload.get("composite_score", 0.0)),
            severity=str(payload.get("severity", "medium")).lower(),
            top_factors=list(payload.get("top_factors") or []),
            artifact_ref=payload.get("artifact_ref") or "",
            trace_ref=payload.get("trace_ref") or "",
            created_at=datetime.now(timezone.utc),
            exemplar_refs=list(payload.get("exemplar_refs") or []),
            checkpoint_ref=payload.get("checkpoint_ref"),
        )
        self.review_queue.enqueue(item)
        return item.review_id


SERVICE_KEY = web.AppKey("service", GatefieldService)


def create_app(config: dict[str, Any] | None = None) -> web.Application:
    service = GatefieldService(config)
    app = web.Application()
    app[SERVICE_KEY] = service

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "agent-gatefield"})

    async def evaluate(request: web.Request) -> web.Response:
        payload = await request.json()
        return web.json_response(service.evaluate(payload), dumps=lambda obj: __import__("json").dumps(obj, default=_json_default))

    async def enqueue_review(request: web.Request) -> web.Response:
        payload = await request.json()
        return web.json_response({"review_id": service.enqueue_review(payload)})

    async def get_decision(request: web.Request) -> web.Response:
        decision_id = request.match_info["decision_id"]
        packet = service.decisions.get(decision_id)
        if not packet:
            raise web.HTTPNotFound(text=f"Decision not found: {decision_id}")
        return web.json_response(packet, dumps=lambda obj: __import__("json").dumps(obj, default=_json_default))

    async def get_state_vector(request: web.Request) -> web.Response:
        run_id = request.match_info["run_id"]
        vector = service.state_vectors_by_run.get(run_id)
        if not vector:
            raise web.HTTPNotFound(text=f"State vector not found: {run_id}")
        return web.json_response(vector, dumps=lambda obj: __import__("json").dumps(obj, default=_json_default))

    async def export_audit(request: web.Request) -> web.Response:
        run_id = request.match_info["run_id"]
        events = service.audit_events_by_run.get(run_id, [])
        return web.json_response({"audit_events": events}, dumps=lambda obj: __import__("json").dumps(obj, default=_json_default))

    app.router.add_get("/v1/health", health)
    app.router.add_post("/v1/evaluate", evaluate)
    app.router.add_post("/v1/review/items", enqueue_review)
    app.router.add_get("/v1/decisions/{decision_id}", get_decision)
    app.router.add_get("/v1/state-vectors/{run_id}", get_state_vector)
    app.router.add_get("/v1/audit/{run_id}", export_audit)
    return app


def main() -> None:
    web.run_app(create_app(), host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
