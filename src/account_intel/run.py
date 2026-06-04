"""Account Intelligence OS runner.

Runs a 4-agent Enterprise Digital Twin workflow.

Modes:
- demo: deterministic offline sample data, no network, no API keys
- live: uses Tavily for web search and optional OpenAI/Anthropic for LLM synthesis
- auto: live if TAVILY_API_KEY is present, otherwise demo
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "examples" / "sample_companies.json"
REPORT_DIR = ROOT / "reports"


# ----------------------------- shared utilities -----------------------------

def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "account"


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def normalize_confidence(value: Any, default: float = 0.70) -> float:
    """Normalize LLM/vendor confidence values to a 0.0-1.0 float.

    LLMs sometimes return strings such as "High", "Medium", "85%",
    or "0.85" even when prompted for numeric JSON. The report pipeline
    should never crash because of that; it should coerce safely and clamp.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        v = value.strip().lower()
        mapping = {
            "very high": 0.95,
            "high": 0.85,
            "strong": 0.85,
            "medium-high": 0.75,
            "medium": 0.65,
            "moderate": 0.65,
            "medium-low": 0.50,
            "low": 0.35,
            "weak": 0.35,
            "unknown": default,
            "n/a": default,
            "na": default,
        }
        if v in mapping:
            numeric = mapping[v]
        else:
            # Accept "85%" or strings with a numeric value inside.
            pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", v)
            if pct_match:
                numeric = float(pct_match.group(1)) / 100.0
            else:
                num_match = re.search(r"-?\d+(?:\.\d+)?", v)
                if not num_match:
                    return default
                numeric = float(num_match.group(0))
    else:
        return default

    # If someone returns 85 instead of 0.85, interpret it as a percentage.
    if numeric > 1.0 and numeric <= 100.0:
        numeric = numeric / 100.0
    return max(0.0, min(1.0, numeric))


def normalized_avg_confidence(items: list[dict[str, Any]], default: float = 0.65) -> float:
    return avg([normalize_confidence(item.get("confidence", default), default) for item in items]) or default


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 45) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:800]}") from exc


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """Best-effort JSON object extraction from an LLM response."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*?\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


@dataclass
class Source:
    title: str
    url: str
    snippet: str
    query: str


@dataclass
class AgentResult:
    agent: str
    summary: str
    findings: list[dict[str, Any]]
    confidence: float
    sources: list[dict[str, str]]
    mode: str


# -------------------------------- search layer -------------------------------

class TavilySearchClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[Source]:
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        response = post_json(
            "https://api.tavily.com/search",
            payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        sources = []
        for item in response.get("results", []):
            sources.append(Source(
                title=str(item.get("title", "Untitled source")),
                url=str(item.get("url", "")),
                snippet=str(item.get("content", ""))[:1200],
                query=query,
            ))
        return sources


def collect_live_sources(account: str, search_client: TavilySearchClient, max_results_per_query: int = 4) -> dict[str, list[Source]]:
    query_map = {
        "research_agent": [
            f"{account} company recent news strategy product announcement",
            f"{account} earnings call investor presentation strategic priorities",
        ],
        "technology_agent": [
            f"{account} engineering blog AI data platform architecture",
            f"{account} jobs AI data engineering platform technologies",
        ],
        "organization_agent": [
            f"{account} executive leadership changes hiring growth AI data",
            f"{account} new chief data officer CTO CIO AI leadership",
        ],
    }
    collected: dict[str, list[Source]] = {}
    for agent, queries in query_map.items():
        bucket: list[Source] = []
        seen_urls: set[str] = set()
        for query in queries:
            for source in search_client.search(query, max_results=max_results_per_query):
                if source.url and source.url not in seen_urls:
                    seen_urls.add(source.url)
                    bucket.append(source)
            time.sleep(0.2)
        collected[agent] = bucket
    return collected


# --------------------------------- LLM layer ---------------------------------

class LLMClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def complete_json(self, system_prompt: str, user_prompt: str) -> Optional[dict[str, Any]]:
        response = post_json(
            "https://api.openai.com/v1/chat/completions",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        content = response["choices"][0]["message"]["content"]
        return extract_json_object(content)


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key
        self.model = model

    def complete_json(self, system_prompt: str, user_prompt: str) -> Optional[dict[str, Any]]:
        response = post_json(
            "https://api.anthropic.com/v1/messages",
            {
                "model": self.model,
                "max_tokens": 1800,
                "temperature": 0.2,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        parts = response.get("content", [])
        text = "\n".join(part.get("text", "") for part in parts if part.get("type") == "text")
        return extract_json_object(text)


def resolve_llm_provider(provider: str) -> str:
    """Resolve provider=auto based on available API keys."""
    provider = (provider or "auto").lower()
    if provider != "auto":
        return provider
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


def build_llm_client(provider: str) -> Optional[LLMClient]:
    provider = resolve_llm_provider(provider)
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        return OpenAIClient(key, os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        return AnthropicClient(key, os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"))
    return None


# ------------------------------- agent logic ---------------------------------

AGENT_SYSTEM_PROMPT = """You are an enterprise account intelligence analyst.
Return ONLY valid JSON with keys: summary, findings, confidence.
Each finding must include: signal_type, title, why_it_matters, evidence, source_urls, confidence.
Confidence values MUST be numeric floats from 0.0 to 1.0, never words like High or Medium.
Do not invent facts. Use only the provided source snippets. If evidence is weak, say so clearly.
"""


def sources_to_prompt(sources: list[Source]) -> str:
    lines = []
    for idx, src in enumerate(sources, start=1):
        lines.append(f"SOURCE {idx}")
        lines.append(f"Title: {src.title}")
        lines.append(f"URL: {src.url}")
        lines.append(f"Query: {src.query}")
        lines.append(f"Snippet: {src.snippet}")
        lines.append("")
    return "\n".join(lines)


def llm_agent_result(agent_name: str, account: str, agent_goal: str, sources: list[Source], llm: Optional[LLMClient]) -> Optional[AgentResult]:
    if not llm or not sources:
        return None
    user_prompt = f"""
