"""Phase 5 — static dashboard (v4, multi-segment).

Renders Alert Cards + a Gap/Opportunity view + an interactive dependency
graph to a single static HTML file via Jinja2, plus a separate glossary
page. No backend framework, no JS build step, no external JS/CSS
dependencies — open dist/index.html directly in a browser. Zero network
calls: reads only the JSON artifacts already produced in data/<segment>/ by
earlier phases.

Every segment with data on disk is loaded and rendered into the SAME page,
each record tagged with its segment — the Segment dropdown in the UI is a
client-side filter over that combined DOM (same mechanism as the existing
time-range filter), not a separate build per segment. That's what lets
switching segments update the graph, Alert Cards, Gaps, Opportunities, and
stat tiles together without a page reload.

The dependency graph is rendered CLIENT-SIDE (vanilla JS, embedded graph
data as JSON) rather than baked into static SVG, because it needs to
re-layout dynamically: a segment or time-range filter changes which
nodes/edges are visible, and a detail-level toggle changes the column
structure itself (Catalyst -> Country -> Company vs. the fuller Catalyst ->
Policy Scope -> Country -> Company). See templates/dashboard.html.jinja.

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

# Every segment config/segments/<name>.yaml can define; only the ones with
# actual pipeline output on disk (checked below) end up in the dashboard.
# Order here is display order in the Segment dropdown.
KNOWN_SEGMENTS = ["pharma", "semiconductor", "textile", "automotive", "steel_aluminum"]


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _iso_date(yyyymmdd: str) -> str:
    """'20260409' -> '2026-04-09' (also passes through already-ISO dates)."""
    s = (yyyymmdd or "").replace("-", "")
    if len(s) == 8:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return yyyymmdd or ""


def _build_segment(segment: str) -> dict:
    """Loads and shapes one segment's data. All returned records are tagged
    with "segment" so the client-side filter can select by it."""
    seg_dir = DATA_DIR / segment
    events = _load(seg_dir / "policy_events.json")
    mentions = _load(seg_dir / "filing_mentions.json")
    links = _load(seg_dir / "graph_links.json")
    cards = _load(seg_dir / "alert_cards.json")

    # IDs (PE-xxxx / FM-xxxx / GL-xxxx) are hashed from source_url and are
    # only unique WITHIN a segment. A broad, genuinely cross-industry
    # government notice (e.g. a multi-sector USMCA or reciprocal-tariff
    # order) legitimately gets pulled by more than one segment's search
    # terms, landing the identical id in both — confirmed to happen for real
    # between pharma/automotive and textile/automotive/steel_aluminum in
    # this run. Since every segment's data is merged into ONE client-side
    # `eventsById`/`mentionsById` map for the dashboard, an unprefixed id
    # from segment A silently overwrites segment B's entry with the same id,
    # which then makes segment B's own graph links resolve to the WRONG
    # segment when filtered — caught because pharma's link count on the live
    # dashboard read 4 instead of 12. Every id that crosses into the
    # client-side JSON (graph_data, and the data-event-id/data-mention-id
    # attributes the JS focus-filter matches against) is segment-prefixed
    # here to make it actually unique; ids used only for this function's own
    # internal per-segment lookups (events_by_id etc.) stay unprefixed since
    # they're scoped to one segment's own data and never collide.
    def gid(raw_id: str) -> str:
        return f"{segment}:{raw_id}"

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
                "segment": segment,
                "policy_event": event,
                "filing_mention": mention,
                "date_iso": _iso_date(event.get("date", "")),
                # The specific resolved country for THIS link — not
                # event["country"], which can be a bloc ("European Union")
                # for a policy event matched against several member states.
                "shared_country": link.get("shared_country") or mention.get("mentioned_country", ""),
                # Segment-prefixed — must match graph_events[].id / DATA.events
                # ids below for the graph's click-to-filter-cards feature to
                # resolve to the right card (see gid() note above).
                "graph_event_id": gid(card["policy_event_id"]),
                "graph_mention_id": gid(card["filing_mention_id"]),
            }
        )

    # --- Gap: FilingMentions with NO matching PolicyEvent this run.
    linked_mention_ids = {link["filing_mention_id"] for link in links}
    gap_mentions = [
        {
            **m,
            "segment": segment,
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
        {"segment": segment, "company": company, "ticker": mentions_[0]["ticker"], "mentions": mentions_}
        for company, mentions_ in sorted(gap_by_company.items())
    ]

    # --- Opportunity: PolicyEvents with NO matching FilingMention this run.
    # Grouped by country, not company — a policy event with no matching
    # filing doesn't have a company to group by yet.
    linked_event_ids = {link["policy_event_id"] for link in links}
    opportunity_events = [
        {**e, "segment": segment, "date_iso": _iso_date(e.get("date", "")), "graph_event_id": gid(e["id"])}
        for e in events
        if e["id"] not in linked_event_ids
    ]
    opportunities_by_country: dict[str, list[dict]] = {}
    for e in opportunity_events:
        opportunities_by_country.setdefault(e["country"], []).append(e)
    opportunities_grouped = [
        {"segment": segment, "country": country, "events": items}
        for country, items in sorted(opportunities_by_country.items())
    ]

    graph_events = [
        {
            "id": gid(e["id"]),
            "headline": e["headline"],
            "country": e["country"],
            "commodity": e["affected_product"],
            "date": _iso_date(e["date"]),
            "severity": e["severity"],
            "source_url": e["source_url"],
            "segment": segment,
        }
        for e in events
    ]
    graph_mentions = [
        {
            "id": gid(m["id"]),
            "company": m["company"],
            "ticker": m["ticker"],
            "country": m["mentioned_country"],
            "commodity": m["mentioned_commodity"],
            "date": _iso_date(m["filing_date"]),
            "source_url": m["source_url"],
            "segment": segment,
        }
        for m in mentions
    ]
    graph_links = [
        {
            "id": gid(link["id"]),
            "event_id": gid(link["policy_event_id"]),
            "mention_id": gid(link["filing_mention_id"]),
            "shared_country": link["shared_country"],
            "segment": segment,
        }
        for link in links
    ]

    return {
        "segment": segment,
        "has_data": bool(events),
        "cards": enriched_cards,
        "gaps_grouped": gaps_grouped,
        "opportunities_grouped": opportunities_grouped,
        "graph_events": graph_events,
        "graph_mentions": graph_mentions,
        "graph_links": graph_links,
        "stats": {
            "policy_events": len(events),
            "filing_mentions": len(mentions),
            "graph_links": len(links),
            "alert_cards": len(cards),
            "gap_mentions": len(gap_mentions),
            "opportunity_events": len(opportunity_events),
        },
    }


def build_dashboard() -> Path:
    segments = [_build_segment(s) for s in KNOWN_SEGMENTS]
    segments = [s for s in segments if s["has_data"]]
    if not segments:
        raise RuntimeError("No segment has any data in data/<segment>/policy_events.json — run run_pipeline.py first.")

    all_cards = [c for seg in segments for c in seg["cards"]]
    all_gaps_grouped = [g for seg in segments for g in seg["gaps_grouped"]]
    all_opportunities_grouped = [o for seg in segments for o in seg["opportunities_grouped"]]

    graph_data = {
        "events": [e for seg in segments for e in seg["graph_events"]],
        "mentions": [m for seg in segments for m in seg["graph_mentions"]],
        "links": [link for seg in segments for link in seg["graph_links"]],
    }

    default_segment = segments[0]["segment"]
    stub_segments = [s for s in KNOWN_SEGMENTS if s not in {seg["segment"] for seg in segments}]

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    dashboard_template = env.get_template("dashboard.html.jinja")
    html = dashboard_template.render(
        segments=segments,
        stub_segments=stub_segments,
        default_segment=default_segment,
        cards=all_cards,
        gaps_grouped=all_gaps_grouped,
        opportunities_grouped=all_opportunities_grouped,
        graph_data_json=json.dumps(graph_data),
        segment_stats_json=json.dumps({seg["segment"]: seg["stats"] for seg in segments}),
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
