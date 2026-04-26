"""
Audit Logger - OTel compatible
"""

import json
import hashlib
from typing import Dict, Optional
from datetime import datetime, timezone
from dataclasses import dataclass


@dataclass
class AuditEvent:
    trace_id: str
    span_id: str
    run_id: str
    event_type: str
    actor: str
    payload_hash: str
    payload_ref: Optional[str]
    retention_class: str


class AuditLogger:
    """Audit event logger with OTel compatibility"""

    def __init__(self):
        self.events: list[AuditEvent] = []

    def log_event(
        self,
        trace_id: str,
        span_id: str,
        run_id: str,
        event_type: str,
        actor: str,
        payload: Dict = None,
        retention_class: str = "audit"
    ) -> AuditEvent:
        """Log an audit event"""
        payload_hash = ""
        payload_ref = None

        if payload:
            payload_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest()[:64]

        event = AuditEvent(
            trace_id=trace_id,
            span_id=span_id,
            run_id=run_id,
            event_type=event_type,
            actor=actor,
            payload_hash=payload_hash,
            payload_ref=payload_ref,
            retention_class=retention_class
        )

        self.events.append(event)
        return event

    def log_decision(
        self,
        trace_id: str,
        run_id: str,
        decision: Dict
    ) -> AuditEvent:
        """Log gate decision"""
        return self.log_event(
            trace_id=trace_id,
            span_id=f"{trace_id[:16]}-decision",
            run_id=run_id,
            event_type="gate_decision",
            actor="gate_engine",
            payload=decision,
            retention_class="audit"
        )

    def log_review(
        self,
        trace_id: str,
        run_id: str,
        review: Dict
    ) -> AuditEvent:
        """Log human review action"""
        return self.log_event(
            trace_id=trace_id,
            span_id=f"{trace_id[:16]}-review",
            run_id=run_id,
            event_type="human_review",
            actor=review.get("reviewer", "unknown"),
            payload=review,
            retention_class="audit"
        )

    def log_correction(
        self,
        trace_id: str,
        run_id: str,
        correction: Dict
    ) -> AuditEvent:
        """Log correction action"""
        return self.log_event(
            trace_id=trace_id,
            span_id=f"{trace_id[:16]}-correction",
            run_id=run_id,
            event_type="correction",
            actor="correction_engine",
            payload=correction,
            retention_class="audit"
        )

    def export_otlp(self) -> list[Dict]:
        """Export events in OTLP format"""
        return [
            {
                "traceId": e.trace_id,
                "spanId": e.span_id,
                "timeUnixNano": int(datetime.now(timezone.utc).timestamp() * 1e9),
                "attributes": {
                    "run_id": e.run_id,
                    "event_type": e.event_type,
                    "actor": e.actor,
                    "payload_hash": e.payload_hash,
                    "retention_class": e.retention_class
                }
            }
            for e in self.events
        ]

    def export_jsonl(self) -> str:
        """Export events as JSONL"""
        lines = []
        for e in self.events:
            lines.append(json.dumps({
                "trace_id": e.trace_id,
                "span_id": e.span_id,
                "run_id": e.run_id,
                "event_type": e.event_type,
                "actor": e.actor,
                "payload_hash": e.payload_hash,
                "retention_class": e.retention_class,
                "created_at": datetime.now(timezone.utc).isoformat()
            }))
        return "\n".join(lines)

    def get_by_run(self, run_id: str) -> list[AuditEvent]:
        """Get all events for a run"""
        return [e for e in self.events if e.run_id == run_id]