create table if not exists decision_events
(
  event_time DateTime64(3),
  run_id String,
  agent_name LowCardinality(String),
  account_name String,
  decision_type LowCardinality(String),
  decision String,
  confidence LowCardinality(String),
  risk_level LowCardinality(String),
  quality_gate_status LowCardinality(String),
  latency_ms Nullable(Float64),
  cost_usd Nullable(Float64),
  model LowCardinality(String),
  evidence_refs Array(String),
  policy_checks Array(String),
  human_feedback String,
  business_outcome String
)
engine = MergeTree
order by (agent_name, account_name, event_time);
