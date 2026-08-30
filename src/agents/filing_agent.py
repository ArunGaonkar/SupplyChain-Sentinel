"""Phase 3 — Agent 2: SEC filing agent.

Reads the raw cached filing excerpts (data/cache/filings_raw/<TICKER>.json)
and uses an LLM to extract FilingMention objects: a company's stated
dependency on a specific country and/or commodity (API, generics, etc.),
citing the filing section it came from.

Like the Policy Agent, this requires real judgment: most excerpts are
generic risk-factor boilerplate or incidental country mentions (a product
approval in Japan, a tax-rate table) that do NOT represent a genuine
sourcing/manufacturing dependency. The agent must tell those apart from
excerpts like Teva's "our policy is to maintain multiple supply sources for
APIs ... India" or Viatris's plant locations list — and skip the rest.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_segment
from src.llm import call_llm, extract_json, save_trajectory
from src.models import FilingMention

FILINGS_RAW_DIR = ROOT / "data" / "cache" / "filings_raw"
OUTPUT_PATH = ROOT / "data" / "filing_mentions.json"

SYSTEM_PROMPT = """You are the Filing Agent in a pharma supply-chain intelligence pipeline.

You will be given excerpts pulled from one company's SEC 10-K filing, found by
searching for tariff-related terms and country names. Many of these excerpts
are generic legal boilerplate or incidental mentions (a product approval in a
country, a tax-rate reconciliation table) that do NOT represent a real
sourcing or manufacturing dependency. Your job is to tell those apart.

For each excerpt that DOES describe a genuine dependency — the company
manufactures, sources active pharmaceutical ingredients (API), or otherwise
materially relies on operations in a specific country, for a specific
commodity/product category — extract one FilingMention:
  - mentioned_country: the country (use one of the seed countries if it
    clearly matches: {countries}; otherwise the actual country named)
  - mentioned_commodity: the specific commodity/product, preferring one of
    {commodities} if it clearly matches, else short free text
  - risk_text: a verbatim quote (<=280 chars) from the excerpt supporting this
  - excerpt_index: the integer index of the input excerpt this came from

Skip excerpts that are incidental (a country only mentioned as a market where
a drug is sold or approved, without any sourcing/manufacturing dependency) or
too generic to name a specific country. It is fine and expected to return an
empty array if none of the excerpts describe a real dependency.

Return ONLY a JSON array of objects with keys: mentioned_country,
mentioned_commodity, risk_text, excerpt_index. No markdown fences, no
commentary."""


def _make_id(source_url: str, excerpt_index: int, country: str, commodity: str) -> str:
    # A single excerpt can legitimately name more than one country (e.g. "sites
    # in Puerto Rico, Ireland, and..."), producing multiple distinct
    # FilingMentions from the same excerpt_index — so country+commodity must
    # be part of the id, not just the excerpt location, or two real mentions
    # collide onto one id and one silently disappears from any dict keyed by id.
    key = f"{source_url}#{excerpt_index}#{country.lower()}#{commodity.lower()}"
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"FM-{h}"


def run_filing_agent(force_refresh: bool = False) -> list[FilingMention]:
    if OUTPUT_PATH.exists() and not force_refresh:
        print(f"[filing_agent] using cached {OUTPUT_PATH}")
        raw = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        return [FilingMention(**m) for m in raw]

    cfg = load_segment("pharma")
    system = SYSTEM_PROMPT.format(
        countries=", ".join(cfg["countries"]),
        commodities=", ".join(cfg["commodities"]),
    )

    mentions: list[FilingMention] = []
    for path in sorted(FILINGS_RAW_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        ticker = record["ticker"]
        excerpts = record["excerpts"]
        if not excerpts:
            continue

        user_lines = [
            f"Company: {record['company']} ({ticker}), {record['filing_type']} filed {record['filing_date']}",
            "",
            "Excerpts:",
        ]
        for i, ex in enumerate(excerpts):
            user_lines.append(f"[{i}] (matched keyword: {ex['keyword']!r}) {ex['text']}")
        user_prompt = "\n\n".join(user_lines)

        print(f"[filing_agent] {ticker}: reviewing {len(excerpts)} excerpts")
        response = call_llm(system, user_prompt, max_tokens=2000)
        try:
            parsed = extract_json(response)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  [filing_agent] {ticker}: failed to parse JSON ({e}), skipping")
            save_trajectory("filing_agent", ticker, system, user_prompt, response, parsed=None)
            continue

        batch_mentions = []
        for obj in parsed:
            idx = obj.get("excerpt_index")
            if idx is None or not (0 <= idx < len(excerpts)):
                continue
            try:
                mention = FilingMention(
                    id=_make_id(record["source_url"], idx, obj["mentioned_country"], obj["mentioned_commodity"]),
                    company=record["company"],
                    ticker=ticker,
                    filing_type=record["filing_type"],
                    filing_date=record["filing_date"],
                    mentioned_country=obj["mentioned_country"],
                    mentioned_commodity=obj["mentioned_commodity"],
                    risk_text=obj.get("risk_text", excerpts[idx]["text"])[:400],
                    source_url=record["source_url"],
                )
            except Exception as e:
                print(f"  [filing_agent] skipping malformed mention: {e}")
                continue
            mentions.append(mention)
            batch_mentions.append(mention.model_dump())

        save_trajectory("filing_agent", ticker, system, user_prompt, response, parsed=batch_mentions)
        print(f"  [filing_agent] {ticker}: {len(excerpts)} excerpts -> {len(batch_mentions)} mentions")

    OUTPUT_PATH.write_text(
        json.dumps([m.model_dump() for m in mentions], indent=2), encoding="utf-8"
    )
    print(f"[filing_agent] {len(mentions)} FilingMentions saved to {OUTPUT_PATH}")
    return mentions


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_filing_agent()
