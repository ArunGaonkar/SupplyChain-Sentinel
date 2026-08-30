"""Phase 4 (part 2) — Alert Cards.

One more LLM call per GraphLink turns a multi-hop link into a plain-English
"why this alert fired" explanation that cites BOTH the policy source and the
filing source. This citation requirement doubles as verification at this
scope: the agent is instructed to ground every claim in the two source
excerpts it's actually given, and not introduce facts absent from them — the
per-link trajectory log lets you check that it didn't. See CHANGELOG.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.llm import call_llm, extract_json, save_trajectory
from src.models import AlertCard, FilingMention, GraphLink, PolicyEvent

POLICY_EVENTS_PATH = ROOT / "data" / "policy_events.json"
FILING_MENTIONS_PATH = ROOT / "data" / "filing_mentions.json"
GRAPH_LINKS_PATH = ROOT / "data" / "graph_links.json"
OUTPUT_PATH = ROOT / "data" / "alert_cards.json"

SYSTEM_PROMPT = """You are the Alert Explainer in a pharma supply-chain intelligence pipeline.

You will be given ONE causal link: a government/news policy event and a
company SEC filing mention that share a country (and possibly a commodity).
Write ONE Alert Card explaining, in plain English for a portfolio manager,
why this pairing matters — e.g. "Country X changed a tariff on Y, and
Company Z's own 10-K already flags exactly this dependency."

Rules:
- Ground every factual claim ONLY in the policy snippet and filing risk_text
  given to you. Do not invent details (specific percentages, dates, dollar
  amounts) that aren't in the provided text.
- Your explanation MUST reference both the policy source and the filing
  source in the text (e.g. "...per the [policy source]..." and "...as
  [Company]'s 10-K discloses...").
- severity: "low", "medium", or "high" — weigh both the policy event's own
  severity and how directly the filing's dependency matches it.
- title: a short (<=100 char) headline for the alert.

Return ONLY a single JSON object with keys: title, severity, explanation.
No markdown fences, no commentary."""


def _build_user_prompt(event: PolicyEvent, mention: FilingMention) -> str:
    return (
        f"POLICY EVENT:\n"
        f"  Country: {event.country}\n"
        f"  Policy type: {event.policy_type}\n"
        f"  Affected product: {event.affected_product}\n"
        f"  Date: {event.date}\n"
        f"  Severity (as assessed by Policy Agent): {event.severity}\n"
        f"  Source: {event.source_url}\n"
        f"  Snippet: {event.snippet}\n\n"
        f"FILING MENTION:\n"
        f"  Company: {mention.company} ({mention.ticker})\n"
        f"  Filing: {mention.filing_type} filed {mention.filing_date}\n"
        f"  Mentioned country: {mention.mentioned_country}\n"
        f"  Mentioned commodity: {mention.mentioned_commodity}\n"
        f"  Source: {mention.source_url}\n"
        f"  Risk text: {mention.risk_text}\n\n"
        f"Write the Alert Card now."
    )


def run_alerts(force_refresh: bool = False) -> list[AlertCard]:
    if OUTPUT_PATH.exists() and not force_refresh:
        print(f"[alerts] using cached {OUTPUT_PATH}")
        raw = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        return [AlertCard(**a) for a in raw]

    events = {e["id"]: PolicyEvent(**e) for e in json.loads(POLICY_EVENTS_PATH.read_text(encoding="utf-8"))}
    mentions = {m["id"]: FilingMention(**m) for m in json.loads(FILING_MENTIONS_PATH.read_text(encoding="utf-8"))}
    links = [GraphLink(**link) for link in json.loads(GRAPH_LINKS_PATH.read_text(encoding="utf-8"))]

    cards: list[AlertCard] = []
    for link in links:
        event = events[link.policy_event_id]
        mention = mentions[link.filing_mention_id]
        user_prompt = _build_user_prompt(event, mention)

        print(f"[alerts] {link.id}: {event.country}/{event.affected_product} <-> {mention.ticker}")
        response = call_llm(SYSTEM_PROMPT, user_prompt, max_tokens=800)
        try:
            obj = extract_json(response)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  [alerts] {link.id}: failed to parse JSON ({e}), skipping")
            save_trajectory("alert_explainer", link.id, SYSTEM_PROMPT, user_prompt, response, parsed=None)
            continue

        card = AlertCard(
            id="AC-" + link.id.removeprefix("GL-"),
            title=obj["title"],
            severity=obj["severity"],
            explanation=obj["explanation"],
            policy_event_id=event.id,
            filing_mention_id=mention.id,
            graph_link_id=link.id,
            policy_source_url=event.source_url,
            filing_source_url=mention.source_url,
        )
        cards.append(card)
        save_trajectory("alert_explainer", link.id, SYSTEM_PROMPT, user_prompt, response, parsed=card.model_dump())

    OUTPUT_PATH.write_text(json.dumps([c.model_dump() for c in cards], indent=2), encoding="utf-8")
    print(f"[alerts] {len(cards)} Alert Cards saved to {OUTPUT_PATH}")
    return cards


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_alerts()
