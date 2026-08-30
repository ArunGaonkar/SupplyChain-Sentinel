"""Phase 5 — static dashboard.

Renders Alert Cards + one dependency-tree SVG to a single static HTML file
via Jinja2. No backend framework, no JS build step — open dist/index.html
directly in a browser. Zero network calls: reads only the JSON artifacts
already produced in data/ by earlier phases.

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

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _load(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _build_dependency_svg(events: list[dict], mentions: list[dict], links: list[dict]) -> str:
    """A 3-column diagram: Policy Events -> shared Country -> Companies,
    built for exactly the entities that appear in at least one graph link
    (no SVG/JS library — plain computed <svg> markup, so it renders with
    zero external dependencies)."""
    events_by_id = {e["id"]: e for e in events}
    mentions_by_id = {m["id"]: m for m in mentions}

    linked_event_ids, countries, companies = [], [], []
    edges_ec, edges_cc = [], []  # event->country, country->company
    for link in links:
        event = events_by_id[link["policy_event_id"]]
        mention = mentions_by_id[link["filing_mention_id"]]
        country = link["shared_country"] or mention["mentioned_country"]

        if event["id"] not in linked_event_ids:
            linked_event_ids.append(event["id"])
        if country not in countries:
            countries.append(country)
        if mention["ticker"] not in companies:
            companies.append(mention["ticker"])

        edge1 = (event["id"], country)
        if edge1 not in edges_ec:
            edges_ec.append(edge1)
        edge2 = (country, mention["ticker"])
        if edge2 not in edges_cc:
            edges_cc.append(edge2)

    if not linked_event_ids:
        return ""

    col_x = {"event": 40, "country": 380, "company": 700}
    row_h = 70
    top_pad = 40
    width = 900
    height = top_pad * 2 + row_h * max(len(linked_event_ids), len(countries), len(companies), 1)

    def y_for(items: list, key) -> float:
        idx = items.index(key)
        return top_pad + row_h * idx + row_h / 2

    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Inter, system-ui, sans-serif" font-size="13">'
    ]

    # edges first (so nodes draw on top)
    for src, dst in edges_ec:
        y1, y2 = y_for(linked_event_ids, src), y_for(countries, dst)
        svg_parts.append(
            f'<path d="M{col_x["event"]+220},{y1} C{col_x["country"]-60},{y1} '
            f'{col_x["event"]+260},{y2} {col_x["country"]},{y2}" '
            f'stroke="#94a3b8" stroke-width="1.5" fill="none" opacity="0.7"/>'
        )
    for src, dst in edges_cc:
        y1, y2 = y_for(countries, src), y_for(companies, dst)
        svg_parts.append(
            f'<path d="M{col_x["country"]+110},{y1} C{col_x["company"]-60},{y1} '
            f'{col_x["country"]+150},{y2} {col_x["company"]},{y2}" '
            f'stroke="#94a3b8" stroke-width="1.5" fill="none" opacity="0.7"/>'
        )

    def node(x, y, label, sub, fill, text_fill="#0f172a"):
        w = 220
        h = 44
        parts = [
            f'<rect x="{x}" y="{y - h/2:.1f}" width="{w}" height="{h}" rx="8" '
            f'fill="{fill}" stroke="#cbd5e1"/>',
            f'<text x="{x + 12}" y="{y - 3:.1f}" fill="{text_fill}" font-weight="600">{label}</text>',
        ]
        if sub:
            parts.append(f'<text x="{x + 12}" y="{y + 14:.1f}" fill="#475569" font-size="11">{sub}</text>')
        return "".join(parts)

    for eid in linked_event_ids:
        e = events_by_id[eid]
        y = y_for(linked_event_ids, eid)
        svg_parts.append(node(col_x["event"], y, e["country"], e["affected_product"][:28], "#eff6ff"))
    for c in countries:
        y = y_for(countries, c)
        svg_parts.append(node(col_x["country"], y, c, "shared country", "#f0fdf4"))
    for tkr in companies:
        y = y_for(companies, tkr)
        svg_parts.append(node(col_x["company"], y, tkr, "10-K filer", "#fef3c7"))

    svg_parts.append("</svg>")
    return "".join(svg_parts)


def build_dashboard() -> Path:
    events = _load("policy_events.json")
    mentions = _load("filing_mentions.json")
    links = _load("graph_links.json")
    cards = _load("alert_cards.json")

    cards_sorted = sorted(cards, key=lambda c: SEVERITY_ORDER.get(c["severity"], 3))
    events_by_id = {e["id"]: e for e in events}
    mentions_by_id = {m["id"]: m for m in mentions}

    enriched_cards = []
    for card in cards_sorted:
        enriched_cards.append(
            {
                **card,
                "policy_event": events_by_id.get(card["policy_event_id"], {}),
                "filing_mention": mentions_by_id.get(card["filing_mention_id"], {}),
            }
        )

    dependency_svg = _build_dependency_svg(events, mentions, links)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("dashboard.html.jinja")
    html = template.render(
        cards=enriched_cards,
        dependency_svg=dependency_svg,
        stats={
            "policy_events": len(events),
            "filing_mentions": len(mentions),
            "graph_links": len(links),
            "alert_cards": len(cards),
        },
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = build_dashboard()
    print(f"[dashboard] wrote {path}")
