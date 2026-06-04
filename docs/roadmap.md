# Roadmap

## Stage 1 — Public OSS blueprint

Goal: publish a clean public repo and blog the architecture.

Deliverables:

- public agent specs
- public skills
- JSON schemas
- synthetic examples
- security model
- blog series
- basic Python validation utilities

## Stage 2 — Run agents in the wild

Goal: prove that the workflow produces useful signals from public data.

Deliverables:

- weekly public signal report
- synthetic and public-company examples
- source coverage metrics
- quality gate metrics
- manually reviewed findings

## Stage 3 — Local runtime

Goal: move from prompts/specs to executable workflows.

Deliverables:

- source connector interfaces
- Postgres workflow state
- ClickHouse signal and telemetry tables
- trace integration with Langfuse or OpenTelemetry
- simple dashboard

## Stage 4 — Decision Intelligence layer

Goal: analyze agent decisions and outcomes.

Deliverables:

- decision event schema
- decision graph
- recommendation accuracy scoring
- feedback loop
- policy checks
- runtime health score

## Stage 5 — SaaS / BYOC product

Goal: offer a hosted or customer-owned deployment.

Potential packages:

- Account Intelligence Cloud
- Enterprise AI Decision Control Plane
- Agent Fleet Governance
- AI Runtime Intelligence

## Guiding principle

Do not build SaaS until repeated usage proves what customers value enough to pay for.
