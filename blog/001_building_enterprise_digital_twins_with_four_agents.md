# Building Enterprise Digital Twins with Four Local AI Agents

Most account research is broken because it is static.

A CRM record tells you what someone knew last quarter. A meeting note tells you what happened in one conversation. A dashboard tells you what was already instrumented. But strategic accounts are living systems. They change every day.

A company launches a new AI initiative. A new data leader joins. Hiring patterns shift. Engineering blogs reveal a new architecture direction. A competitor appears in job descriptions. A product team starts experimenting with real-time analytics, agent observability, or workflow automation.

By the time an account team manually discovers those signals, the window may already be closing.

The idea behind Account Intelligence OS is simple:

> Every strategic account should have a continuously updated digital twin.

Not a CRM profile. Not a dashboard. Not a pile of notes. A living account model that can answer:

- What changed?
- Why does it matter?
- What evidence supports it?
- What should we do next?
- How confident are we?

## The four-agent model

The first version uses four agents.

```text
Company / Account
       |
       v
Research Agent
       |
       v
Technology Agent
       |
       v
Organization Agent
       |
       v
Opportunity Agent
       |
       v
Enterprise Digital Twin Report
```

### 1. Research Agent

The Research Agent looks for strategic and market signals: company direction, product moves, partnerships, acquisitions, public narratives, and business priorities.

### 2. Technology Agent

The Technology Agent looks for architecture and implementation signals: job postings, engineering blogs, GitHub activity, technical language, data platforms, AI infrastructure, observability, streaming, and workflow automation.

### 3. Organization Agent

The Organization Agent looks for people and operating model signals: leadership changes, hiring trends, team formation, reporting lines, and buyer alignment.

### 4. Opportunity Agent

The Opportunity Agent does the synthesis. It consumes the other agents' outputs and turns raw signals into recommended plays, risks, next-best actions, and account strategy.

The important idea is that the agents do not just summarize. They create structured decision events.

Those events later become the foundation for Decision Intelligence.

## Try it locally

This repository now includes a working offline demo. It does not call external APIs, does not need an LLM key, and does not send data anywhere. It runs against a small synthetic source pack so people can experience the workflow immediately.

Clone the repo:

```bash
git clone https://github.com/YOUR_ORG/account-intelligence-os.git
cd account-intelligence-os
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the package:

```bash
pip install -e .
```

Run the sample Digital Twin workflow:

```bash
account-intel --account Datadog
```

Or run it directly with Python:

```bash
python -m account_intel.run --account Datadog
```

You can also try:

```bash
python -m account_intel.run --account Snowflake
python -m account_intel.run --account ClickHouse
```

The demo writes reports to:

```text
reports/datadog_digital_twin.md
reports/datadog_digital_twin.html
reports/datadog_digital_twin.json
```

## Example output

```text
Datadog Enterprise Digital Twin

Research Agent
- Expansion from observability into broader platform operations
- Security and developer workflow adjacency

Technology Agent
- Observability-native architecture pattern
- AI operations use case adjacency

Organization Agent
- Platform buyer alignment

Opportunity Agent
- AI Runtime Intelligence Workshop
- Decision Event Analytics Demo
```

The JSON output also includes metadata-only decision events:

```json
{
  "account": "Datadog",
  "agent": "technology_agent",
  "decision_type": "agent_analysis",
  "confidence": 0.83,
  "finding_count": 2,
  "metadata_only": true
}
```

That part matters.

The first product is account intelligence.

The larger opportunity is understanding how AI systems make decisions over time.

## Why metadata-only matters

Most enterprises will not send prompts, customer records, CRM data, or internal documents into a random SaaS product.

So the architecture starts with a metadata-first model.

The local demo captures:

- agent name
- decision type
- confidence
- finding count
- account name
- timestamp
- metadata-only flag

It does not capture sensitive account data.

That is intentional. If this becomes an enterprise product, customers should be able to choose their data boundary:

- metadata only
- redacted prompts
- full traces in customer-owned storage
- hybrid control plane

## Roadmap

### Phase 1: Local Digital Twin Demo

The first milestone is a working local demo:

- four-agent workflow
- sample company source pack
- markdown report output
- JSON report output
- metadata-only decision events

### Phase 2: Real Source Connectors

Next, replace the synthetic source pack with optional connectors:

- public web search
- company websites
- job postings
- GitHub
- earnings transcripts
- news
- CRM exports
- call transcripts

### Phase 3: Streamlit Command Center

Then add a visual command center:

- account list
- signal timeline
- agent activity
- opportunity map
- report viewer
- decision event explorer

### Phase 4: ClickHouse Decision Analytics

Once agents produce events continuously, store them in ClickHouse:

- decision events
- signal history
- confidence trends
- agent performance
- account change timelines

This is where the project starts becoming more than account intelligence.

It becomes operational analytics for AI systems.

### Phase 5: Decision Intelligence

The final direction is a broader platform for AI Decision Intelligence:

- Which agents are creating value?
- Which agents are drifting?
- Which decisions led to revenue?
- Which decisions introduced risk?
- Which workflows require human review?

That is the bigger category.

Account Intelligence OS is the first wedge.

## Final thought

The future of enterprise AI will not be one giant agent.

It will be fleets of specialized agents creating decisions, signals, recommendations, and actions every day.

The companies that win will not simply deploy agents.

They will understand them.

Account Intelligence OS starts with one practical question:

> Can four local agents create a useful digital twin of a strategic account?

The first demo says yes.

Now the next step is to make it real, connected, observable, and continuously learning.


## Runnable Example

The project includes a local runnable version of the four-agent workflow. You can run it in demo mode with no API keys, or in live mode with web search and optional LLM synthesis.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
account-intel --account Datadog --mode demo
open reports/datadog_digital_twin.html
```

For a source-backed live run:

```bash
export TAVILY_API_KEY=your_tavily_key
account-intel --account Datadog --mode live
open reports/datadog_digital_twin.html
```

For LLM synthesis on top of live search:

```bash
export TAVILY_API_KEY=your_tavily_key
export OPENAI_API_KEY=your_openai_key
account-intel --account Datadog --mode live --llm-provider openai
```

The output is a Markdown, JSON, and HTML Enterprise Digital Twin report generated by four agents: Research, Technology, Organization, and Opportunity.
