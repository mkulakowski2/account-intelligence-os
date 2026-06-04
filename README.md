# Account Intelligence OS

Open-source account intelligence agents for revenue, solutions, and product teams.

Account Intelligence OS is a public, privacy-first blueprint for running agentic account research workflows: deep account packages, daily account signals, meeting prep briefs, and product signal synthesis.

This project is intentionally **runtime-neutral**. You can run the agent specs in Claude, ChatGPT, local LLM workflows, LangGraph, CrewAI, notebooks, or your own internal agent platform.

## Why this exists

Most account research is manual, stale, and scattered across CRM, Slack, docs, support systems, community tools, GitHub, job postings, earnings calls, blogs, and public web signals.

This repo treats account intelligence as an agentic operating system:

```text
Sources -> Evidence Bundle -> Reasoning Skills -> Quality Gate -> Actionable Outputs
```

The long-term thesis is bigger than account research:

```text
Every agentic workflow creates decisions.
Every decision creates telemetry.
Telemetry becomes Decision Intelligence.
```

Account Intelligence OS is the first wedge toward a broader AI Decision Intelligence platform.

## What it includes

- 4 public agent workflows
- reusable source, reasoning, and output skills
- strict evidence contracts
- account isolation rules
- privacy and security model
- optional Postgres + ClickHouse architecture
- synthetic examples
- blog starter kit
- roadmap from OSS blueprint to SaaS product

## Core agents

1. **Account Intelligence Agent** — builds a deep account package.
2. **Daily Signal Agent** — detects meaningful account changes and next-best actions.
3. **Meeting Prep Agent** — creates concise prep briefs before customer meetings.
4. **Product Signal Agent** — turns account and field patterns into product insight.

## Design principles

1. Evidence before claims.
2. Account isolation by default.
3. Source collection can run in parallel; reasoning runs sequentially.
4. Draft actions only; no automatic CRM updates or outbound messages.
5. Metadata-first architecture; sensitive data stays in the customer environment.
6. Pluggable runtimes and sources.

## Quick start: run the local demo

The repo includes a working offline demo. It uses a synthetic source pack, does not call external APIs, and does not send data anywhere.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
account-intel --account Datadog
```

Or run it directly:

```bash
PYTHONPATH=src python3 -m account_intel.run --account Datadog
```

Try additional sample accounts:

```bash
account-intel --account Snowflake
account-intel --account ClickHouse
```

Reports are written to:

```text
reports/<account>_digital_twin.md
reports/<account>_digital_twin.json
reports/<account>_digital_twin.html
```

Open the HTML report locally with:

```bash
open reports/datadog_digital_twin.html
```

The current demo is intentionally local and deterministic. The next milestone is replacing the synthetic source pack with optional public web, jobs, GitHub, CRM export, and call transcript connectors.

## Optional technical architecture

For a local prototype:

- Markdown / Notion / docs for human knowledge and playbooks
- Postgres for workflow state, scopes, rules, and report metadata
- ClickHouse for signal history, agent telemetry, score history, and decision analytics
- Langfuse or OpenTelemetry for trace capture
- A future Decision Intelligence layer for insight, governance, and business outcomes

## Repo structure

```text
agents/        Business workflow agent specs
skills/        Reusable source, reasoning, and output skills
contracts/     JSON schemas for structured outputs and telemetry
docs/          Architecture, security, roadmap, and operating model
examples/      Synthetic outputs and sample evidence
blog/          Public blog starter drafts
src/           Minimal Python utilities for schema validation and events
```

## What this is not

This is not a CRM replacement, a sales engagement tool, a data enrichment scraper, or a system that sends automated outreach.

It is an agentic intelligence layer that turns fragmented account signals into evidence-backed recommendations.

## License

MIT. See `LICENSE`.


## Run the Enterprise Digital Twin demo

This repo now has two modes:

- `demo` mode: fully local, deterministic, no API keys, no network calls.
- `live` mode: uses Tavily for web search and optionally OpenAI or Anthropic for LLM synthesis.

### Local demo mode

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
account-intel --account Datadog --mode demo
open reports/datadog_digital_twin.html
```

### Live web-search mode

```bash
export TAVILY_API_KEY=your_tavily_key
account-intel --account Datadog --mode live
open reports/datadog_digital_twin.html
```

### Live web-search + LLM synthesis

OpenAI:

```bash
export TAVILY_API_KEY=your_tavily_key
export OPENAI_API_KEY=your_openai_key
account-intel --account Datadog --mode live --llm-provider openai
```

Anthropic:

```bash
export TAVILY_API_KEY=your_tavily_key
export ANTHROPIC_API_KEY=your_anthropic_key
account-intel --account Datadog --mode live --llm-provider anthropic
```

Every run writes three files:

```text
reports/<account>_digital_twin.md
reports/<account>_digital_twin.json
reports/<account>_digital_twin.html
```

In live mode, the report includes source URLs. In demo mode, it uses local sample data only.

## Batch and Parallel Runs

Run multiple accounts in one command:

```bash
account-intel --accounts Datadog Snowflake ClickHouse --mode demo --parallel 3
```

Or run from a file:

```bash
account-intel --accounts-file examples/accounts.txt --mode demo --parallel 3
```

Live mode works the same way once `TAVILY_API_KEY` is configured:

```bash
export TAVILY_API_KEY="your_key"
account-intel --accounts-file examples/accounts.txt --mode live --parallel 2
```

With LLM synthesis:

```bash
export OPENAI_API_KEY="your_key"
account-intel --accounts-file examples/accounts.txt --mode live --llm-provider openai --parallel 2
```

Batch runs create individual reports plus a portfolio index:

```text
reports/
├── datadog_digital_twin.html
├── snowflake_digital_twin.html
├── clickhouse_digital_twin.html
└── index.html
```

Open the portfolio index:

```bash
open reports/index.html
```

Keep live parallelism conservative at first. `--parallel 2` or `--parallel 3` is a safer default for API rate limits.

## Phase 1: Account Intelligence Workforce

The Phase 1 runtime turns the single-report demo into a scheduled Account Intelligence Workforce.

Instead of thinking about this as one command that generates one report, think of it as four specialized AI analysts that can be run manually, in batch, or on a schedule:

- Research Agent
- Technology Agent
- Organization Agent
- Opportunity Agent

Run the workforce from the manifest:

```bash
account-intel workforce run --config workforce.yaml
```

Fallback command without CLI installation:

```bash
PYTHONPATH=src python3 -m account_intel.run workforce run --config workforce.yaml
```

The workforce generates:

```text
reports/
├── datadog_digital_twin.html
├── snowflake_digital_twin.html
├── clickhouse_digital_twin.html
└── index.html
```

See `docs/scheduling.md` for cron and Claude Code / Claude Cowork examples.

### Verifying live mode is really using APIs

Live mode requires Tavily search. LLM synthesis is automatic if `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is set.

```bash
export TAVILY_API_KEY="tvly-..."
export OPENAI_API_KEY="sk-..."
account-intel --account Datadog --mode live
```

The command prints diagnostics like:

```text
[account-intel] Datadog: mode=live search=tavily llm=openai
```

If it says `llm=none`, your LLM key is not visible to the shell. If it says `mode=demo`, live mode was not selected or `TAVILY_API_KEY` is missing.

You can also force a provider:

```bash
account-intel --account Datadog --mode live --llm-provider openai
```
