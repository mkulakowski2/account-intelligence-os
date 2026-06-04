create table if not exists agent_runs (
  run_id text primary key,
  agent_name text not null,
  account_name text not null,
  canonical_domain text,
  status text not null,
  started_at timestamptz default now(),
  completed_at timestamptz,
  quality_gate_status text
);

create table if not exists policies (
  policy_id text primary key,
  policy_name text not null,
  policy_type text not null,
  rule_text text not null,
  severity text not null,
  created_at timestamptz default now()
);
