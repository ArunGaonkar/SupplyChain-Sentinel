"""Pulls + caches raw policy/news items for the Policy Agent (src/agents/policy_agent.py).

Primary source: GDELT DOC 2.0 API (https://api.gdeltproject.org/api/v2/doc/doc) —
free, no key required, exactly as specified for this build.

Fallback source: Federal Register API (https://www.federalregister.gov/api/v1) —
also free, no key required. During this build, api.gdeltproject.org was
unreachable (connection timeouts from multiple network paths, matching
publicly reported GDELT infrastructure outages — see CHANGELOG.md Phase 0
entry). Since real pharma tariff/trade-policy notices are exactly what
Federal Register publishes (e.g. Presidential Proclamations adjusting
pharmaceutical ingredient tariffs), it is a faithful substitute for actual
US trade-policy events, not a mock. Both code paths are implemented; if
GDELT is reachable when you run this, it is used and the fallback is skipped.

This module does NOT extract structured fields (country, policy_type,
severity) — that is the Policy Agent's job. It only pulls and caches raw
text (title, url, date, snippet) so the whole pipeline can rerun from
data/cache/ with zero network calls.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "policy_raw"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FEDREG_URL = "https://www.federalregister.gov/api/v1/documents.json"
USER_AGENT = "SupplyChainSentinel/0.1 (hackathon submission; contact arun.rg37@gmail.com)"


def _slug(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")


def _try_gdelt(term: str, max_records: int = 25, timeout: int = 12) -> Optional[list[dict]]:
    try:
        r = requests.get(
            GDELT_URL,
            params={
                "query": term,
                "mode": "artlist",
                "maxrecords": max_records,
                "format": "json",
                "sort": "hybridrel",
            },
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        r.raise_for_status()
        data = r.json()
        articles = data.get("articles", [])
        return [
            {
                "source": "gdelt",
                "query_term": term,
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "date": (a.get("seendate", "") or "")[:8],  # YYYYMMDD
                "domain": a.get("domain", ""),
                "snippet": a.get("title", ""),  # DOC API artlist has no body snippet
                "source_country": a.get("sourcecountry", ""),
            }
            for a in articles
        ]
    except (requests.RequestException, ValueError) as e:
        print(f"  [gdelt] '{term}' unreachable ({type(e).__name__}: {e}) — will try fallback")
        return None


def _try_federal_register(term: str, per_page: int = 15, timeout: int = 20) -> list[dict]:
    r = requests.get(
        FEDREG_URL,
        params={
            "per_page": per_page,
            "conditions[term]": term,
            "conditions[type][]": ["PRORULE", "RULE", "NOTICE", "PRESDOCU"],
            "order": "relevance",
            "fields[]": [
                "title",
                "abstract",
                "html_url",
                "publication_date",
                "agencies",
                "type",
                "document_number",
            ],
        },
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    return [
        {
            "source": "federal_register",
            "query_term": term,
            "title": d.get("title", ""),
            "url": d.get("html_url", ""),
            "date": (d.get("publication_date", "") or "").replace("-", ""),
            "domain": "federalregister.gov",
            "snippet": d.get("abstract") or d.get("title", ""),
            "agencies": [a.get("name") for a in d.get("agencies", [])],
            "doc_type": d.get("type", ""),
            "document_number": d.get("document_number", ""),
        }
        for d in results
    ]


def pull_policy_events(query_terms: list[str], force_refresh: bool = False) -> list[dict]:
    """Pulls raw policy/news items for each query term, caching each to
    data/cache/policy_raw/<term>.json. Returns the combined list.

    If a cache file already exists and force_refresh is False, it is reused
    (this is what makes reruns work with zero network calls).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    combined: list[dict] = []
    gdelt_ever_worked = False

    for term in query_terms:
        cache_path = CACHE_DIR / f"{_slug(term)}.json"
        if cache_path.exists() and not force_refresh:
            print(f"  [cache hit] {cache_path.name}")
            combined.extend(json.loads(cache_path.read_text(encoding="utf-8")))
            continue

        print(f"[policy pull] '{term}'")
        items = _try_gdelt(term)
        if items is not None:
            gdelt_ever_worked = True
        else:
            time.sleep(1)
            try:
                items = _try_federal_register(term)
                print(f"  [federal_register] {len(items)} results for '{term}'")
            except requests.RequestException as e:
                print(f"  [federal_register] also failed for '{term}': {e}")
                items = []

        cache_path.write_text(json.dumps(items, indent=2), encoding="utf-8")
        combined.extend(items)
        time.sleep(0.5)  # be polite to free public APIs

    if not gdelt_ever_worked:
        print(
            "\n[gdelt] NOTE: api.gdeltproject.org was unreachable this run; "
            "all policy events above came from the Federal Register fallback. "
            "See CHANGELOG.md.\n"
        )
    return combined


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(ROOT))
    from src.config import load_segment

    cfg = load_segment("pharma")
    events = pull_policy_events(cfg["gdelt_query_terms"])
    print(f"\nTotal raw policy items cached: {len(events)}")
