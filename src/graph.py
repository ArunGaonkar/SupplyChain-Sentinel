"""Phase 4 — causal graph.

Plain Python (dicts, no networkx/LangGraph needed at this scope) connecting
PolicyEvents to FilingMentions via shared country and/or commodity. This is
the actual cross-referencing step the baseline can't do: it never checks
whether "Ireland cuts pharma tariffs" and "Lilly's API manufacturing is in
Ireland" are talking about the same country.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.models import FilingMention, GraphLink, PolicyEvent

ROOT = Path(__file__).resolve().parent.parent
POLICY_EVENTS_PATH = ROOT / "data" / "policy_events.json"
FILING_MENTIONS_PATH = ROOT / "data" / "filing_mentions.json"
OUTPUT_PATH = ROOT / "data" / "graph_links.json"

# Countries our two agents might name slightly differently for the same place.
COUNTRY_ALIASES = {
    "united states": "united states",
    "usa": "united states",
    "u.s.": "united states",
    "us": "united states",
    "united kingdom": "united kingdom",
    "uk": "united kingdom",
}

# Commodities are free text guided toward config/segments/pharma.yaml's list
# by both agents' prompts, but wording still varies ("API" vs "active
# pharmaceutical ingredients"), so a small synonym map catches the common
# cases without requiring exact string equality.
COMMODITY_SYNONYMS = [
    {"api", "active pharmaceutical ingredient", "active pharmaceutical ingredients", "active ingredient"},
    {"generic drugs", "generic drug", "generics", "generic pharmaceuticals"},
    {"insulin"},
    {"vaccines", "vaccine"},
    {"medical devices", "medical device"},
]


def _norm_country(c: str) -> str:
    c = c.strip().lower()
    return COUNTRY_ALIASES.get(c, c)


def _commodity_match(a: str, b: str) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    if a == b or a in b or b in a:
        return True
    for group in COMMODITY_SYNONYMS:
        if any(term in a for term in group) and any(term in b for term in group):
            return True
    return False


def _link_id(policy_id: str, filing_id: str) -> str:
    return "GL-" + hashlib.sha1(f"{policy_id}|{filing_id}".encode("utf-8")).hexdigest()[:10]


def build_graph(events: list[PolicyEvent], mentions: list[FilingMention]) -> list[GraphLink]:
    links: list[GraphLink] = []
    seen_pairs: set[tuple[str, str, str]] = set()  # (policy_event_id, ticker, normalized_country) — a filing
    # can restate the same country dependency in more than one section (e.g. MD&A and Properties both saying
    # "we manufacture in Ireland"), which would otherwise produce near-duplicate alert cards for one company.
    for event in events:
        event_country = _norm_country(event.country)
        for mention in mentions:
            mention_country = _norm_country(mention.mentioned_country)
            country_match = event_country == mention_country
            commodity_match = _commodity_match(event.affected_product, mention.mentioned_commodity)

            if country_match and commodity_match:
                hop_count, confidence = 1, 0.9
            elif country_match:
                hop_count, confidence = 2, 0.6
            else:
                continue  # commodity-only matches are too weak a signal at this scope; skip

            dedup_key = (event.id, mention.ticker, mention_country)
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)

            links.append(
                GraphLink(
                    id=_link_id(event.id, mention.id),
                    policy_event_id=event.id,
                    filing_mention_id=mention.id,
                    shared_country=event.country if country_match else None,
                    shared_commodity=event.affected_product if commodity_match else None,
                    hop_count=hop_count,
                    confidence=confidence,
                )
            )
    return links


def run_graph(force_refresh: bool = False) -> list[GraphLink]:
    if OUTPUT_PATH.exists() and not force_refresh:
        print(f"[graph] using cached {OUTPUT_PATH}")
        raw = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        return [GraphLink(**link) for link in raw]

    events = [PolicyEvent(**e) for e in json.loads(POLICY_EVENTS_PATH.read_text(encoding="utf-8"))]
    mentions = [FilingMention(**m) for m in json.loads(FILING_MENTIONS_PATH.read_text(encoding="utf-8"))]

    links = build_graph(events, mentions)
    OUTPUT_PATH.write_text(json.dumps([link.model_dump() for link in links], indent=2), encoding="utf-8")
    print(f"[graph] {len(events)} events x {len(mentions)} mentions -> {len(links)} links saved to {OUTPUT_PATH}")
    return links


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_graph()
