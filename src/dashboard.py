"""Phase 5 — static dashboard (v3).

Renders Alert Cards + a Gap/Opportunity view + an interactive dependency
graph to a single static HTML file via Jinja2, plus a separate glossary
page. No backend framework, no JS build step, no external JS/CSS
dependencies — open dist/index.html directly in a browser. Zero network
calls: reads only the JSON artifacts already produced in data/ by earlier
phases.

The dependency graph is rendered CLIENT-SIDE (vanilla JS, embedded graph
data as JSON) rather than baked into static SVG, because it needs to
re-layout dynamically: a time-range filter changes which nodes/edges are
visible, and a detail-level toggle changes the column structure itself
(Catalyst -> Country -> Company vs. the fuller Catalyst -> Policy Scope ->
Country -> Company). See templates/dashboard.html.jinja for the renderer.

Gap vs. Opportunity (both surfaced because neither side of the graph is
"more correct" than the other — a link needs BOTH a PolicyEvent and a
FilingMention, and either side can be missing):
  - Gap: a FilingMention with no matching PolicyEvent — a company disclosed
    a real dependency, but no policy action confirms it yet.
  - Opportunity: a PolicyEvent with no matching FilingMention — a real
    policy action happened, but no covered company's filing has been tied
    to it yet (worth a closer read of that company's filing, or means no
    covered company is exposed).

The per-alert checkbox is a stand-in for the human-approval principle (state
kept client-side in localStorage, no server) — a full approval workflow
(FastAPI + persistence) is a natural next step, not required to prove the
concept, since these alerts only inform a human decision-maker and take no
action themselves. See README.md "Out of scope".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader

DATA_DIR = ROOT / "data"
TEMPLATES_DIR = ROOT / "templates"
OUTPUT_PATH = ROOT / "dist" / "index.html"
GLOSSARY_OUTPUT_PATH = ROOT / "dist" / "glossary.html"

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _load(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _iso_date(yyyymmdd: str) -> str:
    """'20260409' -> '2026-04-09' (also passes through already-ISO dates)."""
    s = (yyyymmdd or "").replace("-", "")
    if len(s) == 8:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return yyyymmdd or ""


def build_dashboard() -> Path:
    events = _load("policy_events.json")
    mentions = _load("filing_mentions.json")
    links = _load("graph_links.json")
    cards = _load("alert_cards.json")

    events_by_id = {e["id"]: e for e in events}
    mentions_by_id = {m["id"]: m for m in mentions}
    links_by_id = {link["id"]: link for link in links}

    cards_sorted = sorted(cards, key=lambda c: SEVERITY_ORDER.get(c["severity"], 3))
    enriched_cards = []
    for card in cards_sorted:
        event = events_by_id.get(card["policy_event_id"], {})
        mention = mentions_by_id.get(card["filing_mention_id"], {})
        link = links_by_id.get(card["graph_link_id"], {})
        enriched_cards.append(
            {
                **card,
                "policy_event": event,
                "filing_mention": mention,
                "date_iso": _iso_date(event.get("date", "")),
                # The specific resolved country for THIS link — not
                # event["country"], which can be a bloc ("European Union")
                # for a policy event matched against several member states.
                "shared_country": link.get("shared_country") or mention.get("mentioned_country", ""),
            }
        )

    # --- Gap: FilingMentions with NO matching PolicyEvent this run — a real,
    # disclosed dependency the company itself named, but with nothing on the
    # policy side to confirm it against yet. See CHANGELOG.md Phase 6
    # (eval-08 / Lilly-China) for why this is a genuine, honest system
    # limitation worth surfacing rather than hiding. Grouped by company.
    linked_mention_ids = {link["filing_mention_id"] for link in links}
    gap_mentions = [
        {
            **m,
            "country": m["mentioned_country"],
            "commodity": m["mentioned_commodity"],
            "date_iso": _iso_date(m.get("filing_date", "")),
        }
        for m in mentions
        if m["id"] not in linked_mention_ids
    ]
    gap_by_company: dict[str, list[dict]] = {}
    for m in gap_mentions:
        gap_by_company.setdefault(m["company"], []).append(m)
    gaps_grouped = [
        # "mentions", not "items" — a dict key named "items" is unreachable
        # via Jinja's `.` attribute access because it collides with the
        # built-in dict.items() method, which Jinja finds first.
        {"company": company, "ticker": mentions_[0]["ticker"], "mentions": mentions_}
        for company, mentions_ in sorted(gap_by_company.items())
    ]

    # --- Opportunity: PolicyEvents with NO matching FilingMention this run —
    # a real policy action happened, but no covered company's filing has
    # been tied to it. Not grouped by company (there isn't one yet) —
    # grouped by country instead, which is the dimension that actually
    # applies to a policy event.
    linked_event_ids = {link["policy_event_id"] for link in links}
    opportunity_events = [
        {**e, "date_iso": _iso_date(e.get("date", ""))} for e in events if e["id"] not in linked_event_ids
    ]
    opportunities_by_country: dict[str, list[dict]] = {}
    for e in opportunity_events:
        opportunities_by_country.setdefault(e["country"], []).append(e)
    opportunities_grouped = [
        {"country": country, "events": items}
        for country, items in sorted(opportunities_by_country.items())
    ]

    graph_data = {
        "events": [
            {
                "id": e["id"],
                "headline": e["headline"],
                "country": e["country"],
                "commodity": e["affected_product"],
                "date": _iso_date(e["date"]),
                "severity": e["severity"],
                "source_url": e["source_url"],
            }
            for e in events
        ],
        "mentions": [
            {
                "id": m["id"],
                "company": m["company"],
                "ticker": m["ticker"],
                "country": m["mentioned_country"],
                "commodity": m["mentioned_commodity"],
                "date": _iso_date(m["filing_date"]),
                "source_url": m["source_url"],
            }
            for m in mentions
        ],
        "links": [
            {
                "id": link["id"],
                "event_id": link["policy_event_id"],
                "mention_id": link["filing_mention_id"],
                "shared_country": link["shared_country"],
            }
            for link in links
        ],
    }

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    dashboard_template = env.get_template("dashboard.html.jinja")
    html = dashboard_template.render(
        cards=enriched_cards,
        gaps_grouped=gaps_grouped,
        opportunities_grouped=opportunities_grouped,
        graph_data_json=json.dumps(graph_data),
        stats={
            "policy_events": len(events),
            "filing_mentions": len(mentions),
            "graph_links": len(links),
            "alert_cards": len(cards),
            "gap_mentions": len(gap_mentions),
            "opportunity_events": len(opportunity_events),
        },
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")

    glossary_template = env.get_template("glossary.html.jinja")
    glossary_html = glossary_template.render()
    GLOSSARY_OUTPUT_PATH.write_text(glossary_html, encoding="utf-8")

    return OUTPUT_PATH


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = build_dashboard()
    print(f"[dashboard] wrote {path}")
    print(f"[dashboard] wrote {GLOSSARY_OUTPUT_PATH}")
