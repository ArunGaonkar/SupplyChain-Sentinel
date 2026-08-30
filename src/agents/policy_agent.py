"""Phase 2 — Agent 1: Policy/news agent.

Reads the raw cached policy items (data/cache/policy_raw/*.json — Federal
Register trade-policy notices, or GDELT articles when that API is reachable),
and uses an LLM to:
  1. filter out items that aren't actually about pharma tariff/trade-policy
     (the raw pull is keyword-matched, so it includes noise like unrelated
     antidumping cases), and
  2. extract each real match into a structured PolicyEvent (country,
     policy_type, affected_product, severity), citing its source_url + a
     verbatim snippet.

This is a real judgment call the model has to make (not a reformat) — that's
the thing a single baseline prompt does badly at scale and this agent does
deliberately, one manageable batch at a time, with a trajectory log saved
per batch call.
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
from src.models import PolicyEvent

POLICY_RAW_DIR = ROOT / "data" / "cache" / "policy_raw"
OUTPUT_PATH = ROOT / "data" / "policy_events.json"
BATCH_SIZE = 18

SYSTEM_PROMPT = """You are the Policy Agent in a pharma supply-chain intelligence pipeline.

You will be given a batch of raw items pulled from government/news sources using
broad keyword search, so many are NOT actually relevant to pharmaceutical
tariff or trade policy (e.g. an antidumping case about soybean meal). Your job:

1. Read each item.
2. SKIP any item that is not substantively about a tariff, import/export
   restriction, trade agreement, or regulatory change affecting pharmaceutical
   products, active pharmaceutical ingredients (API), or medical devices.
3. For each item that IS relevant, extract one structured PolicyEvent:
   - country: the country whose policy/trade action this is (use one of the
     seed countries if it clearly matches: {countries}; otherwise use the
     actual country named)
   - policy_type: one of {policy_types}
   - affected_product: the specific pharma product/commodity affected,
     preferring one of {commodities} if it clearly matches, else short free text
   - severity: "low", "medium", or "high" — based on how material this policy
     action is (e.g. an active tariff change is higher severity than a routine
     public-comment request)
   - snippet: a short verbatim quote (<=200 chars) from the item's title/snippet
     that supports your extraction

Return ONLY a JSON array of objects with keys: country, policy_type,
affected_product, severity, snippet, source_index (the integer index of the
input item this came from). Do not include markdown fences or commentary.
If NO items in the batch are relevant, return an empty array []."""


def _make_id(source_url: str) -> str:
    return "PE-" + hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:10]


def _load_unique_raw_items() -> list[dict]:
    seen: dict[str, dict] = {}
    for path in sorted(POLICY_RAW_DIR.glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            seen.setdefault(item["url"], item)
    return list(seen.values())


def _batches(items: list[dict], size: int):
    for i in range(0, len(items), size):
        yield i, items[i : i + size]


def run_policy_agent(force_refresh: bool = False) -> list[PolicyEvent]:
    if OUTPUT_PATH.exists() and not force_refresh:
        print(f"[policy_agent] using cached {OUTPUT_PATH}")
        raw = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        return [PolicyEvent(**e) for e in raw]

    cfg = load_segment("pharma")
    system = SYSTEM_PROMPT.format(
        countries=", ".join(cfg["countries"]),
        policy_types=", ".join(cfg["policy_types"]),
        commodities=", ".join(cfg["commodities"]),
    )

    items = _load_unique_raw_items()
    print(f"[policy_agent] {len(items)} unique raw items to review")

    events: list[PolicyEvent] = []
    for batch_start, batch in _batches(items, BATCH_SIZE):
        user_lines = []
        for i, item in enumerate(batch):
            user_lines.append(
                f"[{i}] date={item['date']} title={item['title']!r} snippet={item['snippet']!r}"
            )
        user_prompt = "Batch of raw items:\n\n" + "\n".join(user_lines)

        response = call_llm(system, user_prompt, max_tokens=3000)
        call_id = f"batch_{batch_start:03d}"
        try:
            parsed = extract_json(response)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  [policy_agent] batch {batch_start}: failed to parse JSON ({e}), skipping batch")
            save_trajectory("policy_agent", call_id, system, user_prompt, response, parsed=None)
            continue

        batch_events = []
        for obj in parsed:
            src_idx = obj.get("source_index")
            if src_idx is None or not (0 <= src_idx < len(batch)):
                continue
            src_item = batch[src_idx]
            try:
                event = PolicyEvent(
                    id=_make_id(src_item["url"]),
                    country=obj["country"],
                    policy_type=obj["policy_type"],
                    affected_product=obj["affected_product"],
                    date=src_item["date"],
                    source_url=src_item["url"],
                    snippet=obj.get("snippet", src_item["title"])[:300],
                    severity=obj["severity"],
                )
            except Exception as e:
                print(f"  [policy_agent] skipping malformed event: {e}")
                continue
            events.append(event)
            batch_events.append(event.model_dump())

        save_trajectory("policy_agent", call_id, system, user_prompt, response, parsed=batch_events)
        print(f"  [policy_agent] batch {batch_start}: {len(batch)} items -> {len(batch_events)} events")

    OUTPUT_PATH.write_text(
        json.dumps([e.model_dump() for e in events], indent=2), encoding="utf-8"
    )
    print(f"[policy_agent] {len(events)} PolicyEvents saved to {OUTPUT_PATH}")
    return events


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_policy_agent()