Account: {account}
Agent: {agent_name}
Goal: {agent_goal}

Analyze the following source snippets and produce 2-5 specific, source-grounded findings. Avoid generic statements. Name concrete products, initiatives, executives, technologies, dates, partnerships, or hiring patterns when present in the snippets. If the snippets are weak, state exactly what is missing.

{sources_to_prompt(sources)}
"""
    payload = llm.complete_json(AGENT_SYSTEM_PROMPT, user_prompt)
    if not payload:
        return None
    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    for finding in findings:
        if isinstance(finding, dict):
            finding["confidence"] = normalize_confidence(finding.get("confidence", 0.65), 0.65)
    return AgentResult(
        agent=agent_name,
        summary=str(payload.get("summary", f"{agent_name} completed analysis.")),
        findings=findings,
        confidence=normalize_confidence(payload.get("confidence", normalized_avg_confidence(findings)), normalized_avg_confidence(findings)),
        sources=[asdict(s) for s in sources],
        mode="live_llm",
    )


def heuristic_agent_result(agent_name: str, account: str, goal: str, sources: list[Source]) -> AgentResult:
    findings = []
    for idx, src in enumerate(sources[:5], start=1):
        title = src.title or f"Source signal {idx}"
        findings.append({
            "signal_type": agent_name.replace("_agent", ""),
            "title": title,
            "why_it_matters": f"This source may contain relevant evidence for {account}: {goal}",
            "evidence": src.snippet[:450],
            "source_urls": [src.url] if src.url else [],
            "confidence": 0.58,
        })
    return AgentResult(
        agent=agent_name,
        summary=f"Collected {len(findings)} source-backed signals for {account}. No LLM key was used, so findings are extractive rather than synthesized.",
        findings=findings,
        confidence=0.58 if findings else 0.0,
        sources=[asdict(s) for s in sources],
        mode="live_search_only",
    )


def run_live_agents(account: str, llm: Optional[LLMClient]) -> tuple[dict[str, Any], list[AgentResult]]:
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        raise RuntimeError("TAVILY_API_KEY is required for live mode. Use --mode demo for offline mode.")
    source_map = collect_live_sources(account, TavilySearchClient(tavily_key))
    total_sources = sum(len(v) for v in source_map.values())
    company = {
        "name": account,
        "slug": slugify(account),
        "description": f"Live Enterprise Digital Twin generated from {total_sources} web search sources. Agent summaries use LLM synthesis when an OpenAI or Anthropic key is configured; otherwise they use extractive search-only findings.",
    }
    goals = {
        "research_agent": "Identify recent market, product, financial, partnership, acquisition, and strategy signals.",
        "technology_agent": "Identify technology adoption, AI/data/platform engineering signals, and architecture clues.",
        "organization_agent": "Identify leadership, hiring, team growth, and organizational priority signals.",
    }
    results: list[AgentResult] = []
    for agent_name, goal in goals.items():
        sources = source_map.get(agent_name, [])
        result = llm_agent_result(agent_name, account, goal, sources, llm) or heuristic_agent_result(agent_name, account, goal, sources)
        results.append(result)

    # Opportunity agent synthesizes prior outputs. Prefer LLM if available, otherwise deterministic synthesis.
    if llm:
        synthesis_sources = []
        for r in results:
            synthesis_sources.append(Source(
                title=f"{r.agent} findings",
                url="internal://agent-output",
                snippet=json.dumps({"summary": r.summary, "findings": r.findings}, indent=2)[:5000],
                query="agent synthesis",
            ))
        opp = llm_agent_result(
            "opportunity_agent",
            account,
            "Synthesize strategic opportunities, risks, recommended plays, and next actions from the other three agents.",
            synthesis_sources,
            llm,
        )
        if opp:
            results.append(opp)
        else:
            results.append(build_heuristic_opportunities(account, results, mode="live_search_only"))
    else:
        results.append(build_heuristic_opportunities(account, results, mode="live_search_only"))
    return company, results


def build_heuristic_opportunities(account: str, previous_results: list[AgentResult], mode: str) -> AgentResult:
    urls = []
    titles = []
    for result in previous_results:
        for finding in result.findings:
            titles.append(str(finding.get("title", "")))
            urls.extend(finding.get("source_urls", []) if isinstance(finding.get("source_urls"), list) else [])
    findings = [
        {
            "signal_type": "recommended_play",
            "title": "Validate the strongest account signal with a human account owner",
            "why_it_matters": "The system found source-backed signals, but the next step is to confirm account context, current initiatives, and timing.",
            "recommended_action": f"Review the top findings for {account}, map them to active opportunities, and decide whether a tailored discovery conversation is warranted.",
            "evidence": "; ".join([t for t in titles if t][:3]) or "No strong titles found.",
            "source_urls": sorted(set(urls))[:5],
            "confidence": 0.62,
        },
        {
            "signal_type": "recommended_play",
            "title": "Create a persistent Digital Twin and monitor changes over time",
            "why_it_matters": "The real value appears when account signals are tracked historically, scored, and compared week over week.",
            "recommended_action": "Schedule recurring runs and store decision events for trend analysis.",
            "evidence": "This run produced metadata-only decision events suitable for future ClickHouse storage.",
            "source_urls": [],
            "confidence": 0.68,
        },
    ]
    return AgentResult(
        agent="opportunity_agent",
        summary="Synthesized recommended plays from the research, technology, and organization agents.",
        findings=findings,
        confidence=0.65,
        sources=[],
        mode=mode,
    )


# ------------------------------- demo mode -----------------------------------

def load_demo_company(account: str) -> dict[str, Any]:
    data = json.loads(DATA_FILE.read_text())
    normalized = account.lower().strip()
    for company in data["companies"]:
        if normalized in {company["name"].lower(), company.get("slug", "").lower()}:
            return company
    return {
        "name": account,
        "slug": slugify(account),
        "description": "Generated offline demo profile. Replace sample data with live search connectors for production use.",
        "recent_events": [
            {"title": "Strategic modernization signal", "why_it_matters": "The account appears suitable for a first digital twin analysis workflow.", "confidence": 0.55, "source": "sample_data"}
        ],
        "technology_signals": [
            {"title": "Generic AI and data platform signal", "technologies": ["AI agents", "analytics", "workflow automation"], "why_it_matters": "These are common entry points for account intelligence research.", "confidence": 0.5, "source": "sample_data"}
        ],
        "organization_signals": [
            {"title": "Unknown org structure", "why_it_matters": "A live source connector should enrich leadership and hiring signals.", "confidence": 0.4, "source": "sample_data"}
        ],
        "recommended_plays": [
            {"title": "Run a deeper source-backed account analysis", "recommended_action": "Connect web, jobs, GitHub, CRM, and call transcript sources.", "why_now": "The offline demo can only prove the workflow shape, not fresh intelligence.", "confidence": 0.5}
        ],
    }


def demo_agent_result(agent_name: str, summary: str, raw_findings: list[dict[str, Any]], signal_type: str) -> AgentResult:
    findings = []
    for item in raw_findings:
        finding = dict(item)
        finding.setdefault("signal_type", signal_type)
        finding.setdefault("source_urls", [])
        finding.setdefault("evidence", finding.get("source", "sample_data"))
        findings.append(finding)
    return AgentResult(
        agent=agent_name,
        summary=summary,
        findings=findings,
        confidence=round(normalized_avg_confidence(findings), 2),
        sources=[],
        mode="demo",
    )


def run_demo_agents(account: str) -> tuple[dict[str, Any], list[AgentResult]]:
    company = load_demo_company(account)
    research = demo_agent_result("research_agent", f"Identified {len(company.get('recent_events', []))} strategic or market signals for {company['name']}.", company.get("recent_events", []), "market_or_strategy")
    technology = demo_agent_result("technology_agent", f"Detected {len(company.get('technology_signals', []))} technology adoption patterns.", company.get("technology_signals", []), "technology_adoption")
    organization = demo_agent_result("organization_agent", f"Found {len(company.get('organization_signals', []))} organization or hiring signals.", company.get("organization_signals", []), "organization_change")
    opportunity_findings = []
    tech_terms = sorted({t for f in technology.findings for t in f.get("technologies", [])})
    for play in company.get("recommended_plays", []):
        opportunity_findings.append({
            "signal_type": "recommended_play",
            "title": play["title"],
            "recommended_action": play["recommended_action"],
            "why_it_matters": play.get("why_now", "The signal deserves follow-up."),
            "related_technologies": tech_terms[:8],
            "confidence": play.get("confidence", 0.8),
        })
    opportunity = AgentResult(
        agent="opportunity_agent",
        summary=f"Synthesized {len(opportunity_findings)} recommended plays from research, technology, and org signals.",
        findings=opportunity_findings,
        confidence=round(normalized_avg_confidence(opportunity_findings), 2),
        sources=[],
        mode="demo",
    )
    return company, [research, technology, organization, opportunity]


# ----------------------------- report generation -----------------------------

def build_decision_events(account: str, results: list[AgentResult], run_mode: str, llm_provider: str) -> list[dict[str, Any]]:
    now = now_iso()
    events = []
    for result in results:
        events.append({
            "event_time": now,
            "account": account,
            "agent": result.agent,
            "decision_type": "agent_analysis",
            "decision": result.summary,
            "confidence": result.confidence,
            "finding_count": len(result.findings),
            "run_mode": run_mode,
            "agent_mode": result.mode,
            "llm_provider": llm_provider,
            "metadata_only": True,
        })
    return events


def render_markdown(company: dict[str, Any], results: list[AgentResult], decision_events: list[dict[str, Any]], run_mode: str) -> str:
    lines = [
        f"# {company['name']} Enterprise Digital Twin",
        "",
        company.get("description", ""),
        "",
        "## Executive Summary",
        "",
        f"Run mode: **{run_mode}**.",
        "",
        "This report is generated by a four-agent Account Intelligence OS workflow: Research, Technology, Organization, and Opportunity agents.",
        "",
    ]
    for result in results:
        lines += [f"## {result.agent.replace('_', ' ').title()}", "", f"**Summary:** {result.summary}", f"**Confidence:** {result.confidence}", f"**Mode:** {result.mode}", ""]
        for idx, finding in enumerate(result.findings, start=1):
            lines.append(f"### {idx}. {finding.get('title', 'Untitled finding')}")
            for key, value in finding.items():
                if key == "title":
                    continue
                label = key.replace("_", " ").title()
                if isinstance(value, list):
                    value = ", ".join(map(str, value)) if value else "None"
                lines.append(f"- **{label}:** {value}")
            lines.append("")
    unique_sources = unique_source_urls(results)
    if unique_sources:
        lines += ["## Sources", ""]
        for idx, source in enumerate(unique_sources, start=1):
            lines.append(f"{idx}. {source}")
        lines.append("")
    lines += [
        "## Decision Events",
        "",
        "These metadata-only events are the seed of the future Decision Intelligence layer.",
        "",
        "```json",
        json.dumps(decision_events, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def unique_source_urls(results: list[AgentResult]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for result in results:
        for finding in result.findings:
            urls = finding.get("source_urls", [])
            if isinstance(urls, str):
                urls = [urls]
            for url in urls:
                if url and url not in seen and not str(url).startswith("internal://"):
                    seen.add(url)
                    ordered.append(str(url))
    return ordered


def _format_value_html(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return '<span class="muted">None</span>'
        parts = []
        for item in value:
            s = str(item)
            if s.startswith("http://") or s.startswith("https://"):
                parts.append(f'<a class="source-link" href="{escape(s)}" target="_blank" rel="noreferrer">{escape(s)}</a>')
            else:
                parts.append(f'<span class="pill">{escape(s)}</span>')
        return "".join(parts)
    if isinstance(value, float):
        return escape(f"{value:.2f}")
    s = str(value)
    if s.startswith("http://") or s.startswith("https://"):
        return f'<a class="source-link" href="{escape(s)}" target="_blank" rel="noreferrer">{escape(s)}</a>'
    return escape(s)


def _confidence_class(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def _score_label(score: float) -> str:
    if score >= 0.8:
        return "High"
    if score >= 0.6:
        return "Medium"
    return "Emerging"


def _agent_label(agent: str) -> str:
    return agent.replace("_agent", "").replace("_", " ").title()


def _top_opportunities(results: list[AgentResult]) -> list[dict[str, Any]]:
    for result in results:
        if result.agent == "opportunity_agent":
            return result.findings[:5]
    return []


def _all_findings(results: list[AgentResult]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for result in results:
        for finding in result.findings:
            item = dict(finding)
            item["agent"] = result.agent
            findings.append(item)
    return findings


def render_html(company: dict[str, Any], results: list[AgentResult], decision_events: list[dict[str, Any]], run_mode: str) -> str:
    account = escape(company["name"])
    description = escape(company.get("description", ""))
    generated_at = escape(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    total_findings = sum(len(r.findings) for r in results)
    avg_conf = round(avg([r.confidence for r in results]), 2)
    source_urls = unique_source_urls(results)
    opportunity_count = len(_top_opportunities(results))
    mode_label = "Live Intelligence" if run_mode == "live" else "Demo Intelligence"

    # Hero opportunity cards.
    opportunity_cards = []
    for item in _top_opportunities(results):
        title = escape(str(item.get("title", "Untitled opportunity")))
        why = escape(str(item.get("why_it_matters") or item.get("why_now") or "Potential account signal worth review."))
        action = escape(str(item.get("recommended_action", "Review this signal with the account team.")))
        conf = normalize_confidence(item.get("confidence", 0.0), 0.0)
        opportunity_cards.append(f"""
          <article class="opportunity-card">
            <div class="card-topline"><span>Recommended Play</span><b>{conf:.2f}</b></div>
            <h3>{title}</h3>
            <p>{why}</p>
            <div class="action-box"><strong>Next move</strong><br>{action}</div>
          </article>
        """)
    if not opportunity_cards:
        opportunity_cards.append("<article class='opportunity-card'><h3>No opportunities generated</h3><p>Run live mode with search and LLM keys for richer analysis.</p></article>")

    # Agent cards and findings.
    agent_sections = []
    for result in results:
        agent_name = escape(_agent_label(result.agent))
        confidence = normalize_confidence(result.confidence, 0.0)
        chips = []
        chips.append(f"<span class='chip'>{len(result.findings)} findings</span>")
        chips.append(f"<span class='chip'>{escape(result.mode)}</span>")
        finding_cards = []
        for finding in result.findings:
            title = escape(str(finding.get("title", "Untitled finding")))
            signal_type = escape(str(finding.get("signal_type", "signal")).replace("_", " ").title())
            why = escape(str(finding.get("why_it_matters") or finding.get("why_now") or finding.get("evidence") or ""))
            conf = normalize_confidence(finding.get("confidence", 0.0), 0.0)
            urls = finding.get("source_urls", [])
            if isinstance(urls, str):
                urls = [urls]
            source_links = "".join(
                f'<a href="{escape(str(u))}" target="_blank" rel="noreferrer">Source</a>'
                for u in urls[:3] if str(u).startswith(("http://", "https://"))
            )
            extra = []
            for key in ["technologies", "related_technologies"]:
                vals = finding.get(key, [])
                if isinstance(vals, list) and vals:
                    extra.append("".join(f"<span class='mini-pill'>{escape(str(v))}</span>" for v in vals[:8]))
            finding_cards.append(f"""
              <article class="signal-card">
                <div class="signal-meta"><span>{signal_type}</span><span class="score {_confidence_class(conf)}">{conf:.2f}</span></div>
                <h4>{title}</h4>
                <p>{why}</p>
                <div class="mini-pills">{''.join(extra)}</div>
                <div class="source-row">{source_links}</div>
              </article>
            """)
        agent_sections.append(f"""
          <section class="agent-section">
            <div class="section-heading">
              <div>
                <p class="eyebrow">Agent Analysis</p>
                <h2>{agent_name}</h2>
              </div>
              <div class="agent-score {_confidence_class(confidence)}">
                <span>{_score_label(confidence)}</span>
                <strong>{confidence:.2f}</strong>
              </div>
            </div>
            <p class="agent-summary">{escape(result.summary)}</p>
            <div class="chip-row">{''.join(chips)}</div>
            <div class="signals-grid">{''.join(finding_cards)}</div>
          </section>
        """)

    # Timeline-style decision events.
    event_items = []
    for event in decision_events:
        event_items.append(f"""
          <li>
            <span class="dot"></span>
            <div>
              <strong>{escape(str(event.get('agent', '')).replace('_agent', '').replace('_', ' ').title())}</strong>
              <p>{escape(str(event.get('decision', '')))}</p>
              <small>confidence {escape(str(event.get('confidence', '')))} · {escape(str(event.get('finding_count', '')))} findings</small>
            </div>
          </li>
        """)

    source_items = "".join(f'<li><a href="{escape(url)}" target="_blank" rel="noreferrer">{escape(url)}</a></li>' for url in source_urls[:20])
    sources_section = f"<section class='panel'><p class='eyebrow'>Evidence</p><h2>Sources</h2><ol class='sources'>{source_items}</ol></section>" if source_urls else ""
    json_blob = escape(json.dumps(decision_events, indent=2))
    notice = "Live mode used external search and optional LLM synthesis based on configured keys." if run_mode == "live" else "Demo mode used local sample data. No external APIs were called."

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{account} Enterprise Digital Twin</title>
  <style>
    :root {{
      --bg: #07090d;
      --bg2: #0d1117;
      --panel: rgba(18, 24, 33, 0.86);
      --panel2: rgba(29, 37, 50, 0.76);
      --text: #f4f7fb;
      --muted: #9aa7b8;
      --line: rgba(255,255,255,0.11);
      --brand: #ffcc02;
      --brand2: #f59e0b;
      --blue: #66d9ef;
      --green: #39d98a;
      --red: #ff6b6b;
      --shadow: 0 24px 80px rgba(0,0,0,.42);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 0%, rgba(255,204,2,.16), transparent 34rem),
        radial-gradient(circle at 80% 12%, rgba(102,217,239,.12), transparent 30rem),
        linear-gradient(180deg, #05070a 0%, #0a0d12 54%, #06080b 100%);
      line-height: 1.5;
    }}
    a {{ color: #ffe08a; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .page {{ max-width: 1220px; margin: 0 auto; padding: 36px 22px 90px; }}
    .hero {{
      position: relative;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 32px;
      padding: 36px;
      background: linear-gradient(135deg, rgba(18,24,33,.94), rgba(13,17,23,.78));
      box-shadow: var(--shadow);
    }}
    .hero:before {{
      content: "";
      position: absolute;
      inset: -1px;
      background: linear-gradient(90deg, rgba(255,204,2,.28), transparent 22%, rgba(102,217,239,.16));
      opacity: .35;
      pointer-events: none;
    }}
    .hero > * {{ position: relative; }}
    .eyebrow {{
      margin: 0 0 10px;
      color: var(--brand);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .14em;
      text-transform: uppercase;
    }}
    h1 {{ font-size: clamp(40px, 6vw, 76px); line-height: .96; letter-spacing: -.055em; margin: 0 0 16px; }}
    h2 {{ font-size: 28px; letter-spacing: -.03em; margin: 0; }}
    h3 {{ font-size: 21px; letter-spacing: -.02em; margin: 0 0 10px; }}
    h4 {{ font-size: 17px; margin: 0 0 10px; }}
    .hero-copy {{ max-width: 820px; color: var(--muted); font-size: 17px; margin: 0; }}
    .notice {{ margin-top: 18px; color: #d7dde7; font-size: 14px; }}
    .meta-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }}
    .badge {{ border: 1px solid var(--line); background: rgba(255,255,255,.055); border-radius: 999px; padding: 8px 12px; color: #dbe4f0; font-size: 13px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 22px; }}
    .kpi {{ border: 1px solid var(--line); border-radius: 22px; background: rgba(255,255,255,.045); padding: 18px; }}
    .kpi span {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .1em; }}
    .kpi strong {{ display: block; font-size: 30px; margin-top: 4px; }}
    .opportunity-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 24px; }}
    .opportunity-card, .panel, .agent-section {{ border: 1px solid var(--line); background: var(--panel); border-radius: 26px; padding: 24px; box-shadow: 0 16px 50px rgba(0,0,0,.24); }}
    .opportunity-card {{ background: linear-gradient(180deg, rgba(255,204,2,.10), rgba(18,24,33,.88)); }}
    .card-topline {{ display:flex; justify-content:space-between; align-items:center; color: var(--brand); font-size: 12px; font-weight: 800; letter-spacing:.1em; text-transform:uppercase; margin-bottom: 12px; }}
    .opportunity-card p, .agent-summary, .signal-card p {{ color: var(--muted); margin: 0 0 14px; }}
    .action-box {{ border-left: 3px solid var(--brand); background: rgba(255,204,2,.08); padding: 12px 14px; border-radius: 12px; color: #f8fafc; font-size: 14px; }}
    .agent-section {{ margin-top: 22px; }}
    .section-heading {{ display:flex; justify-content:space-between; align-items:flex-start; gap: 18px; margin-bottom: 12px; }}
    .agent-score {{ min-width: 96px; text-align:right; border-radius: 18px; padding: 10px 12px; background: rgba(255,255,255,.05); border: 1px solid var(--line); }}
    .agent-score span {{ display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.09em; }}
    .agent-score strong {{ font-size: 24px; }}
    .high strong, .high.score {{ color: var(--green); }}
    .medium strong, .medium.score {{ color: var(--brand); }}
    .low strong, .low.score {{ color: var(--red); }}
    .chip-row, .mini-pills {{ display:flex; flex-wrap:wrap; gap: 8px; margin: 14px 0 0; }}
    .chip, .mini-pill {{ border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.05); color:#dbe4f0; padding:6px 10px; font-size:12px; }}
    .signals-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 18px; }}
    .signal-card {{ border:1px solid var(--line); border-radius: 20px; background: rgba(7,9,13,.42); padding: 18px; }}
    .signal-meta {{ display:flex; justify-content:space-between; align-items:center; gap:12px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing:.08em; margin-bottom: 10px; }}
    .score {{ font-weight: 800; }}
    .source-row {{ margin-top: 12px; display:flex; gap:10px; flex-wrap:wrap; font-size: 13px; }}
    .two-col {{ display:grid; grid-template-columns: 1.15fr .85fr; gap: 18px; margin-top: 22px; }}
    .timeline {{ list-style:none; padding:0; margin:0; }}
    .timeline li {{ position:relative; display:flex; gap:14px; padding: 0 0 18px; }}
    .timeline li:not(:last-child):before {{ content:""; position:absolute; left:7px; top:20px; bottom:0; width:1px; background:var(--line); }}
    .dot {{ width:15px; height:15px; border-radius:50%; background:var(--brand); box-shadow:0 0 0 5px rgba(255,204,2,.12); margin-top:4px; flex:0 0 auto; }}
    .timeline p {{ margin:4px 0; color:var(--muted); }}
    .timeline small {{ color:#c6cfda; }}
    .sources {{ margin: 6px 0 0; padding-left: 20px; color: var(--muted); }}
    .sources li {{ margin: 8px 0; overflow-wrap:anywhere; }}
    pre {{ white-space: pre-wrap; overflow:auto; max-height:420px; border:1px solid var(--line); border-radius:20px; padding:18px; background:#05070a; color:#cbd5e1; font-size:12px; }}
    .footer {{ margin-top:28px; color:var(--muted); font-size:13px; text-align:center; }}
    @media (max-width: 900px) {{ .kpi-grid, .opportunity-grid, .signals-grid, .two-col {{ grid-template-columns: 1fr; }} .hero {{ padding: 26px; }} }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <p class="eyebrow">Account Intelligence OS · Enterprise Digital Twin</p>
      <h1>{account}</h1>
      <p class="hero-copy">{description}</p>
      <p class="notice">{escape(notice)}</p>
      <div class="meta-row">
        <span class="badge">{escape(mode_label)}</span>
        <span class="badge">Generated {generated_at}</span>
        <span class="badge">Metadata-first report</span>
      </div>
      <div class="kpi-grid">
        <div class="kpi"><span>Agents</span><strong>{len(results)}</strong></div>
        <div class="kpi"><span>Findings</span><strong>{total_findings}</strong></div>
        <div class="kpi"><span>Avg Confidence</span><strong>{avg_conf:.2f}</strong></div>
        <div class="kpi"><span>Sources</span><strong>{len(source_urls)}</strong></div>
      </div>
    </section>

    <section style="margin-top:28px">
      <p class="eyebrow">Executive Plays</p>
      <h2>Recommended Account Moves</h2>
      <div class="opportunity-grid">{''.join(opportunity_cards)}</div>
    </section>

    {''.join(agent_sections)}

    <section class="two-col">
      <div class="panel">
        <p class="eyebrow">Decision Trail</p>
        <h2>Agent Decision Events</h2>
        <ol class="timeline">{''.join(event_items)}</ol>
      </div>
      <div class="panel">
        <p class="eyebrow">Product Direction</p>
        <h2>Why This Matters</h2>
        <p class="agent-summary">Digital twins become more valuable when they are run continuously. The next frontier is historical memory, portfolio-level intelligence, and decision analytics across agent fleets.</p>
        <div class="chip-row"><span class="chip">Historical memory</span><span class="chip">Portfolio intelligence</span><span class="chip">Signal scoring</span><span class="chip">Decision analytics</span></div>
      </div>
    </section>

    {sources_section}

    <section class="panel" style="margin-top:22px">
      <p class="eyebrow">Machine Readable</p>
      <h2>Raw Decision Event Payload</h2>
      <pre>{json_blob}</pre>
    </section>
    <p class="footer">Generated by Account Intelligence OS. This report is designed as a public-safe, metadata-first Digital Account Twin.</p>
  </main>
</body>
</html>"""

