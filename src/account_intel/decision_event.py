from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class DecisionEvent:
    run_id: str
    agent_name: str
    account_name: str
    decision_type: str
    decision: str
    confidence: float
    evidence_refs: List[str]
    quality_gate_status: str
    event_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    risk_level: str = "unknown"
    latency_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None

    def to_dict(self):
        return asdict(self)
