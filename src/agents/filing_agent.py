"""Phase 3 — Agent 2: SEC filing agent.

Reads the raw cached filing excerpts (data/<segment>/cache/filings_raw/<TICKER>.json)
and uses an LLM to extract FilingMention objects: a company's stated
dependency on a specific country and/or commodity (API, generics, advanced
chips, etc.), citing the filing section it came from.

Like the Policy Agent, this requires real judgment: most excerpts are
generic risk-factor boilerplate or incidental country mentions (a product
approval in Japan, a tax-rate table) that do NOT represent a genuine
dependency. The agent must tell those apart from excerpts like Teva's "our
policy is to maintain multiple supply sources for APIs ... India" — or,
just as validly, NVIDIA's "[China] comprise a significant portion of our
revenue" under a US export-control regime — and skip the rest.

A dependency runs in TWO possible directions, and both count: a company can
depend on a country as a SOURCE (manufactures/sources there — the dominant
pattern for pharma tariffs) or as a MARKET/export destination (sells there,
or needs an export license to ship there — the dominant pattern for
semiconductor export controls, where NVIDIA's actual largest China exposure
is post-sale license risk, not sourcing). Missing the second direction was
a real gap found while building the semiconductor segment: the first prompt
here only recognized sourcing language, so it silently skipped NVIDIA's own
account of its most material China exposure. See CHANGELOG.md.
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

SYSTEM_PROMPT = """You are the Filing Agent in a {segment} supply-chain intelligence pipeline.
Segment scope: {segment_description}

You will be given excerpts pulled from one company's SEC 10-K filing, found by
searching for tariff/export-control-related terms and country names. Many of
these excerpts are generic legal boilerplate or truly incidental mentions
(a routine tax-rate reconciliation table with no operational content) that do
NOT represent a real dependency. Your job is to tell those apart from a
genuine one.

A genuine dependency runs in EITHER of two directions — both count equally:
  - SOURCE dependency: the company manufactures, sources, or otherwise
    materially relies on operations located in a specific country.
  - MARKET/EXPORT dependency: the company derives material revenue from, or
    requires a government export license/authorization to sell into, a
    specific country — e.g. "[Country] comprises a significant portion of
    our revenue" under an export-control regime, or "sales to customers in
    [Country] ... materially and adversely affected by export license
    requirements." This direction matters as much as sourcing for segments
    where the live policy lever is export control, not just tariffs.

For each excerpt that DOES describe a genuine dependency (either direction),
about one of this segment's commodities/products ({commodities}), extract one
FilingMention:
  - mentioned_country: the country (use one of the seed countries if it
    clearly matches: {countries}; otherwise the actual country named)
  - mentioned_commodity: the specific commodity/product, preferring one of
    {commodities} if it clearly matches, else short free text
  - risk_text: a verbatim quote (<=280 chars) from the excerpt supporting this
  - excerpt_index: the integer index of the input excerpt this came from

Skip excerpts that are truly incidental (e.g. a country named only in a legal
boilerplate list with no operational or revenue content) or too generic to
name a specific country. It is fine and expected to return an empty array if
none of the excerpts describe a real dependency.

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


def run_filing_agent(segment: str = "pharma", force_refresh: bool = False) -> list[FilingMention]:
    output_path = ROOT / "data" / segment / "filing_mentions.json"
    if output_path.exists() and not force_refresh:
        print(f"[filing_agent] using cached {output_path}")
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        return [FilingMention(**m) for m in raw]

    cfg = load_segment(segment)
    system = SYSTEM_PROMPT.format(
        segment=segment,
        segment_description=cfg.get("description", segment).strip(),
        countries=", ".join(cfg["countries"]),
        commodities=", ".join(cfg["commodities"]),
    )

    filings_raw_dir = ROOT / "data" / segment / "cache" / "filings_raw"
    mentions: list[FilingMention] = []
    for path in sorted(filings_raw_dir.glob("*.json")):
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
        # 2000 was enough when only sourcing-direction dependencies were in
        # scope; broadening to also recognize market/export dependencies
        # (see module docstring) means more excerpts genuinely qualify, and
        # 2000 silently truncated mid-JSON-array for two companies here.
        response = call_llm(system, user_prompt, max_tokens=3000)
        call_id = f"{segment}_{ticker}"
        try:
            parsed = extract_json(response)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  [filing_agent] {ticker}: failed to parse JSON ({e}), skipping")
            save_trajectory("filing_agent", call_id, system, user_prompt, response, parsed=None)
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

        save_trajectory("filing_agent", call_id, system, user_prompt, response, parsed=batch_mentions)
        print(f"  [filing_agent] {ticker}: {len(excerpts)} excerpts -> {len(batch_mentions)} mentions")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([m.model_dump() for m in mentions], indent=2), encoding="utf-8"
    )
    print(f"[filing_agent] {len(mentions)} FilingMentions saved to {output_path}")
    return mentions


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    segment_arg = sys.argv[1] if len(sys.argv) > 1 else "pharma"
    run_filing_agent(segment=segment_arg)
