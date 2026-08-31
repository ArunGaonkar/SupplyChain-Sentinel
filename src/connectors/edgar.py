"""Pulls + caches real SEC filing excerpts for the Filing Agent (src/agents/filing_agent.py).

Uses two free, keyless SEC EDGAR endpoints:
  1. https://www.sec.gov/files/company_tickers.json   -> ticker -> CIK lookup
  2. https://efts.sec.gov/LATEST/search-index          -> full-text search over filings
Then fetches the winning filing's actual HTML document and extracts the
paragraphs around each query-term mention (e.g. "tariffs", "active
pharmaceutical ingredient") as risk_text excerpts.

SEC requires a descriptive User-Agent identifying the requester (fair-access
policy) — see USER_AGENT below. No API key is required for either endpoint.

This module does NOT decide which country/commodity a mention refers to —
that structuring is the Filing Agent's job (an LLM reading the excerpt).
This module only pulls and caches the raw excerpt + citation.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import warnings

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent.parent
# Ticker -> CIK is a global lookup, not segment-specific, so it lives outside
# any data/<segment>/ tree and is shared/accumulated across all segments.
TICKERS_CACHE = ROOT / "data" / "cache" / "sec_company_tickers.json"
USER_AGENT = "SupplyChainSentinel research arun.rg37@gmail.com"
FTS_URL = "https://efts.sec.gov/LATEST/search-index"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

HEADERS = {"User-Agent": USER_AGENT}


def _get_cik_map(tickers: list[str], force_refresh: bool = False) -> dict[str, str]:
    """Returns {ticker: zero-padded-10-digit-CIK}, cached to disk.

    Caches only the resolved subset for tickers actually looked up (not
    SEC's full ~1.1MB company_tickers.json covering every US-listed
    company), accumulated across segments — so a later segment's lookups
    merge into the cache rather than overwriting an earlier segment's.
    """
    cached: dict[str, str] = {}
    if TICKERS_CACHE.exists():
        cached = json.loads(TICKERS_CACHE.read_text(encoding="utf-8"))
        if not force_refresh and all(t in cached for t in tickers):
            return {t: cached[t] for t in tickers}

    r = requests.get(TICKERS_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    raw = r.json()
    by_ticker = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in raw.values()}
    resolved = {t: by_ticker[t] for t in tickers if t in by_ticker}

    merged = {**cached, **resolved}
    TICKERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TICKERS_CACHE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return resolved


def _search_best_filing(
    cik: str, priority_terms: list[str], other_terms: list[str], forms: str = "10-K"
) -> Optional[dict]:
    """Tries the segment's priority terms first (the terms most central to
    this segment's causal thesis — "tariffs" for pharma, but "export
    control" matters at least as much for semiconductors), preferring
    recent filings; falls back to the other configured query terms, then to
    all-time, if nothing recent matches.

    A `forms=10-K` search over a company's full accession history matches
    ANY document filed as part of a 10-K submission, including exhibits
    (equity-plan terms, subsidiary guarantor lists, financing agreements) —
    those can outscore the actual 10-K body on a narrow term match and get
    returned as hits[0], which is a real, silent quality bug (three of our
    16 company pulls hit this before it was caught: MRK, INTC, MU each
    landed on an exhibit with zero operational content instead of the real
    10-K). Each hit's `_source.file_type` distinguishes them ("10-K" for the
    primary document vs. "EX-10.24" etc. for exhibits) — hits matching the
    requested form are preferred; if a search only turns up exhibit hits, an
    exhibit is used rather than treating the whole company as having no
    hits, but only as a last resort.
    """
    all_terms = priority_terms + [t for t in other_terms if t not in priority_terms]
    fallback: Optional[dict] = None
    for date_range in (("2023-01-01", "2026-12-31"), (None, None)):
        for term in all_terms:
            params = {"q": term, "ciks": cik, "forms": forms}
            if date_range[0]:
                params.update({"dateRange": "custom", "startdt": date_range[0], "enddt": date_range[1]})
            try:
                r = requests.get(FTS_URL, params=params, headers=HEADERS, timeout=20)
                r.raise_for_status()
                hits = r.json().get("hits", {}).get("hits", [])
            except (requests.RequestException, ValueError):
                hits = []
            time.sleep(0.3)
            for hit in hits:
                if hit["_source"].get("file_type") == forms:
                    return hit
            if hits and fallback is None:
                fallback = hits[0]  # keep the best exhibit-only hit as a last resort
        if fallback is not None:
            break
    return fallback


def _fetch_filing_text(cik_no_zeros: str, accession_no_dashes: str, filename: str) -> str:
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{filename}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "lxml")

    # Modern 10-Ks are inline-XBRL: a hidden block (div style="display:none"
    # containing <ix:header>/<ix:resources>/<xbrli:context> tag-soup with
    # raw fact dimensions like "us-gaap:ForeignCountryMember") sits alongside
    # the visible document. get_text() would otherwise pull that noise in as
    # if it were prose, so it's stripped first.
    for tag in soup.find_all(style=lambda v: v and "display:none" in v.replace(" ", "")):
        tag.decompose()
    for tag_name in ("script", "style"):
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for tag in soup.find_all(lambda t: t.name and (t.name.startswith("ix:") or t.name.startswith("xbrli"))):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text), url


def _extract_excerpts(
    text: str,
    priority_keywords: list[str],
    country_keywords: list[str],
    other_keywords: list[str],
    window: int = 350,
    priority_slots: int = 2,
    country_slots: int = 6,
    other_slots: int = 2,
) -> list[dict]:
    """Finds non-overlapping windows of text around keyword mentions, with a
    reserved slot budget per category rather than first-match-wins — a plain
    sequential fill lets the segment's priority terms (e.g. "tariffs" for
    pharma, which appears dozens of times as generic risk-factor
    boilerplate) crowd out the country mentions entirely, even though a
    country name near a sourcing/manufacturing mention is exactly the
    country<->commodity dependency signal the Filing Agent needs.

    country_keywords are round-robined (one hit per country before any
    country gets a second) so one heavily-mentioned country (e.g. "China")
    doesn't crowd out others (e.g. "Ireland") the way the priority terms did.
    """

    def find_spans(keywords: list[str]) -> dict[str, list[tuple[int, int]]]:
        by_kw: dict[str, list[tuple[int, int]]] = {kw: [] for kw in keywords}
        for kw in keywords:
            for m in re.finditer(re.escape(kw), text, re.IGNORECASE):
                by_kw[kw].append((m.start(), m.end()))
        return by_kw

    excerpts: list[dict] = []
    taken_starts: list[int] = []

    def try_add(start: int, end: int, kw: str) -> bool:
        if any(abs(start - s) < window for s in taken_starts):
            return False
        lo, hi = max(0, start - window), min(len(text), end + window)
        excerpts.append({"keyword": kw, "text": text[lo:hi].strip()})
        taken_starts.append(start)
        return True

    # 1. Priority-term mentions get a small reserved budget (already
    #    well-represented thematically; we don't want them to dominate).
    priority_spans = find_spans(priority_keywords)
    flat_priority = sorted((s, e, kw) for kw, spans in priority_spans.items() for s, e in spans)
    added = 0
    for start, end, kw in flat_priority:
        if added >= priority_slots:
            break
        if try_add(start, end, kw):
            added += 1

    # 2. Country mentions, round-robined for diversity across countries.
    country_spans = find_spans(country_keywords)
    added = 0
    round_idx = 0
    while added < country_slots:
        progressed = False
        for kw in country_keywords:
            if added >= country_slots:
                break
            spans = country_spans.get(kw, [])
            if round_idx >= len(spans):
                continue
            start, end = spans[round_idx]
            progressed = True
            if try_add(start, end, kw):
                added += 1
        round_idx += 1
        if not progressed:
            break

    # 3. Remaining "other" keywords (supply chain, API, etc.) fill what's left.
    other_spans = find_spans(other_keywords)
    flat_other = sorted((s, e, kw) for kw, spans in other_spans.items() for s, e in spans)
    added = 0
    for start, end, kw in flat_other:
        if added >= other_slots:
            break
        if try_add(start, end, kw):
            added += 1

    return excerpts


def pull_filings(
    companies: list[dict],
    query_terms: list[str],
    countries: list[str],
    segment: str = "pharma",
    priority_terms: list[str] | None = None,
    force_refresh: bool = False,
) -> list[dict]:
    """companies: list of {"name": ..., "ticker": ...} from config/segments/<segment>.yaml.
    countries: seed country list from config, used as secondary excerpt keywords.
    priority_terms: the terms most central to this segment's causal thesis
    ("tariffs"/"tariff" for pharma; something like "export control" matters
    at least as much for semiconductors) — searched and excerpted first,
    ahead of the rest of query_terms. Defaults to ["tariffs", "tariff"] for
    backward compatibility if not given.
    Returns combined list of cached filing records (one per company that had a hit).
    """
    priority_terms = priority_terms or ["tariffs", "tariff"]
    cache_dir = ROOT / "data" / segment / "cache" / "filings_raw"
    cache_dir.mkdir(parents=True, exist_ok=True)
    tickers = [c["ticker"] for c in companies]
    cik_map = _get_cik_map(tickers)

    results = []
    for company in companies:
        ticker = company["ticker"]
        cache_path = cache_dir / f"{ticker}.json"
        if cache_path.exists() and not force_refresh:
            print(f"  [cache hit] {cache_path.name}")
            results.append(json.loads(cache_path.read_text(encoding="utf-8")))
            continue

        cik = cik_map.get(ticker)
        if not cik:
            print(f"  [edgar] no CIK found for {ticker}, skipping")
            continue

        print(f"[edgar pull] {company['name']} ({ticker})")
        hit = _search_best_filing(cik, priority_terms, query_terms)
        if hit is None:
            print(f"  [edgar] no filing hits for {ticker}")
            continue

        src = hit["_source"]
        accession_no_dashes = src["adsh"].replace("-", "")
        filename = hit["_id"].split(":")[1]
        cik_no_zeros = str(int(cik))
        try:
            text, url = _fetch_filing_text(cik_no_zeros, accession_no_dashes, filename)
        except requests.RequestException as e:
            print(f"  [edgar] failed to fetch filing doc for {ticker}: {e}")
            continue

        # "United States" isn't an interesting sourcing-dependency country for
        # this graph (it's usually the policy-imposer, not the sourcing
        # location), so it's deprioritized to "other" rather than taking a
        # country slot.
        sourcing_countries = [c for c in countries if c != "United States"]
        priority_lower = {t.lower() for t in priority_terms}
        other_terms = [t for t in query_terms if t.lower() not in priority_lower] + ["United States"]
        excerpts = _extract_excerpts(
            text,
            priority_keywords=priority_terms,
            country_keywords=sourcing_countries,
            other_keywords=other_terms,
        )
        record = {
            "company": company["name"],
            "ticker": ticker,
            "cik": cik,
            "filing_type": src["form"],
            "filing_date": src["file_date"],
            "accession": src["adsh"],
            "source_url": url,
            "excerpts": excerpts,
        }
        cache_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        results.append(record)
        time.sleep(0.5)  # be polite to SEC's free endpoint

    return results


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(ROOT))
    from src.config import load_segment

    segment_arg = sys.argv[1] if len(sys.argv) > 1 else "pharma"
    cfg = load_segment(segment_arg)
    filings = pull_filings(
        cfg["companies"],
        cfg["edgar_query_terms"],
        cfg["countries"],
        segment=segment_arg,
        priority_terms=cfg.get("edgar_priority_terms"),
    )
    total_excerpts = sum(len(f["excerpts"]) for f in filings)
    print(f"\nFilings pulled: {len(filings)}, total excerpts: {total_excerpts}")
