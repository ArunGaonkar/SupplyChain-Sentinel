"""Phase 1 — THE BASELINE.

One direct LLM prompt over the raw cached text (policy items + filing
excerpts), asked to summarize/alert. No schema, no forced citations, no
structured cross-referencing between sources — this is the comparison
point the advanced pipeline (agents -> graph -> Alert Cards) must beat.

Output is saved verbatim to data/baseline_output.json in Phase 1 and is
NOT touched again after eval/run_eval.py runs in Phase 6.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.llm import call_llm

ROOT = Path(__file__).resolve().parent.parent

SYSTEM_PROMPT_TEMPLATE = (
    "You are a financial news analyst. You will be given a raw dump of {segment} "
    "trade-policy news items and SEC filing excerpts. Read them and write a "
    "short set of alerts about anything noteworthy for a portfolio manager "
    "tracking {segment} supply chains."
)


def _load_raw_text(segment: str) -> str:
    parts = []
    segment_dir = ROOT / "data" / segment / "cache"

    seen_urls = set()
    for path in sorted((segment_dir / "policy_raw").glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            parts.append(
                f"[POLICY ITEM] {item['date']} | {item['title']}\n"
                f"Source: {item['url']}\n"
                f"Snippet: {item['snippet']}\n"
            )

    for path in sorted((segment_dir / "filings_raw").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        for ex in record["excerpts"]:
            parts.append(
                f"[FILING EXCERPT] {record['company']} ({record['ticker']}) "
                f"{record['filing_type']} filed {record['filing_date']}\n"
                f"Source: {record['source_url']}\n"
                f"Excerpt: {ex['text']}\n"
            )

    return "\n---\n".join(parts)


def run_baseline(segment: str = "pharma", force_refresh: bool = False) -> dict:
    output_path = ROOT / "data" / segment / "baseline_output.json"
    # This output is the fixed comparison point for eval/run_eval.py (Phase 6)
    # — once it exists, later pipeline runs must NOT silently regenerate it
    # (a fresh LLM call would produce different prose each time and make the
    # baseline-vs-advanced comparison non-reproducible run to run).
    if output_path.exists() and not force_refresh:
        print(f"[baseline] using cached {output_path} (frozen after Phase 1 — pass force_refresh=True to redo)")
        return json.loads(output_path.read_text(encoding="utf-8"))

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(segment=segment)
    raw_text = _load_raw_text(segment)
    user_prompt = (
        f"Here is the raw pulled data ({segment} trade-policy news + SEC filing excerpts):\n\n"
        f"{raw_text}\n\n"
        "Write your alerts now."
    )
    response = call_llm(system_prompt, user_prompt, max_tokens=3000)

    result = {
        "phase": "baseline",
        "segment": segment,
        "description": "Single direct LLM prompt over raw cached text — no structure, no forced citations, no graph.",
        "input_char_count": len(raw_text),
        "system_prompt": system_prompt,
        "response": response,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    segment_arg = sys.argv[1] if len(sys.argv) > 1 else "pharma"
    result = run_baseline(segment=segment_arg)
    print(f"Baseline output saved to data/{segment_arg}/baseline_output.json")
    print(f"Input was {result['input_char_count']} chars\n")
    print(result["response"])
