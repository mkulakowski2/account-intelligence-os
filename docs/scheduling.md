# Scheduling the Account Intelligence Workforce

Phase 1 introduces a workforce-oriented runtime. The goal is simple: run the same account intelligence workflow every day, across one account or an entire portfolio, and generate fresh Digital Twin reports.

## Run the workforce manually

```bash
account-intel workforce run --config workforce.yaml
```

Or without installing the package:

```bash
PYTHONPATH=src python3 -m account_intel.run workforce run --config workforce.yaml
```

## Run a single account

```bash
account-intel --account Datadog --mode demo
```

## Run multiple accounts

```bash
account-intel --accounts Datadog Snowflake ClickHouse --mode demo --parallel 3
```

## Run from an accounts file

```bash
account-intel --accounts-file examples/accounts.txt --mode demo --parallel 3
```

## Run daily with cron

Open your crontab:

```bash
crontab -e
```

Add this example to run every weekday at 7 AM:

```bash
0 7 * * 1-5 cd /path/to/account-intelligence-os-public && source .venv/bin/activate && account-intel workforce run --config workforce.yaml >> /tmp/account-intel.out 2>> /tmp/account-intel.err
```

## Run through Claude Code / Claude Cowork

Use this instruction as the scheduled task:

```text
Every weekday at 7 AM, open the Account Intelligence OS repo and run:
account-intel workforce run --config workforce.yaml

After the run finishes, summarize reports/index.html and highlight the top new account opportunities, risks, and technology signals.
```

## Live mode keys

Demo mode needs no keys. Live mode needs search and optionally an LLM provider:

```bash
export TAVILY_API_KEY="your_tavily_key"
export OPENAI_API_KEY="your_openai_key"
account-intel workforce run --config workforce.yaml --mode live --llm-provider openai
```

or:

```bash
export TAVILY_API_KEY="your_tavily_key"
export ANTHROPIC_API_KEY="your_anthropic_key"
account-intel workforce run --config workforce.yaml --mode live --llm-provider anthropic
```
