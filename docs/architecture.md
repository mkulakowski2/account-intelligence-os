# Architecture

## Core pattern

```text
Agent starts
  -> create scope envelope
  -> collect source evidence
  -> normalize evidence bundle
  -> run reasoning skills
  -> assemble output
  -> run quality gate
  -> emit decision events
```

## Logical layers

### 1. Human knowledge layer

Markdown, Notion, docs, call notes, product notes, architecture playbooks, industry points of view, and internal enablement material.

### 2. Source connector layer

Pluggable connectors for CRM, docs, Slack-like collaboration tools, support systems, community tools, GitHub, job postings, public web, investor relations, blogs, and review sites.

### 3. Evidence bundle layer

Every source result becomes a structured evidence record. Final outputs are only allowed to use claims that trace back to evidence.

### 4. Reasoning layer

Sequential skills for entity resolution, deduplication, scoring, use-case generation, value framing, and architecture validation.

### 5. Output layer

Agent outputs include account packages, daily digests, meeting prep briefs, product signal briefs, and outreach drafts.

### 6. Operational telemetry layer

Every run emits decision events: what the agent decided, why, confidence, latency, cost, source coverage, quality gate status, and feedback.

### 7. Decision Intelligence layer

Future product layer that analyzes agent behavior, signal quality, recommendation accuracy, and business outcomes.

## Suggested local stack

```text
Markdown / Notion / Git
        |
        v
Agent Runtime
        |
        +--> Postgres: scopes, runs, rules, report metadata
        |
        +--> ClickHouse: signals, telemetry, score history, decision events
        |
        +--> Langfuse/OpenTelemetry: traces and evaluations
        |
        v
Decision Intelligence UI
```

## Parallelism rule

Only source collection skills can run in parallel.

Reasoning, scoring, use-case generation, outreach generation, report assembly, and quality validation must run sequentially per account.