def write_reports(company: dict[str, Any], results: list[AgentResult], decision_events: list[dict[str, Any]], run_mode: str) -> tuple[Path, Path, Path, dict[str, Any]]:
    REPORT_DIR.mkdir(exist_ok=True)
    slug = slugify(company["name"])
    json_payload = {
        "account": company["name"],
        "generated_at": now_iso(),
        "mode": run_mode,
        "agents": [asdict(r) for r in results],
        "decision_events": decision_events,
    }
    json_path = REPORT_DIR / f"{slug}_digital_twin.json"
    md_path = REPORT_DIR / f"{slug}_digital_twin.md"
    html_path = REPORT_DIR / f"{slug}_digital_twin.html"
    json_path.write_text(json.dumps(json_payload, indent=2))
    md_path.write_text(render_markdown(company, results, decision_events, run_mode))
    html_path.write_text(render_html(company, results, decision_events, run_mode))
    return md_path, json_path, html_path, json_payload



def render_portfolio_index(report_payloads: list[dict[str, Any]], run_mode: str) -> str:
    generated_at = escape(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    cards = []
    for payload in sorted(report_payloads, key=lambda p: str(p.get("account", "")).lower()):
        account = str(payload.get("account", "Unknown"))
        slug = slugify(account)
        agents = payload.get("agents", [])
        total_findings = sum(len(agent.get("findings", [])) for agent in agents if isinstance(agent, dict))
        confidences = [normalize_confidence(agent.get("confidence", 0.0), 0.0) for agent in agents if isinstance(agent, dict)]
        avg_conf = avg(confidences)
        top_titles = []
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            for finding in agent.get("findings", [])[:2]:
                if isinstance(finding, dict) and finding.get("title"):
                    top_titles.append(str(finding["title"]))
        top_signal = top_titles[0] if top_titles else "No signal generated"
        cards.append(f"""
          <a class="account-card" href="{escape(slug)}_digital_twin.html">
            <div class="card-top"><span>{escape(str(payload.get('mode', run_mode)).title())}</span><b>{avg_conf:.2f}</b></div>
            <h2>{escape(account)}</h2>
            <p>{escape(top_signal)}</p>
            <div class="card-stats"><span>{total_findings} findings</span><span>{len(agents)} agents</span></div>
          </a>
        """)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Account Intelligence OS Portfolio Index</title>
  <style>
    :root{{--bg:#05070a;--panel:rgba(18,24,33,.86);--text:#f4f7fb;--muted:#9aa7b8;--line:rgba(255,255,255,.11);--brand:#ffcc02;--blue:#66d9ef}}
    *{{box-sizing:border-box}}
    body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--text);background:radial-gradient(circle at 14% 0%,rgba(255,204,2,.16),transparent 34rem),radial-gradient(circle at 82% 14%,rgba(102,217,239,.12),transparent 30rem),linear-gradient(180deg,#05070a,#0a0d12 58%,#06080b);line-height:1.5}}
    .page{{max-width:1220px;margin:0 auto;padding:38px 22px 90px}}
    .hero{{border:1px solid var(--line);background:linear-gradient(135deg,rgba(18,24,33,.94),rgba(13,17,23,.78));border-radius:32px;padding:36px;box-shadow:0 24px 80px rgba(0,0,0,.42)}}
    .eyebrow{{margin:0 0 10px;color:var(--brand);font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}}
    h1{{font-size:clamp(40px,6vw,72px);line-height:.96;letter-spacing:-.055em;margin:0 0 16px}}
    .hero p{{color:var(--muted);font-size:17px;max-width:780px}}
    .grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:26px}}
    .account-card{{display:block;color:var(--text);text-decoration:none;border:1px solid var(--line);border-radius:26px;padding:24px;background:rgba(18,24,33,.86);box-shadow:0 16px 50px rgba(0,0,0,.24);transition:transform .16s ease,border-color .16s ease}}
    .account-card:hover{{transform:translateY(-3px);border-color:rgba(255,204,2,.45)}}
    .card-top{{display:flex;justify-content:space-between;align-items:center;color:var(--brand);font-size:12px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;margin-bottom:16px}}
    h2{{font-size:26px;letter-spacing:-.03em;margin:0 0 10px}}
    .account-card p{{color:var(--muted);min-height:48px}}
    .card-stats{{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}}
    .card-stats span{{border:1px solid var(--line);border-radius:999px;padding:6px 10px;color:#dbe4f0;background:rgba(255,255,255,.05);font-size:12px}}
    .footer{{margin-top:28px;color:var(--muted);font-size:13px;text-align:center}}
    @media(max-width:900px){{.grid{{grid-template-columns:1fr}}.hero{{padding:26px}}}}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <p class="eyebrow">Account Intelligence OS · Portfolio Run</p>
      <h1>Enterprise Digital Twin Portfolio</h1>
      <p>Generated {generated_at}. This index summarizes all account reports produced in this batch and links to each account dossier.</p>
    </section>
    <section class="grid">{''.join(cards)}</section>
    <p class="footer">Generated by Account Intelligence OS batch mode.</p>
  </main>
</body>
</html>"""

def write_portfolio_index(report_payloads: list[dict[str, Any]], run_mode: str) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    index_path = REPORT_DIR / "index.html"
    index_path.write_text(render_portfolio_index(report_payloads, run_mode))
    return index_path


def run_one_account(account: str, run_mode: str, llm_provider: str) -> tuple[str, Path, Path, Path, dict[str, Any]]:
    resolved_llm_provider = resolve_llm_provider(llm_provider)
    llm: Optional[LLMClient] = None
    if resolved_llm_provider != "none":
        llm = build_llm_client(resolved_llm_provider)
    if run_mode == "live":
        print(f"[account-intel] {account}: mode=live search=tavily llm={resolved_llm_provider}", file=sys.stderr)
        company, results = run_live_agents(account, llm)
    else:
        print(f"[account-intel] {account}: mode=demo search=offline llm=none", file=sys.stderr)
        company, results = run_demo_agents(account)
    decision_events = build_decision_events(company["name"], results, run_mode, resolved_llm_provider)
    md_path, json_path, html_path, json_payload = write_reports(company, results, decision_events, run_mode)
    return company["name"], md_path, json_path, html_path, json_payload


def load_accounts_from_file(path: str) -> list[str]:
    accounts = []
    for line in Path(path).read_text().splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#"):
            accounts.append(clean)
    return accounts


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        return value


def load_workforce_config(path: str) -> dict[str, Any]:
    """Load a tiny YAML subset without adding PyYAML as a dependency.

    Supported shape is intentionally simple and public-repo friendly:

    name: Account Intelligence Workforce
    mode: demo
    parallel: 3
    llm_provider: none
    accounts:
      - Datadog
      - Snowflake
    agents:
      research:
        enabled: true
    """
    config: dict[str, Any] = {"accounts": [], "agents": {}}
    section: Optional[str] = None
    current_agent: Optional[str] = None
    for raw in Path(path).read_text().splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if not raw.startswith(" ") and stripped.endswith(":"):
            section = stripped[:-1]
            current_agent = None
            if section == "accounts":
                config.setdefault("accounts", [])
            elif section == "agents":
                config.setdefault("agents", {})
            else:
                config.setdefault(section, {})
            continue
        if not raw.startswith(" ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            config[key.strip()] = _parse_scalar(value)
            section = None
            current_agent = None
            continue
        if section == "accounts" and stripped.startswith("-"):
            account = stripped[1:].strip().strip('"').strip("'")
            if account:
                config.setdefault("accounts", []).append(account)
            continue
        if section == "agents":
            if raw.startswith("  ") and not raw.startswith("    ") and stripped.endswith(":"):
                current_agent = stripped[:-1]
                config.setdefault("agents", {}).setdefault(current_agent, {})
                continue
            if current_agent and raw.startswith("    ") and ":" in stripped:
                key, value = stripped.split(":", 1)
                config.setdefault("agents", {}).setdefault(current_agent, {})[key.strip()] = _parse_scalar(value)
                continue
        if section == "schedule" and raw.startswith("  ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            config.setdefault("schedule", {})[key.strip()] = _parse_scalar(value)
    return config


def dedupe_accounts(accounts: list[str]) -> list[str]:
    seen_accounts: set[str] = set()
    return [a for a in accounts if a and not (a.lower() in seen_accounts or seen_accounts.add(a.lower()))]


def run_accounts(accounts: list[str], run_mode: str, llm_provider: str, parallel: int, output_format: str = "markdown") -> tuple[list[tuple[str, Path, Path, Path, dict[str, Any]]], list[tuple[str, str]], Optional[Path]]:
    accounts = dedupe_accounts(accounts)
    if not accounts:
        raise ValueError("No accounts provided.")

    if run_mode == "auto":
        run_mode = "live" if os.getenv("TAVILY_API_KEY") else "demo"

    parallel = max(1, int(parallel or 1))
    if run_mode == "live" and parallel > 3:
        print("Warning: live mode parallelism above 3 may hit API rate limits.", file=sys.stderr)

    completed: list[tuple[str, Path, Path, Path, dict[str, Any]]] = []
    failures: list[tuple[str, str]] = []

    if parallel == 1 or len(accounts) == 1:
        for account in accounts:
            try:
                print(f"Running {account}...", file=sys.stderr)
                completed.append(run_one_account(account, run_mode, llm_provider))
            except Exception as exc:
                failures.append((account, str(exc)))
                print(f"FAILED {account}: {exc}", file=sys.stderr)
    else:
        with ThreadPoolExecutor(max_workers=min(parallel, len(accounts))) as executor:
            future_map = {executor.submit(run_one_account, account, run_mode, llm_provider): account for account in accounts}
            for future in as_completed(future_map):
                account = future_map[future]
                try:
                    completed.append(future.result())
                    print(f"Completed {account}.", file=sys.stderr)
                except Exception as exc:
                    failures.append((account, str(exc)))
                    print(f"FAILED {account}: {exc}", file=sys.stderr)

    payloads = [item[4] for item in completed]
    index_path = write_portfolio_index(payloads, run_mode) if len(completed) > 1 else None
    return completed, failures, index_path


def print_run_summary(completed: list[tuple[str, Path, Path, Path, dict[str, Any]]], failures: list[tuple[str, str]], index_path: Optional[Path], output_format: str = "markdown") -> None:
    if len(completed) == 1 and not failures:
        account, md_path, json_path, html_path, json_payload = completed[0]
        if output_format == "json":
            print(json.dumps(json_payload, indent=2))
        elif output_format == "html":
            print(html_path.read_text())
        else:
            print(md_path.read_text())
        print(f"\nSaved reports:\n- {md_path}\n- {json_path}\n- {html_path}\n\nOpen HTML report:\nopen {html_path}", file=sys.stderr if output_format == "json" else sys.stdout)
    else:
        print("\nBatch complete.")
        for account, md_path, json_path, html_path, _ in completed:
            print(f"- {account}: {html_path}")
        if index_path:
            print(f"\nPortfolio index:\nopen {index_path}")
        if failures:
            print("\nFailures:", file=sys.stderr)
            for account, error in failures:
                print(f"- {account}: {error}", file=sys.stderr)
            sys.exit(1)


def handle_workforce(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Run the Account Intelligence Workforce from a manifest.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run the configured Account Intelligence Workforce.")
    run_parser.add_argument("--config", default="workforce.yaml", help="Path to workforce.yaml. Default: workforce.yaml")
    run_parser.add_argument("--mode", choices=["auto", "demo", "live"], help="Override mode from config.")
    run_parser.add_argument("--parallel", type=int, help="Override parallelism from config.")
    run_parser.add_argument("--llm-provider", choices=["auto", "none", "openai", "anthropic"], help="Override LLM provider from config. auto uses OPENAI_API_KEY or ANTHROPIC_API_KEY if present.")
    run_parser.add_argument("--accounts", nargs="+", help="Override accounts from config.")
    run_parser.add_argument("--accounts-file", help="Append accounts from a file.")
    args = parser.parse_args(argv)

    if args.command == "run":
        config = load_workforce_config(args.config)
        accounts = list(args.accounts or config.get("accounts", []))
        if args.accounts_file:
            accounts.extend(load_accounts_from_file(args.accounts_file))
        mode = args.mode or str(config.get("mode", "auto"))
        parallel = args.parallel if args.parallel is not None else int(config.get("parallel", 1))
        llm_provider = args.llm_provider or str(config.get("llm_provider", os.getenv("AIOS_LLM_PROVIDER", "auto")))
        workforce_name = config.get("name", "Account Intelligence Workforce")
        print(f"Running workforce: {workforce_name}", file=sys.stderr)
        completed, failures, index_path = run_accounts(accounts, mode, llm_provider, parallel)
        print_run_summary(completed, failures, index_path)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "workforce":
        handle_workforce(sys.argv[2:])
        return

    parser = argparse.ArgumentParser(description="Run Account Intelligence OS Enterprise Digital Twin agents.")
    parser.add_argument("--account", help="Single company/account name. Try: Datadog, Snowflake, ClickHouse")
    parser.add_argument("--accounts", nargs="+", help="Multiple account names to run in one batch.")
    parser.add_argument("--accounts-file", help="Text file with one account per line. Blank lines and # comments are ignored.")
    parser.add_argument("--parallel", type=int, default=1, help="Number of accounts to process concurrently. Default: 1")
    parser.add_argument("--mode", choices=["auto", "demo", "live"], default="auto", help="auto uses live mode when TAVILY_API_KEY is set, otherwise demo mode")
    parser.add_argument("--llm-provider", choices=["auto", "none", "openai", "anthropic"], default=os.getenv("AIOS_LLM_PROVIDER", "auto"), help="auto uses OPENAI_API_KEY or ANTHROPIC_API_KEY if present")
    parser.add_argument("--format", choices=["markdown", "json", "html"], default="markdown")
    args = parser.parse_args()

    accounts: list[str] = []
    if args.account:
        accounts.append(args.account)
    if args.accounts:
        accounts.extend(args.accounts)
    if args.accounts_file:
        accounts.extend(load_accounts_from_file(args.accounts_file))
    if not accounts:
        parser.error("Provide --account, --accounts, or --accounts-file.")

    completed, failures, index_path = run_accounts(accounts, args.mode, args.llm_provider, args.parallel, args.format)
    print_run_summary(completed, failures, index_path, args.format)


if __name__ == "__main__":
    main()
